"""
DVWA 暴力破解工具 — 安全测试用例
================================
测试覆盖：
  - 输入校验函数
  - 日志脱敏函数
  - BruteForcer 类线程安全
  - Cookie 解析优先级
  - 异常处理正确性
  - DVWA 安全等级适配
"""

import sys
import os
import threading
import queue
import json
import tempfile
import hashlib
from pathlib import Path

# 将上级目录加入 path，以便导入 dvwa_brute 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dvwa_brute as db


# ============================================================
# 1. 输入校验测试
# ============================================================
class TestInputValidation:
    """测试所有输入校验函数。"""

    def test_validate_url_valid(self):
        """合法 URL 应通过校验。"""
        assert db.validate_url("http://127.0.0.1/dvwa/vulnerabilities/brute/")
        assert db.validate_url("https://example.com:8080/path?param=value")
        assert db.validate_url("http://localhost/")

    def test_validate_url_invalid(self):
        """非法 URL 应被拒绝。"""
        assert not db.validate_url("")
        assert not db.validate_url("not-a-url")
        assert not db.validate_url("ftp://invalid.com/")
        assert not db.validate_url("://missing-scheme.com/")

    def test_validate_threads_valid(self):
        """合法线程数应通过校验。"""
        assert db.validate_threads(1)
        assert db.validate_threads(5)
        assert db.validate_threads(50)

    def test_validate_threads_invalid(self):
        """非法线程数应被拒绝。"""
        assert not db.validate_threads(0)
        assert not db.validate_threads(-1)
        assert not db.validate_threads(51)
        assert not db.validate_threads(1000)

    def test_validate_delay_valid(self):
        """合法延迟应通过校验。"""
        assert db.validate_delay(0.0)
        assert db.validate_delay(0.1)
        assert db.validate_delay(5.0)
        assert db.validate_delay(10.0)

    def test_validate_delay_invalid(self):
        """非法延迟应被拒绝。"""
        assert not db.validate_delay(-0.1)
        assert not db.validate_delay(10.1)
        assert not db.validate_delay(100.0)

    def test_validate_file_path_valid(self):
        """存在的非空文件应通过校验。"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("test content\n")
            tmp_path = f.name
        try:
            assert db.validate_file_path(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_validate_file_path_not_exist(self):
        """不存在的文件应被拒绝。"""
        assert not db.validate_file_path("/nonexistent/path/to/file.txt")

    def test_validate_file_path_empty(self):
        """空文件应被拒绝。"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            # 写空文件
            tmp_path = f.name
        try:
            assert not db.validate_file_path(tmp_path)
        finally:
            os.unlink(tmp_path)


# ============================================================
# 2. Cookie 安全测试
# ============================================================
class TestCookieSecurity:
    """测试 Cookie 脱敏和解析逻辑。"""

    def test_sanitize_short_cookie(self):
        """短 Cookie 脱敏。"""
        result = db.sanitize_cookie_for_log("abc")
        assert len(result) <= len("***") + 4

    def test_sanitize_normal_cookie(self):
        """正常长度 Cookie 脱敏 — 只保留前 8 字符。"""
        result = db.sanitize_cookie_for_log(
            "PHPSESSID=abcdef1234567890abcdef1234567890"
        )
        assert result.endswith("***")
        assert len(result) == 11  # 8 + "***"
        # 确保完整值没有出现在脱敏结果中
        assert "1234567890abcdef" not in result

    def test_sanitize_empty_cookie(self):
        """空 Cookie 脱敏返回占位符。"""
        result = db.sanitize_cookie_for_log("")
        assert result == "<empty>"

    def test_sanitize_none_cookie(self):
        """None Cookie 脱敏返回占位符。"""
        result = db.sanitize_cookie_for_log(None)
        assert result == "<empty>"

    def test_resolve_cookie_from_env(self, monkeypatch):
        """环境变量 DVWA_COOKIE 应优先使用。"""
        monkeypatch.setenv("DVWA_COOKIE", "env_cookie_value")
        result = db.resolve_cookie(cli_cookie="cli_value")
        assert result == "env_cookie_value"

    def test_resolve_cookie_from_file(self, monkeypatch):
        """配置文件应作为次优先级来源。"""
        monkeypatch.delenv("DVWA_COOKIE", raising=False)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("file_cookie_value")
            tmp_path = f.name
        try:
            result = db.resolve_cookie(cli_cookie=None, cookie_file=tmp_path)
            assert result == "file_cookie_value"
        finally:
            os.unlink(tmp_path)

    def test_resolve_cookie_fallback_to_cli(self, monkeypatch):
        """命令行 Cookie 应作为最低优先级备选。"""
        monkeypatch.delenv("DVWA_COOKIE", raising=False)
        result = db.resolve_cookie(cli_cookie="cli_fallback_value")
        assert result == "cli_fallback_value"


