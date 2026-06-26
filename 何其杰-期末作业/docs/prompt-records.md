# Prompt 与 AI 协作记录

## 对话一：让 AI 审查现有代码的安全问题

### 我的 Prompt

> 我计划对现有 DVWA 暴力破解脚本 `dvwa_brute.py` 进行安全加固。先仔细阅读代码，针对工具自身的滥用风险和代码质量问题进行审查。请先不修改代码，从凭证保护、异常处理、线程安全、速率限制、输入校验、审计日志等方面考虑，并指出现有实现中的具体代码位置和问题。

### AI 的回答摘要

AI 读完代码（169 行）后指出了七个问题：

1. Cookie 通过命令行明文泄露：Cookie 仅通过 `-c` 命令行参数明文传入，会留在进程列表和 Shell 历史记录中。
2. 两处裸 except：第 57 行和第 97 行用了裸 `except:`，连 `KeyboardInterrupt` 都吞掉了，而且网络报错完全看不到原因。
3. `self.found` 在多线程中没有锁保护，多个线程同时命中时可能重复写入 `result.txt`。
4. 无任何速率限制：线程间隔只写了 0.05 秒，5 线程差不多每秒 100 个请求，没有限速手段。
5. 外部输入零校验：URL、线程数、字典文件路径都没做校验，传负数线程或不存在的路径就直接崩。
6. 无审计日志：所有输出只到控制台，没有日志文件，事后无法追溯操作记录。
7. 硬编码检测字符串 + 无授权声明：成功/失败标志硬编码为英文 DVWA 界面文本，换个语言就检测不到了；工具启动也没有授权提示。

---

## 对话二：把风险转化成约束，让 AI 撰写文档

### 我的 Prompt

> 基于刚才识别出的七个问题，现在需要把它们转化为可执行的安全约束和改造方案。请完成两件事：第一，输出 constraint-doc.md（包含背景说明、任务范围、安全约束、禁止行为、验收条件）和 risk-analysis.md（包含选定模块、涉及的敏感操作、主要安全风险、安全目标）；第二，给出每个安全点的具体改造方案，包括新增哪些函数、修改哪些类、参数如何设计。以上内容先不要写代码，给出文档和设计方案。

### AI 的回答摘要

AI 针对七个风险逐一给出了具体约束和改造方案：

**Cookie 管理**：引入三级读取优先级——环境变量 `DVWA_COOKIE` → `--cookie-file` 配置文件 → `-c` 命令行参数。使用 `-c` 方式时打印安全警告。日志中 Cookie 必须脱敏（截取前几位后追加占位符）。对应新增 `resolve_cookie()` 和 `sanitize_cookie_for_log()` 两个函数。

**异常处理**：所有裸 `except:` 替换为具体异常类型。文件 I/O 区分 `FileNotFoundError` / `PermissionError` / `OSError`；网络请求区分 `ConnectionError` / `Timeout` / `RequestException`；队列操作使用 `queue.Empty`。每个异常分支记录包含上下文的日志。

**线程安全**：`self.found` 和尝试计数器分别使用 `threading.Lock` 保护，在 `with` 块内完成读写，消除 TOCTOU 窗口。

**速率与资源控制**：新增 `--delay` 参数（默认 0.1 秒，范围 0.0-10.0 秒），每次请求后等待。线程数通过 `-t` 指定，限制 1-50。对应新增 `validate_delay()` 和 `validate_threads()` 校验函数。

**输入校验**：所有外部输入在进入业务逻辑前校验——URL 格式（正则 `^https?://`）、线程数范围、延迟范围、字典文件存在且非空。校验失败输出中文错误信息并 `sys.exit(1)`。对应新增 `validate_url()` 和 `validate_file_path()`。

**审计日志**：用 `logging` 模块替代 `print`。控制台 INFO 级别，文件 DEBUG 级别（含每次尝试的用户名和密码用于审计追踪）。日志格式含时间戳、级别和线程名。支持 `--log-file` 自定义路径。对应新增 `setup_logging()`。

**合规授权**：新增 `show_disclaimer()`，启动时展示授权声明并要求输入 `yes` 确认。提供 `--skip-disclaimer` 用于自动化测试。

**DVWA 等级适配与报告**：新增 `--level` 参数支持 low / medium / high，high 等级自动从页面提取 `user_token` 作为 CSRF token（新增 `_fetch_csrf_token()` 方法）。新增 `--report` 参数支持 JSON / HTML 格式报告输出（新增 `generate_report()`），报告不含 Cookie 信息。

AI 同时产出了完整的 `risk-analysis.md` 和 `constraint-doc.md`。


## 对话三：开始撰写代码

### 我的 Prompt

