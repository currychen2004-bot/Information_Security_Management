from __future__ import annotations

import re

from .errors import CredentialError


COOKIE_NAME_PATTERN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def _contains_control_characters(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def parse_cookie(cookie_text: str) -> dict[str, str]:
    if not cookie_text:
        return {}
    if _contains_control_characters(cookie_text):
        raise CredentialError("Cookie 包含禁止的控制字符。")

    cookies: dict[str, str] = {}
    for raw_part in cookie_text.split(";"):
        part = raw_part.strip()
        if not part:
            continue
        if "=" not in part:
            raise CredentialError("Cookie 片段缺少等号。")
        name, value = (item.strip() for item in part.split("=", 1))
        if not COOKIE_NAME_PATTERN.fullmatch(name):
            raise CredentialError("Cookie 名称不符合 HTTP Token 格式。")
        if _contains_control_characters(value):
            raise CredentialError("Cookie 值包含禁止的控制字符。")
        if name in cookies:
            raise CredentialError("Cookie 中存在重复名称。")
        cookies[name] = value
    return cookies


def build_cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in cookies.items())
