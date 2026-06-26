# DVWA 暴力破解工具 — 安全加固整改报告

## 整改背景

本次整改针对 `dvwa_brute.py` 原始版本（169 行）中识别出的 8 项安全问题。整改过程使用 Claude Code 作为 AI 编程助手，所有安全约束在对话开始前通过结构化 Prompt 传递。完整交互记录见 `prompt-records.md`。

原始代码的安全缺陷按严重程度排列：

| 优先级 | 问题 | 直接影响 |
|--------|------|---------|
| 高 | 两处裸 `except:` 吞没所有异常 | 程序不可中断，故障不可诊断 |
| 高 | `self.found` 多线程无锁共享 | 竞态条件，可能重复写入结果 |
| 高 | 无任何速率限制机制 | 可能触发防火墙封锁或被判定为真实攻击 |
| 中 | Cookie 仅通过 CLI `-c` 明文传入 | 进程列表和 Shell 历史泄露凭证 |
| 中 | URL/线程数/文件路径零校验 | 非法输入导致不可预期行为 |
| 中 | 无持久化审计日志 | 操作行为无法事后追溯 |
| 低 | 检测字符串硬编码英文 | 非英文 DVWA 界面可能漏报 |
| 低 | 无使用授权声明 | 缺少合规自证材料 |

## 修改内容（按模块分组）

### 1. 凭据安全

- 新增 `resolve_cookie()` 函数，按环境变量 `DVWA_COOKIE` → `--cookie-file` 文件 → `-c` 命令行参数的优先级读取 Cookie。命令行方式每次使用都会触发 `logger.warning()` 安全警告，引导用户迁移到更安全的方式。
- 新增 `sanitize_cookie_for_log()` 函数，对写入日志的 Cookie 做脱敏：任何长度一律截取前 8 个字符后追加 `***`，空值返回 `<empty>`。`BruteForcer.__init__()` 中记录初始化日志时调用此函数。
- `generate_report()` 的 JSON 和 HTML 输出均不包含 Cookie 字段。

### 2. 异常处理

- 全局替换裸 `except:` → 具体异常类型。文件 I/O 路径使用 `FileNotFoundError` / `PermissionError` / `OSError` 三级区分；网络路径使用 `requests.ConnectionError` / `requests.Timeout` / `requests.RequestException` 三级区分；队列操作使用 `queue.Empty`。每个 `except` 分支都调用 `logger.error()` 或 `logger.warning()` 记录可诊断的上下文。
- 新增 AST 静态扫描测试（`test_no_bare_except_in_source`），在 CI 层面保证未来不会引入新的裸 `except:`。

### 3. 并发安全

- `BruteForcer.__init__()` 中新增两个 `threading.Lock` 实例：`self.found_lock`（保护破解成功标志和结果写入）、`self.attempt_lock`（保护尝试计数器）。
- `worker()` 中重写命中逻辑：`if hit:` 进入 `with self.found_lock:` 临界区，在锁内二次检查 `if not self.found:` 后才执行结果写入和标志置位，消除了经典的双重检测（double-check）TOCTOU 窗口。
- `total_attempts` 的自增操作在 `with self.attempt_lock:` 内完成。

### 4. 速率与资源控制

- 新增 `--delay` CLI 参数（默认 0.1 秒，合法范围 0.0-10.0 秒，由 `validate_delay()` 校验）。`worker()` 中在每次请求后执行 `time.sleep(self.delay)`。
- `REQUEST_TIMEOUT` 从 5 秒上调至 10 秒，所有 `requests.get()` 调用均传入 `timeout` 参数。
- 新增 `validate_threads()` 限制线程数在 1-50 范围内，拒绝 0 和大于 50 的值。

### 5. 输入校验

新增四个独立校验函数，在 `main()` 中按序调用，校验失败均给出中文提示后 `sys.exit(1)`：

- `validate_url()`：正则 `^https?://`，拒绝空字符串、无 scheme、`ftp://` 等非 HTTP 协议 URL。
- `validate_threads()`：检查 1 ≤ threads ≤ 50。
- `validate_delay()`：检查 0.0 ≤ delay ≤ 10.0。
- `validate_file_path()`：`pathlib.Path` 检查存在性 + 是否为文件 + 文件大小 > 0。

### 6. 审计日志

- 新增 `setup_logging()` 函数，配置双 Handler：`StreamHandler`（控制台，INFO 级别）和 `FileHandler`（文件，DEBUG 级别）。日志格式统一为 `时间戳 | 级别 | 线程名 | 消息`。
- `BruteForcer.__init__()`、`load_tasks()`、`worker()`、`run()` 中插入关键事件日志点：初始化参数（Cookie 脱敏）、任务加载统计、每次尝试（DEBUG）、成功命中、异常、总耗时和结果。
- `setup_logging()` 包含去重逻辑（`if logger.handlers: return logger`），避免重复调用导致 handler 累积。

### 7. 检测灵活性与 DVWA 适配

