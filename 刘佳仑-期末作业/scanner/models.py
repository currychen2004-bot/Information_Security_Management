from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidatedTarget:
    url: str
    scheme: str
    hostname: str
    port: int
    path: str
    resolved_ips: tuple[str, ...]


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str
    elapsed_seconds: float
    content_type: str


@dataclass(frozen=True)
class Finding:
    parameter: str
    category: str
    confidence: str
    evidence: str
    payloads: tuple[str, ...]
    status_codes: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["payloads"] = list(self.payloads)
        result["status_codes"] = list(self.status_codes)
        return result


@dataclass
class ScanResult:
    scan_id: str
    started_at: str
    duration_seconds: float
    target: str
    parameters: list[str]
    request_count: int
    time_tests_enabled: bool
    findings: list[Finding] = field(default_factory=list)
    stopped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "started_at": self.started_at,
            "duration_seconds": round(self.duration_seconds, 3),
            "target": self.target,
            "parameters": self.parameters,
            "request_count": self.request_count,
            "time_tests_enabled": self.time_tests_enabled,
            "stopped_reason": self.stopped_reason,
            "findings": [finding.to_dict() for finding in self.findings],
        }