> 按照确认后的方案开始实现。保留原始代码的 BruteForcer 类 + queue.Queue + daemon 线程的核心架构。每完成一个安全控制点，说明它对应的代码位置和执行路径。编写安全测试时覆盖两个方向：验证合法输入被正确放行，以及验证非法输入和危险行为被正确拒绝。测试代码中不使用真实 Cookie 或面向真实目标的字典，不为了通过测试而增加绕过开关。

### AI 生成的几个关键实现

已完成全部代码实现（693 行）和 32 个安全测试用例。各安全控制点的代码位置和执行路径如下：

**Cookie 三级优先级解析** — `resolve_cookie()`，在 `main()` 中参数校验之后、实例化 BruteForcer 之前调用：

```python
def resolve_cookie(cli_cookie=None, cookie_file=None):
    env_cookie = os.getenv("DVWA_COOKIE")
    if env_cookie:
        logger.info("Cookie 来源: 环境变量 DVWA_COOKIE")
        return env_cookie
    if cookie_file:
        with open(cookie_file, "r", encoding="utf-8") as f:
            file_cookie = f.read().strip()
        if file_cookie:
            logger.info("Cookie 来源: 配置文件 %s", cookie_file)
            return file_cookie
    if cli_cookie:
        logger.warning("Cookie 来源: 命令行参数（不推荐）。建议使用环境变量 DVWA_COOKIE 或 --cookie-file。")
        return cli_cookie
    logger.critical("未提供 Cookie。请通过环境变量 DVWA_COOKIE、--cookie-file 或 -c 提供。")
    sys.exit(1)
```

**Cookie 日志脱敏** — `sanitize_cookie_for_log()`，在 `BruteForcer.__init__()` 记录初始化日志时调用，截取前 8 字符后追加 `***`：

```python
def sanitize_cookie_for_log(cookie: str) -> str:
    if not cookie:
        return "<empty>"
    if len(cookie) <= 8:
        return cookie[:4] + "***"
    return cookie[:8] + "***"
```

**线程安全的命中处理** — `worker()` 中，检测到成功标志后进入 `with self.found_lock` 临界区，在锁内二次检查 `if not self.found` 消除 TOCTOU 窗口，确保多个线程同时命中时只写入一次结果文件：

```python
if hit:
    with self.found_lock:
        if not self.found:
            self.found = True
            self.found_user = user
            self.found_pass = pwd
            print("\n破解成功！")
            print("user:", user)
            print("password:", pwd)
            with open(RESULT_FILE, "w", encoding="utf-8") as f:
                f.write(f"username:{user}\npassword:{pwd}\n")
            logger.info("结果已写入 %s | user=%s", RESULT_FILE, user)
    self.q.task_done()
    break
```

**多语言检测标志** — 模块顶部常量，同时覆盖英文和中文 DVWA 界面：

```python
SUCCESS_FLAGS = [
    "Welcome to the password protected area",   # DVWA 英文界面
    "欢迎进入密码保护区域",                       # DVWA 中文界面
]
```

**授权声明** — `show_disclaimer()`，在 `main()` 中校验通过后、发起任何网络请求前调用，打印带 Unicode 边框的完整授权条款，要求输入 `yes` 确认：

```python
def show_disclaimer() -> bool:
    print(disclaimer)  # 带边框的授权条款文本
    try:
        answer = input("请输入 'yes' 确认您已获得授权: ").strip()
        if answer.lower() == "yes":
            logger.info("用户已确认授权声明")
            return True
        else:
            logger.warning("用户拒绝授权声明，程序退出")
            return False
    except (EOFError, KeyboardInterrupt):
        print("\n程序已取消。")
        return False
```

**输入校验链** — `main()` 中在 Cookie 解析之前依次执行，每个校验失败输出中文错误信息后 `sys.exit(1)`：

```python
if not validate_url(args.url):
    print("错误：URL 格式不合法，必须以 http:// 或 https:// 开头。")
    sys.exit(1)
if not validate_threads(args.threads):
    print(f"错误：线程数必须在 {MIN_THREADS}-{MAX_THREADS} 之间。")
    sys.exit(1)
if not validate_delay(args.delay):
    print("错误：请求间隔必须在 0.0-10.0 秒之间。")
    sys.exit(1)
if not validate_file_path(args.wordlist):
    print(f"错误：密码字典文件不存在或为空: {args.wordlist}")
    sys.exit(1)
```

**DVWA 等级适配** — `_fetch_csrf_token()`，仅在 `--level high` 时由 `worker()` 调用，从 DVWA 页面 HTML 中正则提取 `user_token`。提取失败时降级为无 token 请求，通过 `logger.warning()` 通知用户：

