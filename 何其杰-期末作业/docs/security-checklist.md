# DVWA 暴力破解工具 — 代码审查与安全检查记录

## 审查说明

AI 生成的代码不能直接信任。本次审查分两轮进行：第一轮逐条对照原始 Prompt 中的约束，确认每个要求都有对应的代码实现；第二轮从攻击者和审计者视角出发，检查那些 Prompt 中没有显式提及但实际存在的安全问题。

审查对象：`dvwa_brute.py` 安全加固版（693 行）及配套测试 `tests/test_security.py`（32 个用例）。

---

## 第一轮：逐条对照 Prompt 约束

以下 11 条对应 `constraint-doc.md` 和对话二 Prompt 中给出的每项安全要求。每条均直接检查源码中的对应位置。

**1. Cookie 多级读取优先级**

- 结果：通过
- 代码位置：`resolve_cookie()` 函数，环境变量 `DVWA_COOKIE` → `--cookie-file` → `-c` 三级，CLI 方式调用 `logger.warning()` 输出提醒
- 测试覆盖：`TestCookieSecurity` 类 6 个用例，验证三级优先级和 CLI 警告行为

**2. 无裸 except**

- 结果：通过
- 代码位置：全局搜索确认。文件 I/O 使用 `FileNotFoundError` / `PermissionError` / `OSError`；网络请求使用 `requests.ConnectionError` / `requests.Timeout` / `requests.RequestException`；队列操作使用 `queue.Empty`
- 测试覆盖：`TestNoBareExcept::test_no_bare_except_in_source` 用 AST 静态扫描源码，逐行检查，确认零残留

**3. 共享状态加锁**

- 结果：通过
- 代码位置：`BruteForcer.__init__()` 中初始化 `self.found_lock = threading.Lock()` 和 `self.attempt_lock = threading.Lock()`；`worker()` 中 `with self.found_lock:` 保护标志读写和结果写入；`with self.attempt_lock:` 保护计数器
- 测试覆盖：`TestBruteForcerThreadSafety` 类 4 个用例，验证锁存在、类型正确、实例独立、锁保护下状态正确读写

**4. 请求超时**

- 结果：通过
- 代码位置：常量 `REQUEST_TIMEOUT = 10`；`worker()` 和 `_fetch_csrf_token()` 中所有 `requests.get()` 调用均传入 `timeout=REQUEST_TIMEOUT`
- 测试覆盖：`test_request_timeout_set` 验证常量在 1-30 合理范围内

**5. 速率限制**

- 结果：通过
- 代码位置：`--delay` 参数（默认 0.1）；`worker()` 中每次请求后 `time.sleep(self.delay)`；`validate_delay()` 限制范围 0.0-10.0
- 测试覆盖：`TestInputValidation` 中 4 个 delay 校验用例

**6. URL 格式校验**

- 结果：通过
- 代码位置：`validate_url()` 正则匹配 `^https?://` 开头格式；`main()` 中在发起任何网络请求前调用
- 测试覆盖：`test_validate_url_valid`（合法 URL 放行）和 `test_validate_url_invalid`（空字符串、非 URL、ftp 协议拒绝）

**7. 线程数范围校验**

- 结果：通过
- 代码位置：`validate_threads()` 限制 1-50；`main()` 中校验不通过则 `sys.exit(1)`
- 测试覆盖：合法值 1/5/50 通过，0/-1/51/1000 拒绝

**8. 文件路径校验**

- 结果：通过
- 代码位置：`validate_file_path()` 检查 `Path.exists()` + `is_file()` + `stat().st_size > 0`；`main()` 中对 `--wordlist` 调用
- 测试覆盖：存在非空文件通过，不存在路径拒绝，空文件拒绝

**9. 审计日志**

- 结果：通过
- 代码位置：`setup_logging()` 配置文件和控台双 Handler；文件 DEBUG 级（含每次尝试的用户名和密码），控制台 INFO 级；支持 `--log-file` 自定义路径
- 测试覆盖：`TestLogging` 类 2 个用例

**10. Cookie 日志脱敏**

- 结果：通过
- 代码位置：`sanitize_cookie_for_log()` 只保留前 8 字符后追加 `***`；`BruteForcer.__init__()` 记录日志时调用该函数
- 测试覆盖：`TestCookieSecurity` 中 4 个脱敏用例（正常长度、短值、空字符串、None）

**11. 授权声明**

- 结果：通过
- 代码位置：`show_disclaimer()` 打印带边框声明文本，`input()` 等待用户输入 `yes`；输入不为 `yes` 时 `sys.exit(0)`；`--skip-disclaimer` 仅用于自动化测试
- 测试覆盖：通过人工验证三种路径（输入 yes / 输入 no / Ctrl+C）