# ============================================================
# 3. BruteForcer 线程安全测试
# ============================================================
class TestBruteForcerThreadSafety:
    """测试 BruteForcer 的线程安全机制。"""

    def test_found_lock_exists(self):
        """BruteForcer 实例应有 found_lock 属性。"""
        bf = db.BruteForcer(
            url="http://127.0.0.1/test/",
            cookie="test=abc",
            user="admin",
            wordlist="non_existent_file.txt",
            threads=2,
        )
        assert hasattr(bf, "found_lock")
        assert isinstance(bf.found_lock, type(threading.Lock()))

    def test_attempt_lock_exists(self):
        """BruteForcer 实例应有 attempt_lock 属性。"""
        bf = db.BruteForcer(
            url="http://127.0.0.1/test/",
            cookie="test=abc",
            user="admin",
            wordlist="non_existent_file.txt",
            threads=2,
        )
        assert hasattr(bf, "attempt_lock")
        assert isinstance(bf.attempt_lock, type(threading.Lock()))

    def test_multiple_instances_independent(self):
        """不同 BruteForcer 实例应有独立的锁。"""
        bf1 = db.BruteForcer(
            url="http://127.0.0.1/test1/",
            cookie="test=abc",
            user="admin",
            wordlist="non_existent_file.txt",
            threads=1,
        )
        bf2 = db.BruteForcer(
            url="http://127.0.0.1/test2/",
            cookie="test=xyz",
            user="user",
            wordlist="non_existent_file.txt",
            threads=1,
        )
        assert bf1.found_lock is not bf2.found_lock
        assert bf1.found is False
        assert bf2.found is False

    def test_found_flag_under_lock(self):
        """found 标志在锁保护下应正确更新。"""
        bf = db.BruteForcer(
            url="http://127.0.0.1/test/",
            cookie="test=abc",
            user="admin",
            wordlist="non_existent_file.txt",
            threads=1,
        )
        with bf.found_lock:
            bf.found = True
        assert bf.found is True

        with bf.found_lock:
            bf.found = False
        assert bf.found is False


# ============================================================
# 4. 日志系统测试
# ============================================================
class TestLogging:
    """测试审计日志系统。"""

    def test_logger_has_handlers(self):
        """Logger 应配置了 handler。"""
        assert len(db.logger.handlers) >= 1

    def test_logger_setup_idempotent(self):
        """重复调用 setup_logging 不会重复添加 handler。"""
        initial_count = len(db.logger.handlers)
        db.setup_logging("dvwa_brute_test.log")
        assert len(db.logger.handlers) == initial_count


