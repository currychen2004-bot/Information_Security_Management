# DVWA 暴力破解工具 — 安全加固前后对比

## 总览

| 维度 | 加固前 | 加固后 |
|------|--------|--------|
| 代码规模 | 169 行 | 693 行 |
| 安全测试 | 无 | 32 个用例，7 个测试类 |
| bandit 扫描 | 未执行（预测有裸 except 等告警） | 0 告警（High/Medium/Low 均为 0） |
| 安全控制点 | 0 | 10 项（详见下方） |

## 逐项对比

### Cookie 管理

**之前：** 仅通过 `-c` 命令行参数传入，直接赋值给 `self.headers = {"Cookie": cookie}`。进程列表可见完整凭据，Shell 历史永久保留。

**之后：** 三级读取优先级（环境变量 `DVWA_COOKIE` → `--cookie-file` 文件 → `-c` 参数），推荐方式不经过命令行。写入日志时自动脱敏为 `前8字符***`。报告文件不含 Cookie 字段。

### 异常处理

**之前：** 第 57 行和第 97 行两处裸 `except:`。按 Ctrl+C 无法退出。网络故障静默吞没，用户完全不知道请求在大量失败。

**之后：** 全部替换为具体异常类型（`FileNotFoundError` / `PermissionError` / `OSError` 用于 I/O，`ConnectionError` / `Timeout` / `RequestException` 用于网络，`queue.Empty` 用于队列）。每个异常分支记录包含上下文的日志。新增 AST 静态扫描测试防止裸 `except:` 在未来重新出现。

### 线程安全

**之前：** `self.found` 无锁保护。多线程同时命中时可能重复写 `result.txt`、重复打印成功信息、`task_done()` 计数错乱。

**之后：** `self.found_lock` 保护破解状态和结果写入，`self.attempt_lock` 保护尝试计数。worker 中使用双重检测模式（`with found_lock:` 内二次 `if not self.found:`），消除 TOCTOU 窗口。

### 速率控制

**之前：** 请求间仅间隔 `THREAD_SLEEP_INTERVAL = 0.05` 秒（这是线程轮询间隔，不是速率限制）。5 线程有效 QPS 约 50-100，无任何可配置的限速手段。

**之后：** `--delay` 参数控制每次请求后的等待时间（默认 0.1 秒，范围 0.0-10.0 秒）。`validate_delay()` 拒绝负值。默认值下 5 线程约 50 QPS，用户可根据目标承受能力和授权范围灵活调整。

### 输入校验

**之前：** 零校验。URL 可以是任意字符串，线程数可以是负数，字典文件路径可以不检查就直接打开。

**之后：** `validate_url()` 正则检查 HTTP/HTTPS 格式，`validate_threads()` 限制 1-50，`validate_delay()` 限制 0.0-10.0，`validate_file_path()` 检查存在+是文件+非空。四个校验在 `main()` 中在发起任何网络请求之前串联执行，失败即给出中文提示并退出。

### 审计能力

**之前：** 只有 `print()` 到控制台。进程结束后无任何记录留存。

**之后：** `logging` 模块双通道输出。控制台 INFO 级别显示关键事件（启动、成功/失败、统计）。文件 DEBUG 级别记录完整操作详情（时间戳、线程名、每次尝试的用户名和密码）。Cookie 在日志中脱敏。日志路径可通过 `--log-file` 自定义。

### 检测灵活性

**之前：** `SUCCESS_FLAG = "Welcome to the password protected area"` 硬编码单个英文字符串。

**之后：** `SUCCESS_FLAGS` 和 `FAIL_FLAGS` 为列表，同时预置英文和中文 DVWA 界面的对应文本。`BruteForcer.__init__()` 接受 `success_flags` 和 `fail_flags` 可选参数允许用户注入自定义标志。

### DVWA 等级支持

**之前：** 仅支持 Low 等级（GET 请求无 token）。

**之后：** `--level low/medium/high` 三级。High 等级下 `_fetch_csrf_token()` 先从页面提取 `user_token`，构造请求时一并发送。提取失败时自动降级并记录 warning。

### 合规授权

**之前：** 无。工具启动即执行。

**之后：** `show_disclaimer()` 打印带边框授权条款，要求输入 `yes` 确认。输入其他内容或 Ctrl+C 则退出。`--skip-disclaimer` 仅用于 pytest 自动化测试。

### 测试报告

**之前：** 无。

**之后：** `--report json` 生成结构化 JSON（含时间、目标、等级、成功状态、统计数字）。`--report html` 生成带 CSS 样式的可视化页面。失败报告密码字段为 null。报告不包含 Cookie。

## 新增代码清单

| 类别 | 函数/属性 | 用途 |
|------|----------|------|
| Cookie | `resolve_cookie()` | 三级优先级解析 |
| Cookie | `sanitize_cookie_for_log()` | 日志脱敏 |
| 校验 | `validate_url()` | URL 格式 |
| 校验 | `validate_threads()` | 线程数范围 |
| 校验 | `validate_delay()` | 延迟范围 |
| 校验 | `validate_file_path()` | 文件有效性 |
| 授权 | `show_disclaimer()` | 启动授权确认 |
| 日志 | `setup_logging()` | 双通道日志配置 |
| 报告 | `generate_report()` | JSON/HTML 报告 |
| 并发 | `BruteForcer.found_lock` | 破解状态保护 |
| 并发 | `BruteForcer.attempt_lock` | 计数器保护 |
| 适配 | `BruteForcer._fetch_csrf_token()` | High 等级 token |
| 测试 | `tests/test_security.py` | 32 个安全用例 |

## 验证结果

```bash
# 安全测试
$ pytest tests/test_security.py -v
32 passed in 0.59s

# 静态扫描
$ python -m bandit -r dvwa_brute.py -f txt
No issues identified. (High: 0, Medium: 0, Low: 0)
```
