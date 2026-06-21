from __future__ import annotations

import time
from email.message import Message
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .credentials import build_cookie_header
from .errors import NetworkRequestError, SafetyLimitError
from .models import HttpResponse
from .policy import ScopePolicy


DEFAULT_USER_AGENT = "Authorized-DVWA-SQLI-Scanner/1.0"
ALLOWED_CONTENT_TYPES = (
    "text/",
    "application/json",
    "application/xhtml+xml",
    "application/xml",
)


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _content_type(headers: Message) -> str:
    return (headers.get_content_type() or "").lower()


def _decode_body(raw: bytes, headers: Message) -> str:
    charset = headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


class SafeHttpClient:
    def __init__(self, policy: ScopePolicy, cookies: dict[str, str] | None = None) -> None:
        self.policy = policy
        self.request_count = 0
        self._last_request_started: float | None = None
        # 不使用环境中的 HTTP_PROXY，避免本地靶场 Cookie 被转发给代理。
        self._opener = build_opener(ProxyHandler({}), NoRedirectHandler())
        self._headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json",
        }
        cookie_header = build_cookie_header(cookies or {})
        if cookie_header:
            self._headers["Cookie"] = cookie_header

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_started is None:
            return
        elapsed = time.monotonic() - self._last_request_started
        remaining = self.policy.request_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _read_limited(self, response) -> bytes:  # noqa: ANN001
        raw = response.read(self.policy.max_response_bytes + 1)
        if len(raw) > self.policy.max_response_bytes:
            raise SafetyLimitError("响应体超过授权策略中的大小上限。")
        return raw

    def get(self, url: str) -> HttpResponse:
        self.policy.validate_url(url)
        if self.request_count >= self.policy.max_requests:
            raise SafetyLimitError("已达到授权策略中的最大请求次数。")

        self._wait_for_rate_limit()
        self._last_request_started = time.monotonic()
        self.request_count += 1
        request = Request(url=url, headers=self._headers, method="GET")
        started = time.perf_counter()

        try:
            with self._opener.open(request, timeout=self.policy.timeout_seconds) as response:
                content_type = _content_type(response.headers)
                if content_type and not content_type.startswith(ALLOWED_CONTENT_TYPES):
                    raise SafetyLimitError("目标返回了不允许分析的响应类型。")
                body = _decode_body(self._read_limited(response), response.headers)
                return HttpResponse(
                    status=response.status,
                    body=body,
                    elapsed_seconds=time.perf_counter() - started,
                    content_type=content_type,
                )
        except HTTPError as exc:
            try:
                if 300 <= exc.code < 400:
                    raise SafetyLimitError("安全策略已阻止 HTTP 重定向。") from exc
                content_type = _content_type(exc.headers)
                if content_type and not content_type.startswith(ALLOWED_CONTENT_TYPES):
                    raise SafetyLimitError("目标返回了不允许分析的响应类型。") from exc
                body = _decode_body(self._read_limited(exc), exc.headers)
                return HttpResponse(
                    status=exc.code,
                    body=body,
                    elapsed_seconds=time.perf_counter() - started,
                    content_type=content_type,
                )
            finally:
                exc.close()
        except (URLError, TimeoutError, OSError) as exc:
            raise NetworkRequestError("目标网络请求失败，请检查本地靶场状态。") from exc