---

## 第二轮：人工深度审查

以下 8 条是我在阅读 AI 生成的完整代码后，从安全视角提出的额外检查项。这些检查超出了原始 Prompt 的字面要求，关注的是 Prompt 覆盖不到的实现细节和架构决策。

**A. Cookie 在进程列表中的实际暴露面**

- 结果：通过
- 说明：三级优先级机制确保推荐路径（环境变量、配置文件）不经过命令行，进程列表中不会出现 Cookie。CLI 路径被保留但每次使用都打印警告。测试验证了 `monkeypatch.setenv` 场景下环境变量优先读取。

**B. 竞态条件的实际消除效果**

- 结果：通过
- 说明：`found_lock` 的 `with` 块同时保护了 `self.found` 的读写和 `result.txt` 的文件写入，消除了检测-设置之间的 TOCTOU 窗口。测试创建了多个独立 BruteForcer 实例确保锁之间互不干扰。

**C. 速率限制的下限保护**

- 结果：通过
- 说明：`validate_delay()` 拒绝负值，`--delay 0` 是允许的（裸奔模式）但需要用户显式指定。默认 0.1 秒的保守值确保"开箱即用"时不会无节制发包。

**D. 错误信息的适度性**

- 结果：通过
- 说明：校验失败时给出中文提示（如"URL 格式不合法"），不输出 Python 堆栈。日志文件则记录完整的异常类型和上下文，方便开发者排查。两层的区分是合理的。

**E. 报告中的隐私保护**

- 结果：通过
- 说明：JSON 和 HTML 报告均不包含 Cookie 字段。失败报告中的 `username` 和 `password` 字段设为 `null` 而非空字符串，语义更准确。测试验证了生成的 JSON 文件中不含 Cookie 相关内容。

**F. 日志文件的隐私与审计平衡**

- 结果：通过
- 说明：这是本次设计中一个有意的权衡——DEBUG 日志完整记录每次尝试的用户名和密码（明文），牺牲部分隐私来换取完整审计能力。这个选择本身是合理的（爆破工具的操作本身就涉及明文凭据的传输），但用户需要知道这一点。已在 README 和 `fix-report.md` 的剩余风险中说明。

**G. DVWA 等级适配的降级策略**

- 结果：通过
- 说明：high 等级下 CSRF token 提取使用正则匹配页面 HTML。如果 token 提取失败（页面结构不匹配），`_fetch_csrf_token()` 返回空字符串并打 warning 日志，不阻断后续爆破流程。这种降级策略在工具可用性和正确性之间取得了合适的平衡。

**H. 代码可维护性**

- 结果：通过
- 说明：所有公开函数有 docstring；安全相关常量集中在文件顶部（`REQUEST_TIMEOUT`、`MAX_THREADS`、`COOKIE_ENV_VAR` 等）；类的职责边界清晰（校验函数独立、报告生成独立、日志配置独立）。低耦合设计有利于后续的独立修改和测试。

---

## 测试结果汇总

**pytest 安全测试套件**

```bash
cd 成员代码/DVWA 暴力破解工具-何其杰
pytest tests/test_security.py -v
```

结果：`32 passed in 0.59s`，覆盖 7 个测试类。

**bandit 静态安全扫描**

```bash
python -m bandit -r dvwa_brute.py -f txt
```

结果：`No issues identified.`（High: 0, Medium: 0, Low: 0），693 行代码全部通过。

---

## 已知局限

以下风险在本轮加固中已识别但保留，属于工具定位和作业范围约束下的合理取舍：

- **日志中的明文凭据**：DEBUG 级日志记录完整用户名和密码，用于审计目的。生产环境中应配合日志加密或定期清理策略。当前依赖用户自行管理 `dvwa_brute.log` 的文件权限。
- **字典文件内容不受控**：工具不检查密码字典中是否包含恶意构造的超长字符串或特殊 Unicode 字符。这些内容会被原样发送，可能对目标 DVWA 产生非预期影响，但不会反噬工具本身。
- **High 等级 token 提取的脆弱性**：正则匹配依赖 DVWA 页面 HTML 的 `input[name=user_token]` 结构。如果 DVWA 更新版本改变了 HTML 布局，token 提取会静默失败并降级为无 token 模式。
- **并发日志写入**：多个 `dvwa_brute.py` 进程共用一个日志文件时，日志行可能交错。这是 Python `logging` 模块在多进程场景下的已知限制，非本工具独有。
- **TLS 证书验证**：工具使用 `requests` 库的默认 TLS 行为。如果 DVWA 使用自签名证书，需用户自行在代码中添加 `verify=False`（不推荐）或配置 CA bundle。