- `SUCCESS_FLAGS` 和 `FAIL_FLAGS` 从单个字符串改为列表，预置英文和中文两种 DVWA 界面语言的成功/失败标志。
- `BruteForcer.__init__()` 接受 `success_flags` 和 `fail_flags` 可选参数，允许用户注入自定义检测字符串。
- 新增 `--level` 参数（可选值 `low` / `medium` / `high`），`LEVEL_TOKEN_PARAM` 字典映射等级到 CSRF token 参数名。
- 新增 `_fetch_csrf_token()` 方法：high 等级下先 GET 页面，正则提取 `<input name="user_token" value="...">` 的值，构造爆破请求时一并发送。提取失败时降级为无 token 模式并通过 `logger.warning()` 通知。

### 8. 合规边界

- 新增 `show_disclaimer()` 函数：打印带 Unicode 边框的授权声明，要求用户输入 `yes` 确认。输入不为 `yes` 时 `sys.exit(0)`退出，`KeyboardInterrupt` 或 `EOFError` 时友好退出。
- 新增 `--skip-disclaimer` 标志，仅用于 pytest 自动化测试场景，正常使用时不应使用。

### 9. 报告与测试

- 新增 `generate_report()` 函数：支持 JSON（结构化机器可读）和 HTML（人类可读带 CSS 样式）两种格式。报告字段包括时间戳、目标 URL、安全等级、成功状态、用户名/密码（失败时为 null）、总尝试次数、耗时、线程数和延迟设置。报告不含 Cookie。
- 新建 `tests/test_security.py`：32 个测试用例，组织为 7 个测试类（输入校验 9 + Cookie 安全 6 + 线程安全 4 + 日志系统 2 + 报告生成 4 + 常量配置 5 + 裸 except 扫描 1）。

## 验收确认

以下验收条件在整改后的代码上已逐一验证：

- [x] Cookie 从环境变量读取时，不出现在进程列表或 Shell 历史中
- [x] 传入非法 URL 格式 → 输出"URL 格式不合法"并退出
- [x] 传入非法线程数 → 输出"线程数必须在 1-50 之间"并退出
- [x] 传入不存在的字典文件 → 输出"密码字典文件不存在或为空"并退出
- [x] 网络异常 → 日志中记录具体异常类型，不静默吞没
- [x] 多线程同时命中 → `result.txt` 仅写入一次
- [x] 启动 → 展示授权声明，`yes` 继续 / 其他退出
- [x] 日志文件 → 搜索不到完整 Cookie 原文
- [x] `--level high` → 自动携带 CSRF token
- [x] `--report json` → 生成有效 JSON，含完整统计
- [x] `pytest tests/test_security.py -v` → 32 passed
- [x] `bandit -r dvwa_brute.py` → 0 告警

## 测试证据

**pytest（32 个用例全部通过）**：

```text
platform win32 -- Python 3.12.7, pytest-7.4.4
collected 32 items

TestInputValidation::test_validate_url_valid PASSED
TestInputValidation::test_validate_url_invalid PASSED
TestInputValidation::test_validate_threads_valid PASSED
TestInputValidation::test_validate_threads_invalid PASSED
TestInputValidation::test_validate_delay_valid PASSED
TestInputValidation::test_validate_delay_invalid PASSED
TestInputValidation::test_validate_file_path_valid PASSED
TestInputValidation::test_validate_file_path_not_exist PASSED
TestInputValidation::test_validate_file_path_empty PASSED
TestCookieSecurity::test_sanitize_short_cookie PASSED
TestCookieSecurity::test_sanitize_normal_cookie PASSED
TestCookieSecurity::test_sanitize_empty_cookie PASSED
TestCookieSecurity::test_sanitize_none_cookie PASSED
TestCookieSecurity::test_resolve_cookie_from_env PASSED
TestCookieSecurity::test_resolve_cookie_from_file PASSED
TestCookieSecurity::test_resolve_cookie_fallback_to_cli PASSED
TestBruteForcerThreadSafety::test_found_lock_exists PASSED
TestBruteForcerThreadSafety::test_attempt_lock_exists PASSED
TestBruteForcerThreadSafety::test_multiple_instances_independent PASSED
TestBruteForcerThreadSafety::test_found_flag_under_lock PASSED
TestLogging::test_logger_has_handlers PASSED
TestLogging::test_logger_setup_idempotent PASSED
TestReportGeneration::test_generate_json_report_success PASSED
TestReportGeneration::test_generate_json_report_failure PASSED
TestReportGeneration::test_generate_html_report PASSED
TestReportGeneration::test_generate_report_invalid_format PASSED
TestConstants::test_max_threads_reasonable PASSED
TestConstants::test_min_threads_positive PASSED
TestConstants::test_request_timeout_set PASSED
TestConstants::test_success_flags_not_empty PASSED
TestConstants::test_level_token_param_has_entries PASSED
TestNoBareExcept::test_no_bare_except_in_source PASSED

============================== 32 passed in 0.59s ==============================
```

**bandit（零告警）**：

```text
Test results:
        No issues identified.

Code scanned:
        Total lines of code: 693

Run metrics:
        Total issues (by severity):
                Undefined: 0 | Low: 0 | Medium: 0 | High: 0
```