# ============================================================
# 5. 报告生成测试
# ============================================================
class TestReportGeneration:
    """测试结果报告生成功能。"""

    def test_generate_json_report_success(self):
        """成功爆破应生成有效的 JSON 报告。"""
        report_path = db.generate_report(
            report_format="json",
            target_url="http://127.0.0.1/test/",
            level="low",
            username="admin",
            password="password",
            total_attempts=42,
            elapsed=3.14,
            found=True,
            thread_count=5,
            delay=0.1,
        )
        assert report_path.endswith(".json")
        assert os.path.isfile(report_path)

        # 验证 JSON 结构
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["success"] is True
        assert data["username"] == "admin"
        assert data["password"] == "password"
        assert data["total_attempts"] == 42
        assert data["security_level"] == "low"

        os.unlink(report_path)

    def test_generate_json_report_failure(self):
        """爆破失败应生成有效的 JSON 报告（不含密码）。"""
        report_path = db.generate_report(
            report_format="json",
            target_url="http://127.0.0.1/test/",
            level="medium",
            username="",
            password="",
            total_attempts=1000,
            elapsed=60.0,
            found=False,
            thread_count=10,
            delay=0.5,
        )
        assert report_path.endswith(".json")
        assert os.path.isfile(report_path)

        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["success"] is False
        assert data["username"] is None
        assert data["password"] is None

        os.unlink(report_path)

    def test_generate_html_report(self):
        """HTML 报告应生成且包含关键信息。"""
        report_path = db.generate_report(
            report_format="html",
            target_url="http://127.0.0.1/test/",
            level="high",
            username="admin",
            password="letmein",
            total_attempts=99,
            elapsed=12.5,
            found=True,
            thread_count=3,
            delay=1.0,
        )
        assert report_path.endswith(".html")
        assert os.path.isfile(report_path)

        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "<!DOCTYPE html>" in content
        assert "admin" in content
        assert "letmein" in content
        assert "high" in content
        assert "99" in content

        os.unlink(report_path)

    def test_generate_report_invalid_format(self):
        """不支持的报告格式应返回空字符串。"""
        result = db.generate_report(
            report_format="xml",
            target_url="http://127.0.0.1/test/",
            level="low",
            username="",
            password="",
            total_attempts=0,
            elapsed=0,
            found=False,
            thread_count=1,
            delay=0,
        )
        assert result == ""


# ============================================================
# 6. 常量与配置测试
# ============================================================
class TestConstants:
    """测试安全相关常量和配置。"""

    def test_max_threads_reasonable(self):
        """最大线程数应在合理范围内。"""
        assert db.MAX_THREADS <= 100
        assert db.MAX_THREADS >= 10

    def test_min_threads_positive(self):
        """最小线程数应为正数。"""
        assert db.MIN_THREADS >= 1

    def test_request_timeout_set(self):
        """HTTP 请求超时应已设置。"""
        assert db.REQUEST_TIMEOUT > 0
        assert db.REQUEST_TIMEOUT <= 30  # 超时不应过长

    def test_success_flags_not_empty(self):
        """成功检测标志列表不应为空。"""
        assert len(db.SUCCESS_FLAGS) > 0

    def test_level_token_param_has_entries(self):
        """安全等级映射应包含 high 等级的 token 参数。"""
        assert "high" in db.LEVEL_TOKEN_PARAM
        assert db.LEVEL_TOKEN_PARAM["low"] is None
        assert db.LEVEL_TOKEN_PARAM["high"] == "user_token"


# ============================================================
# 7. 无裸 except 检查（代码质量）
# ============================================================
class TestNoBareExcept:
    """验证代码中没有裸 except:（通过 ast 静态检查）。"""

    def test_no_bare_except_in_source(self):
        """dvwa_brute.py 源码不应包含 'except:'（裸异常）。"""
        source_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "dvwa_brute.py",
        )
        with open(source_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith("#"):
                continue
            # 检查裸 except（注意：except Exception as e: 合法）
            if stripped == "except:" or stripped.startswith("except:"):
                # 进一步确认：不是 "except Exception" 等具体类型
                if stripped == "except:":
                    raise AssertionError(
                        f"发现裸 except: 在第 {i} 行: {line.rstrip()}"
                    )
                # 如果是 "except:" 后面跟空格，也不是具体异常
                if stripped.startswith("except: "):
                    raise AssertionError(
                        f"发现裸 except: 在第 {i} 行: {line.rstrip()}"
                    )
