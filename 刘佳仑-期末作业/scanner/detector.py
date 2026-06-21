from __future__ import annotations

import re
import statistics
import time
from collections import OrderedDict
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

from .errors import AuthorizationError, ScannerError
from .models import Finding, HttpResponse, ScanResult


SQL_ERROR_PATTERNS = tuple(
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in (
        r"SQL syntax",
        r"mysql_fetch",
        r"mysqli_fetch",
        r"You have an error in your SQL syntax",
        r"Warning:\s*mysql_",
        r"Unclosed quotation mark",
        r"quoted string not properly terminated",
        r"ODBC SQL",
        r"PDOException",
        r"SQLite/JDBCDriver",
    )
)
ERROR_PAYLOADS = ("'", '"')
BOOLEAN_PAYLOAD_PAIR = ("' AND '1'='1'-- ", "' AND '1'='2'-- ")
TIME_PAYLOAD = "1 AND SLEEP(2)"
BOOLEAN_LENGTH_DIFFERENCE_RATIO = 0.15
TIME_DELAY_THRESHOLD_SECONDS = 1.2
MAX_PARAMETER_NAME_LENGTH = 64
MAX_PARAMETER_VALUE_LENGTH = 512


def _contains_control_characters(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _split_target(raw_url: str) -> tuple[str, OrderedDict[str, list[str]]]:
    parsed = urlparse(raw_url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if not pairs:
        raise AuthorizationError("URL 中没有可扫描的 Query 参数。")

    params: OrderedDict[str, list[str]] = OrderedDict()
    for name, value in pairs:
        if not name:
            raise AuthorizationError("Query 参数名称不得为空。")
        if len(name) > MAX_PARAMETER_NAME_LENGTH or _contains_control_characters(name):
            raise AuthorizationError("Query 参数名称超长或包含控制字符。")
        if len(value) > MAX_PARAMETER_VALUE_LENGTH or _contains_control_characters(value):
            raise AuthorizationError("Query 参数值超长或包含控制字符。")
        params.setdefault(name, []).append(value)
    base_url = urlunparse(parsed._replace(query="", fragment=""))
    return base_url, params


def _build_url(base_url: str, params: OrderedDict[str, list[str]]) -> str:
    return f"{base_url}?{urlencode(params, doseq=True)}"


def _mutate(
    params: OrderedDict[str, list[str]],
    parameter: str,
    payload: str,
) -> OrderedDict[str, list[str]]:
    mutated = OrderedDict((name, values.copy()) for name, values in params.items())
    values = mutated[parameter]
    values[0] = f"{values[0]}{payload}"
    return mutated


def _sql_error_hits(body: str) -> tuple[str, ...]:
    return tuple(pattern.pattern for pattern in SQL_ERROR_PATTERNS if pattern.search(body))


def _length_difference_ratio(first: str, second: str) -> float:
    return abs(len(first) - len(second)) / max(1, len(first), len(second))


def _run_get(client, url: str) -> HttpResponse:  # noqa: ANN001
    return client.get(url)


def scan(client, raw_url: str, *, enable_time_tests: bool = False) -> ScanResult:  # noqa: ANN001
    validated = client.policy.validate_url(raw_url)
    base_url, params = _split_target(raw_url)
    if len(params) > client.policy.max_parameters:
        raise AuthorizationError("Query 参数数量超过授权策略上限。")
    if enable_time_tests and not client.policy.allow_time_based_tests:
        raise AuthorizationError("授权配置未允许延时检测。")

    started_clock = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    findings: list[Finding] = []
    stopped_reason: str | None = None

    try:
        baseline_samples = [
            _run_get(client, _build_url(base_url, params)),
            _run_get(client, _build_url(base_url, params)),
        ]

        for parameter in params:
            for payload in ERROR_PAYLOADS:
                response = _run_get(
                    client,
                    _build_url(base_url, _mutate(params, parameter, payload)),
                )
                hits = _sql_error_hits(response.body)
                if hits:
                    findings.append(
                        Finding(
                            parameter=parameter,
                            category="sql-error-disclosure",
                            confidence="high",
                            evidence=f"响应命中 {len(hits)} 个 SQL 报错特征。",
                            payloads=(payload,),
                            status_codes=(response.status,),
                        )
                    )
                    break

            true_response = _run_get(
                client,
                _build_url(base_url, _mutate(params, parameter, BOOLEAN_PAYLOAD_PAIR[0])),
            )
            false_response = _run_get(
                client,
                _build_url(base_url, _mutate(params, parameter, BOOLEAN_PAYLOAD_PAIR[1])),
            )
            difference = _length_difference_ratio(true_response.body, false_response.body)
            baseline_median = statistics.median(len(item.body) for item in baseline_samples)
            true_gap = abs(len(true_response.body) - baseline_median) / max(1, baseline_median)
            if difference >= BOOLEAN_LENGTH_DIFFERENCE_RATIO and true_gap < difference:
                findings.append(
                    Finding(
                        parameter=parameter,
                        category="boolean-differential",
                        confidence="medium",
                        evidence=(
                            "布尔真假响应长度差异比例为 "
                            f"{difference:.2f}，且真条件更接近重复基线。"
                        ),
                        payloads=BOOLEAN_PAYLOAD_PAIR,
                        status_codes=(true_response.status, false_response.status),
                    )
                )

            if enable_time_tests:
                time_response = _run_get(
                    client,
                    _build_url(base_url, _mutate(params, parameter, TIME_PAYLOAD)),
                )
                baseline_elapsed = statistics.median(
                    item.elapsed_seconds for item in baseline_samples
                )
                delay = time_response.elapsed_seconds - baseline_elapsed
                if delay >= TIME_DELAY_THRESHOLD_SECONDS:
                    findings.append(
                        Finding(
                            parameter=parameter,
                            category="time-delay",
                            confidence="medium",
                            evidence=f"测试响应比基线中位数慢 {delay:.2f} 秒。",
                            payloads=(TIME_PAYLOAD,),
                            status_codes=(time_response.status,),
                        )
                    )
    except ScannerError as exc:
        stopped_reason = str(exc)

    display_host = (
        f"[{validated.hostname}]" if ":" in validated.hostname else validated.hostname
    )
    sanitized_target = urlunparse(
        (validated.scheme, f"{display_host}:{validated.port}", validated.path, "", "", "")
    )
    return ScanResult(
        scan_id=str(uuid4()),
        started_at=started_at,
        duration_seconds=time.perf_counter() - started_clock,
        target=sanitized_target,
        parameters=list(params),
        request_count=client.request_count,
        time_tests_enabled=enable_time_tests,
        findings=findings,
        stopped_reason=stopped_reason,
    )
