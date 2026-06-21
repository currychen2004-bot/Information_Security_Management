from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import ScanResult


def _atomic_private_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
        os.chmod(path, 0o600)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _markdown_text(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_markdown(result: ScanResult) -> str:
    status = "安全中止" if result.stopped_reason else "扫描完成"
    lines = [
        "# 受控 SQL 注入扫描报告",
        "",
        f"- 扫描编号：`{_markdown_text(result.scan_id)}`",
        f"- 开始时间：`{_markdown_text(result.started_at)}`",
        f"- 脱敏目标：`{_markdown_text(result.target)}`",
        f"- 参数名：`{_markdown_text(', '.join(result.parameters))}`",
        f"- 请求数：`{result.request_count}`",
        f"- 延时测试：`{'enabled' if result.time_tests_enabled else 'disabled'}`",
        f"- 状态：`{status}`",
        "",
    ]
    if result.stopped_reason:
        lines.extend(
            [
                "## 安全中止原因",
                "",
                _markdown_text(result.stopped_reason),
                "",
            ]
        )

    lines.extend(["## 可疑点", ""])
    if not result.findings:
        lines.extend(["未发现符合当前启发式规则的可疑点。该结果不代表目标绝对安全。", ""])
    else:
        lines.extend(
            [
                "| 参数 | 类型 | 置信度 | 证据 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for finding in result.findings:
            lines.append(
                f"| {_markdown_text(finding.parameter)} "
                f"| {_markdown_text(finding.category)} "
                f"| {_markdown_text(finding.confidence)} "
                f"| {_markdown_text(finding.evidence)} |"
            )
        lines.append("")

    lines.extend(
        [
            "## 人工复核提示",
            "",
            "本报告只记录启发式检测结果。应结合授权范围、DVWA 安全级别、请求重放和后端代码完成人工复核。",
            "",
            "> 报告不保存 Cookie、Query 参数值或原始响应体。",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(result: ScanResult, report_directory: Path) -> tuple[Path, Path]:
    json_path = report_directory / "latest-scan.json"
    markdown_path = report_directory / "latest-scan.md"
    _atomic_private_write(
        json_path,
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_private_write(markdown_path, render_markdown(result))
    return json_path, markdown_path
