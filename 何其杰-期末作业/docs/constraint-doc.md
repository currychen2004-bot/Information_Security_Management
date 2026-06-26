# DVWA 暴力破解工具 — AI 协作约束说明

## 项目背景

修改对象：`成员代码/DVWA 暴力破解工具-何其杰/dvwa_brute.py`，原始 169 行，多线程 GET 型暴力破解脚本，面向本地 DVWA 靶场的 Brute Force 模块。

改造方向：不是重写新工具，而是在保留原有 `BruteForcer` 类 + `queue.Queue` + daemon 线程架构的基础上，对这个工具自身的安全性做加固，并新增 DVWA 安全等级适配与测试报告功能。

## 任务范围

- 对 `dvwa_brute.py` 进行安全加固，修复已识别出的 7 项安全隐患。
- 新增 Cookie 安全读取机制（环境变量 / 配置文件 / CLI 三级优先级）。
- 新增输入校验逻辑（URL 格式、线程数范围、延迟范围、文件存在性及非空）。
- 新增请求速率限制与线程安全锁保护。
- 引入 logging 模块替代 print，实现审计日志双通道输出。
- 新增启动授权声明，要求用户确认已获得测试授权。
- 新增 DVWA 安全等级适配（low / medium / high）与 CSRF token 自动处理。
- 新增 JSON / HTML 格式测试报告生成功能。
- 编写安全测试用例，覆盖输入校验、Cookie 安全、线程安全、报告生成等模块。
- 更新 README 及 docs/、reports/ 下的过程文档。

## 必须遵守的安全约束

以下规则在 Prompt 中以结构化方式传递给 AI（见 `prompt-records.md` 对话二），同时也是人工审查时的检查标准（见 `security-checklist.md`）。

### 凭据管理

- Cookie 的读取优先级：环境变量 `DVWA_COOKIE` > `--cookie-file` 指定的文件 > `-c` 命令行参数。
- 如果用户使用 `-c` 方式传 Cookie，程序必须打印安全警告，提醒用户这种方式不推荐。
- 写入日志文件的 Cookie 必须脱敏，无论原始长度多少，只保留前 8 个字符后追加 `***`。
- 测试代码、README 示例、提交历史中不得出现任何真实有效的 Cookie 或密码。

### 异常与错误处理

- 代码中不允许出现裸 `except:`。所有异常捕获必须指定具体类型。
- 文件操作至少要区分 `FileNotFoundError`、`PermissionError`、`OSError`。
- 网络操作至少要区分 `requests.ConnectionError`、`requests.Timeout`、`requests.RequestException`。
- 每个异常分支必须输出包含上下文信息（哪个文件、哪个 URL、哪个用户/密码组合）的日志。

### 并发与资源控制

- `self.found` 和尝试计数器的读写必须用 `threading.Lock` 保护。
- 每次 HTTP 请求必须带 `timeout` 参数，默认不超过 10 秒。
- 每次请求完成后必须按 `--delay` 参数等待（默认 0.1 秒，允许范围 0.0-10.0 秒）。
- 线程数允许范围 1-50，拒绝超出范围的值。

### 输入边界

- URL 必须匹配 `http://` 或 `https://` 开头的基本格式，不合法则拒绝并给出明确提示。
- 字典文件路径必须验证：存在、是文件、大小大于 0 字节。
- 所有校验失败时，程序给出中文提示后退出，不抛 Python 堆栈跟踪。

### 合规与审计

- 程序启动后、执行爆破之前，必须打印授权声明并要求用户输入 `yes` 确认。
- 审计日志文件默认名为 `dvwa_brute.log`，可通过 `--log-file` 自定义路径。
- 日志级别：控制台输出 INFO 及以上，文件记录 DEBUG 及以上（含每次尝试的具体用户名和密码，用于完整审计追踪）。

## 明确的红线

这些行为在任何情况下都不允许：

- 不允许裸 `except:`（重申，因为这是最容易在 AI 生成代码中出现的模式）
- 不允许不设速率上限的发包逻辑——即使 `--delay` 设为 0，也要有 `validate_delay()` 的 0.0-10.0 范围约束
- 不允许在日志、报告或 stdout 中输出完整 Cookie 原文
- 不允许将 `.env`、含真实凭据的配置文件提交到 Git
- 不允许在测试用例中使用真实的 Cookie 或面向真实目标的密码字典

## 如何验证

以下条件用于判断 AI 生成的代码是否真正落实了约束（而不是只在注释里提一句）：

1. 执行 `python dvwa_brute.py -h`，输出中包含 `--cookie-file`、`--delay`、`--level`、`--report`、`--log-file`、`--skip-disclaimer`。
2. 设置环境变量 `DVWA_COOKIE=test123` 后运行工具（不带 `-c`），日志中应显示"Cookie 来源: 环境变量"。
3. 传入 `-u "ftp://bad.com"` 时，程序拒绝并退出，不发起任何网络请求。
4. 传入 `-t 0` 或 `-t 999` 时，程序拒绝并提示合法范围是 1-50。
5. 审计日志文件中搜索完整 Cookie 值，不应命中。
6. 运行 `pytest tests/test_security.py -v`，全部 32 个用例通过。
7. 运行 `bandit -r dvwa_brute.py`，0 个告警。
