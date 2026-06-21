from __future__ import annotations

import ipaddress
import json
import posixpath
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import unquote, urlparse

from .errors import AuthorizationError, ConfigurationError
from .models import ValidatedTarget


Resolver = Callable[..., list[tuple]]
CONTROL_CHARACTERS = {chr(value) for value in range(32)} | {chr(127)}
MAX_URL_LENGTH = 2048


def _require_string_list(data: dict, key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ConfigurationError(f"{key} 必须是非空字符串数组。")
    return value


def _bounded_number(
    data: dict,
    key: str,
    minimum: float,
    maximum: float,
    *,
    integer: bool = False,
) -> float | int:
    value = data.get(key)
    expected = int if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, expected):
        raise ConfigurationError(f"{key} 必须是数值。")
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{key} 必须在 {minimum} 到 {maximum} 之间。")
    return int(value) if integer else float(value)


def _path_is_allowed(path: str, prefixes: Iterable[str]) -> bool:
    for prefix in prefixes:
        normalized_prefix = prefix.rstrip("/") or "/"
        if path == normalized_prefix or path.startswith(f"{normalized_prefix}/"):
            return True
    return False


@dataclass(frozen=True)
class ScopePolicy:
    allowed_hosts: frozenset[str]
    allowed_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
    allowed_ports: frozenset[int]
    allowed_path_prefixes: tuple[str, ...]
    max_requests: int
    request_interval_seconds: float
    timeout_seconds: float
    max_response_bytes: int
    max_parameters: int
    allow_time_based_tests: bool

    @classmethod
    def from_file(cls, path: Path) -> "ScopePolicy":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigurationError("无法读取授权配置文件。") from exc
        if not isinstance(raw, dict):
            raise ConfigurationError("授权配置的顶层必须是 JSON 对象。")

        hosts = {
            item.strip().lower().rstrip(".")
            for item in _require_string_list(raw, "allowed_hosts")
        }
        if any(not host or any(char in CONTROL_CHARACTERS for char in host) for host in hosts):
            raise ConfigurationError("allowed_hosts 包含无效主机名。")

        try:
            networks = tuple(
                ipaddress.ip_network(item, strict=True)
                for item in _require_string_list(raw, "allowed_networks")
            )
        except ValueError as exc:
            raise ConfigurationError("allowed_networks 包含无效网段。") from exc

        ports_raw = raw.get("allowed_ports")
        if (
            not isinstance(ports_raw, list)
            or not ports_raw
            or any(isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535 for port in ports_raw)
        ):
            raise ConfigurationError("allowed_ports 必须是 1-65535 的非空整数数组。")

        paths = tuple(_require_string_list(raw, "allowed_path_prefixes"))
        if any(not path.startswith("/") or "\\" in path for path in paths):
            raise ConfigurationError("allowed_path_prefixes 必须是以 / 开头的 URL 路径。")

        allow_time = raw.get("allow_time_based_tests", False)
        if not isinstance(allow_time, bool):
            raise ConfigurationError("allow_time_based_tests 必须是布尔值。")

        return cls(
            allowed_hosts=frozenset(hosts),
            allowed_networks=networks,
            allowed_ports=frozenset(ports_raw),
            allowed_path_prefixes=paths,
            max_requests=int(_bounded_number(raw, "max_requests", 1, 200, integer=True)),
            request_interval_seconds=float(
                _bounded_number(raw, "request_interval_seconds", 0, 10)
            ),
            timeout_seconds=float(_bounded_number(raw, "timeout_seconds", 0.2, 30)),
            max_response_bytes=int(
                _bounded_number(raw, "max_response_bytes", 1024, 5 * 1024 * 1024, integer=True)
            ),
            max_parameters=int(_bounded_number(raw, "max_parameters", 1, 20, integer=True)),
            allow_time_based_tests=allow_time,
        )

    def validate_url(
        self,
        raw_url: str,
        *,
        resolver: Resolver = socket.getaddrinfo,
    ) -> ValidatedTarget:
        if (
            not raw_url
            or len(raw_url) > MAX_URL_LENGTH
            or any(char in CONTROL_CHARACTERS for char in raw_url)
        ):
            raise AuthorizationError("URL 为空或包含控制字符。")

        parsed = urlparse(raw_url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise AuthorizationError("只允许 http 或 https 目标。")
        if parsed.username is not None or parsed.password is not None:
            raise AuthorizationError("禁止在 URL 中携带用户名或密码。")
        if parsed.fragment:
            raise AuthorizationError("目标 URL 不应包含片段标识符。")

        hostname = (parsed.hostname or "").lower().rstrip(".")
        if hostname not in self.allowed_hosts:
            raise AuthorizationError("目标主机不在授权白名单中。")
        try:
            port = parsed.port or (443 if scheme == "https" else 80)
        except ValueError as exc:
            raise AuthorizationError("目标端口格式无效。") from exc
        if port not in self.allowed_ports:
            raise AuthorizationError("目标端口不在授权白名单中。")

        decoded_path = unquote(parsed.path or "/")
        if "\\" in decoded_path or any(char in CONTROL_CHARACTERS for char in decoded_path):
            raise AuthorizationError("目标路径包含非法字符。")
        path = posixpath.normpath(decoded_path)
        if decoded_path.endswith("/") and not path.endswith("/"):
            path += "/"
        if not _path_is_allowed(path, self.allowed_path_prefixes):
            raise AuthorizationError("目标路径不在授权白名单中。")

        try:
            address_info = resolver(hostname, port, type=socket.SOCK_STREAM)
            resolved = {
                ipaddress.ip_address(str(item[4][0]).split("%", 1)[0])
                for item in address_info
            }
        except (OSError, ValueError, IndexError, TypeError) as exc:
            raise AuthorizationError("目标主机无法安全解析。") from exc
        if not resolved:
            raise AuthorizationError("目标主机没有可用 IP 地址。")

        for address in resolved:
            if (
                not address.is_loopback
                and (
                    address.is_global
                    or address.is_link_local
                    or address.is_multicast
                    or address.is_unspecified
                    or address.is_reserved
                )
            ):
                raise AuthorizationError("目标解析到禁止的 IP 地址类型。")
            if not any(address in network for network in self.allowed_networks):
                raise AuthorizationError("目标 IP 不在授权网段中。")

        return ValidatedTarget(
            url=raw_url,
            scheme=scheme,
            hostname=hostname,
            port=port,
            path=path,
            resolved_ips=tuple(sorted(str(address) for address in resolved)),
        )
