from __future__ import annotations

import ipaddress

from scanner.policy import ScopePolicy


def make_policy(
    *,
    ports: frozenset[int] = frozenset({80}),
    paths: tuple[str, ...] = ("/vulnerabilities/sqli/",),
    networks: tuple[str, ...] = ("127.0.0.0/8",),
    max_requests: int = 40,
    max_response_bytes: int = 65536,
    allow_time_tests: bool = False,
) -> ScopePolicy:
    return ScopePolicy(
        allowed_hosts=frozenset({"127.0.0.1", "localhost"}),
        allowed_networks=tuple(ipaddress.ip_network(item) for item in networks),
        allowed_ports=ports,
        allowed_path_prefixes=paths,
        max_requests=max_requests,
        request_interval_seconds=0,
        timeout_seconds=2,
        max_response_bytes=max_response_bytes,
        max_parameters=5,
        allow_time_based_tests=allow_time_tests,
    )