```python
def _fetch_csrf_token(self) -> str:
    try:
        r = requests.get(self.url, headers=self.headers, timeout=REQUEST_TIMEOUT)
        match = re.search(
            r'<input\s+type=[\'"]hidden[\'"]\s+name=[\'"]user_token[\'"]\s+value=[\'"]([^\'"]+)[\'"]',
            r.text,
        )
        if match:
            return match.group(1)
        else:
            logger.warning("未能从页面提取 user_token，降级为无 token 请求")
            return ""
    except requests.RequestException as e:
        logger.error("获取 CSRF token 失败: %s", e)
        return ""
```

**安全测试** — `tests/test_security.py`，32 个用例覆盖 7 个方面：输入校验（9 项，验证合法输入放行和非法输入拒绝）、Cookie 安全（6 项，脱敏正确性和三级解析优先级）、线程安全（4 项，锁存在、类型正确、实例独立、锁保护读写）、日志系统（2 项）、报告生成（4 项，JSON 成功/失败、HTML 生成、无效格式拒绝）、常量配置（5 项）、无裸 except 检查（1 项，AST 静态扫描源码）。测试中未使用任何真实 Cookie 或密码字典。

### 审查初步结论

上述安全控制均进入真实执行路径。Cookie 优先级在 `main()` 的参数处理阶段执行，锁保护在 `worker()` 的热路径中每次命中都会触发，校验链在发起网络请求前拦截所有非法输入，授权声明在 `main()` 启动阶段阻塞等待用户确认——没有一项是仅存在于注释中的。

---

## 对话四：跑测试发现三个问题

### 问题一：日志 handler 重复添加

**我的 Prompt：**

> 测试运行时发现一个问题：模块导入时已经执行了 `logger = setup_logging()`，测试中再次调用 `setup_logging("dvwa_brute_test.log")` 会导致 FileHandler 重复添加。请在 `setup_logging()` 中增加去重判断，确保同一 logger 的 handler 不会重复注册，并补充对应的测试用例验证去重行为。

**AI 的修改：** 在 `setup_logging()` 开头加了 `if logger.handlers: return logger`，测试类里补了 `test_logger_setup_idempotent`。跑完 32 个全过。


### 问题二：medium 等级和 low 一样

**我的 Prompt：**

> `LEVEL_TOKEN_PARAM` 中 medium 和 low 的值均为 None，代码层面两者完全等价。DVWA medium 等级在后端逻辑上与 low 相同（仅前端通过 sleep 增加延时），请确认这种设计是预期行为，并在代码注释和 README 中说明 medium 等级建议配合较大的 `--delay` 值使用。

**AI 的确认：** 对，DVWA medium 只是前端 `sleep(2)` 拖时间，后端收到的还是普通 GET 请求，没有 token。工具直接走后端请求，所以 low 和 medium 请求构造一样。加了注释说明，README 里也写了 medium 建议配大一点的 `--delay`。

---

## 对话五：最终验证

### 我的 Prompt

> 请进行最终验证，逐项列出实际结果而非仅给出结论。验证范围包括：输入校验各函数对合法与非法输入的拒绝/放行情况、Cookie 三级解析优先级的正确性、线程锁的存在性与独立性、报告生成功能的正确性与隐私保护（报告中不应出现 Cookie）、源码中裸 except 的静态扫描结果、bandit 安全审计输出、以及 `--help` 参数的完整性。如果真实 DVWA 集成测试因环境未运行而无法执行，必须在报告中明确标注，不得推测或编造测试数据。

### 验证结果

- **pytest**：32 个全过，0.59s。覆盖输入校验（9）、Cookie 安全（6）、线程安全（4）、日志（2）、报告（4）、常量（5）、裸 except 扫描（1）。
- **bandit**：693 行代码，No issues identified，High/Medium/Low 全是 0。
- **--help**：`--cookie-file`、`--delay`、`--level`、`--report`、`--log-file`、`--skip-disclaimer` 都在，环境变量 `DVWA_COOKIE` 的说明也有。
- **代码量**：169 行 → 693 行，增加的部分主要是校验逻辑、日志系统、授权模块、报告生成和测试。
- **真实 DVWA**：仓库里有源码但没有 PHP+MySQL 环境，没做端到端爆破集成测试。在 `scan-report.md` 里如实写了。

### 我的总结

在本次让AI协作开发的过程中，我先让 AI 读原代码找风险（对应第一步风险识别），然后把风险变成约束让它写文档做方案（第二步约束表达），方案我审查完提了三个问题后才让它动代码。代码出来以后跑测试发现 handler 重复和路径的问题又让它修改（第三步审查 + 第四步整改），最后 bandit 和 pytest 双重验证确认没有问题（第五步验证）。完成了风险的判断、约束的优先级、方案的取舍和测试结果等安全管理环节。
