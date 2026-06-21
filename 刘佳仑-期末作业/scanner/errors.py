class ScannerError(Exception):
    """扫描器可预期错误的基类。"""


class ConfigurationError(ScannerError):
    """授权配置无效。"""


class AuthorizationError(ScannerError):
    """扫描目标超出授权范围。"""


class CredentialError(ScannerError):
    """凭据格式不安全或无效。"""


class SafetyLimitError(ScannerError):
    """请求超出安全资源限制。"""


class NetworkRequestError(ScannerError):
    """网络请求在不泄露响应细节的情况下失败。"""
