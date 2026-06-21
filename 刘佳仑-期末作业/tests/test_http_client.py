from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scanner.errors import SafetyLimitError
from scanner.http_client import SafeHttpClient

from tests.helpers import make_policy


class SecurityTestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/test/redirect"):
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.end_headers()
            return
        if self.path.startswith("/test/large"):
            body = b"A" * 4096
        else:
            body = b"baseline"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: ANN001, A002
        return


class SafeHttpClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), SecurityTestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_port

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def policy(self, **kwargs):  # noqa: ANN003
        return make_policy(ports=frozenset({self.port}), paths=("/test",), **kwargs)

    def test_normal_text_response_is_read(self) -> None:
        client = SafeHttpClient(self.policy())
        response = client.get(f"http://127.0.0.1:{self.port}/test/ok")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, "baseline")

    def test_redirect_is_blocked(self) -> None:
        client = SafeHttpClient(self.policy())
        with self.assertRaisesRegex(SafetyLimitError, "重定向"):
            client.get(f"http://127.0.0.1:{self.port}/test/redirect")

    def test_oversized_response_is_blocked(self) -> None:
        client = SafeHttpClient(self.policy(max_response_bytes=1024))
        with self.assertRaisesRegex(SafetyLimitError, "响应体"):
            client.get(f"http://127.0.0.1:{self.port}/test/large")

    def test_request_budget_is_enforced(self) -> None:
        client = SafeHttpClient(self.policy(max_requests=1))
        client.get(f"http://127.0.0.1:{self.port}/test/ok")
        with self.assertRaisesRegex(SafetyLimitError, "请求次数"):
            client.get(f"http://127.0.0.1:{self.port}/test/ok")


if __name__ == "__main__":
    unittest.main()
