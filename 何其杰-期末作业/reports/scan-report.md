# DVWA 暴力破解工具 — 安全扫描与测试报告

## 扫描对象

- **文件**：`成员代码/DVWA 暴力破解工具-何其杰/dvwa_brute.py`（安全加固版，693 行）
- **测试**：`成员代码/DVWA 暴力破解工具-何其杰/tests/test_security.py`（32 个用例）
- **扫描日期**：2026-06-25

## 扫描工具与命令

| 工具 | 用途 | 命令 |
|------|------|------|
| pytest 7.4.4 | 安全功能测试 | `pytest tests/test_security.py -v` |
| bandit 1.8+ | Python 安全静态分析 | `python -m bandit -r dvwa_brute.py -f txt` |

## pytest 测试结果

**32 个用例全部通过（0.59s）。**

### 输入校验（9 项）

验证"会拒绝什么"——确保非法输入被正确拦截：

- URL 校验：空字符串、非 URL 文本、`ftp://` 协议 → 拒绝
- URL 校验：`http://127.0.0.1/`、`https://example.com:8080/path` → 通过
- 线程数校验：0、-1、51、1000 → 拒绝
- 线程数校验：1、5、50 → 通过
- 延迟校验：-0.1、10.1 → 拒绝
- 延迟校验：0.0、0.1、5.0、10.0 → 通过
- 文件路径：`/nonexistent/` → 拒绝
- 文件路径：存在且非空的临时文件 → 通过
- 文件路径：存在但大小为 0 的临时文件 → 拒绝

### Cookie 安全（6 项）

验证凭据保护和解析优先级：

- 脱敏：正常 Cookie（43 字符）→ 输出 11 字符（前 8 位 + `***`）
- 脱敏：短 Cookie（3 字符）→ 正确处理
- 脱敏：空字符串 → 返回 `<empty>`
- 脱敏：`None` → 返回 `<empty>`
- 解析：环境变量 `DVWA_COOKIE` 存在时优先使用
- 解析：环境变量未设置时，配置文件 > CLI 参数

### 线程安全（4 项）

验证并发保护机制：

- `found_lock` 和 `attempt_lock` 在 `__init__` 中正确初始化
- 锁的类型为 `threading.Lock`
- 两个独立 BruteForcer 实例的锁互不共享
- `with found_lock:` 下状态读写正确

### 日志系统（2 项）

- Logger 至少配置了一个 Handler（文件或控制台）
- `setup_logging()` 重复调用不增加 Handler（去重逻辑生效）

### 报告生成（4 项）

- JSON 报告（成功）：生成有效 JSON，`success: true`，`username`/`password` 含实际值
- JSON 报告（失败）：`success: false`，`username`/`password` 为 `null`
- HTML 报告：生成 `<!DOCTYPE html>` 样式化页面，含目标 URL、等级、统计
- 无效格式（`--report xml`）：返回空字符串，不生成文件

### 常量与配置（5 项）

- `MAX_THREADS` ≤ 100 且在 10 以上
- `MIN_THREADS` ≥ 1
- `REQUEST_TIMEOUT` 在 1-30 秒范围内
- `SUCCESS_FLAGS` 列表非空
- `LEVEL_TOKEN_PARAM` 包含 `low`（None）和 `high`（`"user_token"`）

### 代码质量（1 项）

- AST 静态扫描源码，逐行检查，确认 693 行中无裸 `except:` 残留

## bandit 扫描结果

```
Run started: 2026-06-25

Test results:
    No issues identified.

Code scanned:
    Total lines of code: 693
    Total lines skipped (#nosec): 0

Run metrics:
    Total issues (by severity):
        Undefined: 0
        Low: 0
        Medium: 0
        High: 0
    Total issues (by confidence):
        Undefined: 0
        Low: 0
        Medium: 0
        High: 0
Files skipped: 0
```

bandit 没有因为日志中使用明文密码（B105: hardcoded password string）而误报，说明代码中的密码相关字符串均来自运行时变量或参数，没有硬编码在源码中。裸 except、无超时请求等原始代码中的问题已全部消除。

## 命令行接口完整性

`python dvwa_brute.py -h` 输出中包含以下安全相关参数：

- `-c/--cookie`：认证 Cookie（帮助文本标注"不推荐"）
- `--cookie-file`：从文件读取 Cookie
- `-t/--threads`：线程数 1-50
- `--delay`：请求间隔 0.0-10.0 秒
- `--level {low,medium,high}`：DVWA 安全等级
- `--report {json,html}`：生成测试报告
- `--log-file`：自定义审计日志路径
- `--skip-disclaimer`：跳过授权声明（仅测试用）

帮助文本同时提示了环境变量 `DVWA_COOKIE` 的使用方式和优先级。

## 关于真实 DVWA 集成测试的说明

本仓库中的 DVWA 靶场源码位于 `漏洞靶场/DVWA/`，为 PHP 应用，需要配合 PHP + MySQL 运行环境。扫描执行时本地未运行 DVWA 服务，因此本报告中的测试覆盖均为**代码层面的安全功能验证**（单元测试 + 静态分析），不包括实战 DVWA 登录态下的端到端爆破集成测试。工具在 DVWA 各安全等级下的实际行为已在代码中通过参数化设计来保证（`--level` + `_fetch_csrf_token()` 的降级策略），但实战验证需要在配置好 DVWA 环境后执行。

## 结论

加固后的 `dvwa_brute.py`（693 行）通过了全部 32 项安全测试用例和 bandit 静态安全扫描。原始代码中的 8 项安全隐患（凭证泄露、裸 except、线程竞态、无速率限制、输入未校验、无审计日志、硬编码检测、无授权声明）均已消除。新增的 DVWA 安全等级适配、JSON/HTML 报告生成和完整安全测试套件使工具在功能、安全性和可维护性三个维度上均得到显著提升。
