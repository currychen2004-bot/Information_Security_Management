from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scanner.detector import scan
from scanner.errors import AuthorizationError
from scanner.models import HttpResponse
from scanner.reporting import write_reports

from tests.helpers import make_policy


class FakeVulnerableClient:
    def __init__(self) -> None:
        self.policy = make_policy()
        self.request_count = 0

    def get(self, url: str) -> HttpResponse:
        self.request_count += 1
        value = parse_qs(urlparse(url).query, keep_blank_values=True)["id"][0]
        if value.endswith("'") or value.endswith('"'):
            body = "You have an error in your SQL syntax"
        elif "'1'='2'" in value:
            body = "no rows"
        else:
            body = "A" * 120
        return HttpResponse(200, body, 0.01, "text/html")


class DetectorAndReportingTests(unittest.TestCase):
    def test_error_and_boolean_evidence_are_reported(self) -> None:
        result = scan(
            FakeVulnerableClient(),
            "http://127.0.0.1/vulnerabilities/sqli/?id=1",
        )
        categories = {finding.category for finding in result.findings}
        self.assertIn("sql-error-disclosure", categories)
        self.assertIn("boolean-differential", categories)
        self.assertIsNone(result.stopped_reason)

    def test_time_test_requires_double_authorization(self) -> None:
        with self.assertRaisesRegex(AuthorizationError, "延时"):
            scan(
                FakeVulnerableClient(),
                "http://127.0.0.1/vulnerabilities/sqli/?id=1",
                enable_time_tests=True,
            )

    def test_encoded_query_control_character_is_rejected(self) -> None:
        with self.assertRaisesRegex(AuthorizationError, "控制字符"):
            scan(
                FakeVulnerableClient(),
                "http://127.0.0.1/vulnerabilities/sqli/?id%0aInjected=1",
            )

    def test_reports_are_private_and_do_not_contain_cookie(self) -> None:
        secret = "session-cookie-must-not-leak"
        client = FakeVulnerableClient()
        client.cookies = {"PHPSESSID": secret}
        result = scan(client, "http://127.0.0.1/vulnerabilities/sqli/?id=1")

        with tempfile.TemporaryDirectory() as directory:
            json_path, markdown_path = write_reports(result, Path(directory))
            combined = json_path.read_text() + markdown_path.read_text()
            self.assertNotIn(secret, combined)
            self.assertNotIn("id=1", combined)
            self.assertEqual(stat.S_IMODE(json_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(markdown_path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
