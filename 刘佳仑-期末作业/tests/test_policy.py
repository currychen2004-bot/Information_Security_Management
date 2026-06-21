from __future__ import annotations

import socket
import unittest

from scanner.errors import AuthorizationError

from tests.helpers import make_policy


def resolver_for(address: str):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET

    def resolve(host, port, **kwargs):  # noqa: ANN001, ARG001
        socket_address = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
        return [(family, socket.SOCK_STREAM, 6, "", socket_address)]

    return resolve


class ScopePolicyTests(unittest.TestCase):
    def test_local_dvwa_target_is_allowed(self) -> None:
        policy = make_policy()
        target = policy.validate_url(
            "http://127.0.0.1/vulnerabilities/sqli/?id=1",
            resolver=resolver_for("127.0.0.1"),
        )
        self.assertEqual(target.hostname, "127.0.0.1")
        self.assertEqual(target.resolved_ips, ("127.0.0.1",))

    def test_ipv6_loopback_is_allowed_when_explicitly_scoped(self) -> None:
        policy = make_policy(networks=("127.0.0.0/8", "::1/128"))
        target = policy.validate_url(
            "http://localhost/vulnerabilities/sqli/?id=1",
            resolver=resolver_for("::1"),
        )
        self.assertEqual(target.resolved_ips, ("::1",))

    def test_public_host_is_rejected_by_host_allowlist(self) -> None:
        policy = make_policy()
        with self.assertRaisesRegex(AuthorizationError, "主机"):
            policy.validate_url(
                "https://example.com/vulnerabilities/sqli/?id=1",
                resolver=resolver_for("93.184.216.34"),
            )

    def test_public_ip_is_rejected_even_if_network_was_misconfigured(self) -> None:
        policy = make_policy(networks=("0.0.0.0/0",))
        with self.assertRaisesRegex(AuthorizationError, "IP"):
            policy.validate_url(
                "http://localhost/vulnerabilities/sqli/?id=1",
                resolver=resolver_for("93.184.216.34"),
            )

    def test_cloud_metadata_address_is_rejected(self) -> None:
        policy = make_policy(networks=("0.0.0.0/0",))
        with self.assertRaisesRegex(AuthorizationError, "IP"):
            policy.validate_url(
                "http://localhost/vulnerabilities/sqli/?id=1",
                resolver=resolver_for("169.254.169.254"),
            )

    def test_embedded_credentials_are_rejected(self) -> None:
        policy = make_policy()
        with self.assertRaisesRegex(AuthorizationError, "用户名或密码"):
            policy.validate_url(
                "http://user:secret@127.0.0.1/vulnerabilities/sqli/?id=1",
                resolver=resolver_for("127.0.0.1"),
            )

    def test_encoded_path_traversal_is_rejected(self) -> None:
        policy = make_policy()
        with self.assertRaisesRegex(AuthorizationError, "路径"):
            policy.validate_url(
                "http://127.0.0.1/vulnerabilities/sqli/%2e%2e/admin?id=1",
                resolver=resolver_for("127.0.0.1"),
            )

    def test_unsupported_scheme_is_rejected(self) -> None:
        policy = make_policy()
        with self.assertRaisesRegex(AuthorizationError, "http"):
            policy.validate_url("file:///etc/passwd", resolver=resolver_for("127.0.0.1"))


if __name__ == "__main__":
    unittest.main()
