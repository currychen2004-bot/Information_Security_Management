import unittest

from scanner.credentials import build_cookie_header, parse_cookie
from scanner.errors import CredentialError


class CredentialTests(unittest.TestCase):
    def test_valid_cookie_is_parsed(self) -> None:
        cookies = parse_cookie("PHPSESSID=test-session; security=low")
        self.assertEqual(
            build_cookie_header(cookies),
            "PHPSESSID=test-session; security=low",
        )

    def test_header_injection_is_rejected(self) -> None:
        with self.assertRaisesRegex(CredentialError, "控制字符"):
            parse_cookie("PHPSESSID=test\r\nX-Injected: yes")

    def test_malformed_cookie_is_rejected_instead_of_ignored(self) -> None:
        with self.assertRaisesRegex(CredentialError, "等号"):
            parse_cookie("PHPSESSID=test; malformed")

    def test_duplicate_cookie_name_is_rejected(self) -> None:
        with self.assertRaisesRegex(CredentialError, "重复"):
            parse_cookie("security=low; security=high")


if __name__ == "__main__":
    unittest.main()
