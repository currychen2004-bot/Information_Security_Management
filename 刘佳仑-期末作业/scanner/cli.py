from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from .credentials import parse_cookie
from .detector import scan
from .errors import ConfigurationError, ScannerError
from .http_client import SafeHttpClient
from .policy import ScopePolicy
from .reporting import write_reports


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SCOPE = PROJECT_DIR / "config" / "authorized-scope.example.json"
DEFAULT_REPORT_DIR = PROJECT_DIR / "reports" / "generated"


def _sanitized_display_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    return urlunparse(parsed._replace(query="", fragment=""))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="受控授权的 DVWA SQL 注入扫描器",
    )
    parser.add_argument("--url", required=True, help="已授权的本地 DVWA URL，需包含 Query 参数")
    parser.add_argument(
        "--scope",
        type=Path,
        default=DEFAULT_SCOPE,
        help="JSON 授权范围配置文件",
    )
    parser.add_argument(
        "--cookie-env",
        default="DVWA_COOKIE",
        help="保存 Cookie 的环境变量名，默认为 DVWA_COOKIE",
    )
    parser.add_argument(
        "--prompt-cookie",
        action="store_true",
        help="通过隐藏输入读取 Cookie，优先于环境变量",
    )
    parser.add_argument(
        "--enable-time-tests",
        action="store_true",
        help="申请执行延时测试，同时需要授权配置允许",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="脱敏报告输出目录",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        policy = ScopePolicy.from_file(args.scope)
        policy.validate_url(args.url)
        if args.prompt_cookie:
            cookie_text = getpass.getpass("DVWA Cookie（输入不回显）: ")
        else:
            cookie_text = os.environ.get(args.cookie_env, "")
        cookies = parse_cookie(cookie_text)
        client = SafeHttpClient(policy, cookies)

        allowed_report_root = (PROJECT_DIR / "reports").resolve()
        report_directory = args.report_dir.resolve()
        if not report_directory.is_relative_to(allowed_report_root):
            raise ConfigurationError("报告目录必须位于个人作业的 reports 目录内。")

        print(f"[*] 已通过授权校验的目标: {_sanitized_display_url(args.url)}")
        print(f"[*] 延时测试: {'已申请' if args.enable_time_tests else '禁用'}")
        result = scan(client, args.url, enable_time_tests=args.enable_time_tests)
        json_path, markdown_path = write_reports(result, report_directory)

        print(f"[*] 请求数: {result.request_count}")
        print(f"[*] 可疑点: {len(result.findings)}")
        if result.stopped_reason:
            print(f"[!] 扫描已安全中止: {result.stopped_reason}")
        print(f"[*] JSON 报告: {json_path}")
        print(f"[*] Markdown 报告: {markdown_path}")
        return 3 if result.stopped_reason else 0
    except ScannerError as exc:
        print(f"[!] 安全中止: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
