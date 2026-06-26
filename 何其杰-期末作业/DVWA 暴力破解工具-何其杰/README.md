### DVWA Brute Force多线程暴力破解 — 安全加固版
何其杰 2022212887

### 1. 工具定位

这是一个针对 DVWA Brute Force模块开发的自动化暴力破解测试工具，目标是：

- 通过多线程提高爆破效率
- 支持单用户名定向爆破或用户名字典组合爆破
- 自动识别并保存破解成功的账号密码
- **（安全加固版新增）** 凭证安全管理、审计日志、速率限制、安全等级适配、结果报告生成

> ⚠️ **警告**：本工具仅限在已获授权的 DVWA 靶场环境中使用。未经授权对非自有系统使用本工具属于违法行为。启动时需输入 `yes` 确认已获得授权。

### 2. 文件说明

- `dvwa_brute.py`：主程序脚本（安全加固版，693 行）
- `username.txt`：可选，用于多用户爆破模式的用户名列表
- `password.txt`：必需，密码字典文件
- `result.txt`：输出文件，自动记录破解成功获取到的用户名和密码
- `dvwa_brute.log`：审计日志文件，记录所有操作详情（Cookie 已脱敏）
- `tests/test_security.py`：安全测试用例（32 个）
- `report_*.json` / `report_*.html`：测试结果报告（可选生成）

### 3. 安全加固内容（作业三）

相比原始版本（169 行），安全加固版（693 行）新增以下安全机制：

| 安全改进 | 说明 |
|---------|------|
| Cookie 安全读取 | 支持环境变量 `DVWA_COOKIE`、`--cookie-file` 配置文件、`-c` CLI 参数三级优先级，推荐前两种方式 |
| 异常分类处理 | 全部裸 `except:` 替换为具体异常类型（`requests.ConnectionError`/`requests.Timeout`/`FileNotFoundError` 等） |
| 线程安全锁 | `threading.Lock` 保护 `self.found` 和 `self.total_attempts` 共享状态 |
| 速率限制 | `--delay` 参数（默认 0.1 秒），可配置 0.0-10.0 秒 |
| 输入校验 | URL 格式、线程数（1-50）、延迟范围（0.0-10.0）、文件存在性/非空四层校验 |
| 审计日志 | `logging` 模块双通道输出，Cookie 脱敏（只保留前 8 字符） |
| 授权声明 | 启动时显示授权条款，要求输入 `yes` 确认 |
| 多语言检测 | 同时支持 DVWA 英文和中文界面的成功/失败标志 |
| 安全等级适配 | `--level low/medium/high`，high 等级自动携带 CSRF token |
| 结果报告 | `--report json/html` 生成结构化或可视化测试报告 |

### 4. 爆破逻辑

脚本采用多线程并发模式，核心流程如下：

- **授权确认**：启动时显示授权声明，需输入 `yes` 确认。
- **输入校验**：校验 URL 格式、线程数范围、字典文件有效性，不合法则明确报错退出。
- **任务组合逻辑**：
  - 若通过参数传入单个用户名，则进行"1对多"爆破。
  - 若未传入用户名，脚本自动读取 `username.txt`，进行"多对多"组合爆破。
- **安全等级适配**：
  - Low/Medium：GET 请求直接发送。
  - High：先获取页面 CSRF token（`user_token`），再携带 token 发送请求。
- **速率控制**：每次请求后按 `--delay` 设置的间隔等待，防止无节制发包。
- **特征匹配**：实时监控响应正文，命中成功标志（支持中英文）则判定破解成功。
- **线程安全**：使用锁保护共享状态，多线程同时命中时只写入一次结果文件。
- **审计日志**：所有操作（含每次尝试的用户名和密码）记录到 `dvwa_brute.log`。

### 5. 使用前准备

1. 启动 DVWA 环境
2. 登录账户，将 Security Level设置为目标等级（Low/Medium/High）
3. 点击左侧菜单进入 Brute Force页面
4. **推荐方式**：将浏览器 Cookie 设置为环境变量：
   ```sh
   export DVWA_COOKIE="PHPSESSID=xxx; security=low"
   ```
   或保存到文件：
   ```sh
   echo "PHPSESSID=xxx; security=low" > cookie.txt
   ```

### 6. 运行示例

在当前目录下执行命令：

**模式 A：单用户爆破（使用环境变量 Cookie）**

```sh
export DVWA_COOKIE="PHPSESSID=xxx; security=low"
python dvwa_brute.py -u "http://127.0.0.1/dvwa/vulnerabilities/brute/" -user "admin" -w "password.txt" --level low
```

**模式 B：多用户爆破（使用配置文件 Cookie）**

```sh
python dvwa_brute.py -u "http://127.0.0.1/dvwa/vulnerabilities/brute/" --cookie-file cookie.txt -user "username.txt" -w "password.txt" --level medium --delay 0.5
```

**模式 C：High 安全等级 + HTML 报告**

```sh
python dvwa_brute.py -u "http://127.0.0.1/dvwa/vulnerabilities/brute/" --cookie-file cookie.txt -user "admin" -w "password.txt" --level high -t 3 --delay 1.0 --report html
```

**安全加固版新增参数：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-c, --cookie` | 认证 Cookie（不推荐，建议用环境变量） | — |
| `--cookie-file` | 从文件读取 Cookie | — |
| `--delay` | 每次请求间隔秒数（0.0-10.0） | 0.1 |
| `--level` | DVWA 安全等级（low/medium/high） | low |
| `--report` | 生成报告格式（json/html） | 不生成 |
| `--log-file` | 审计日志文件路径 | dvwa_brute.log |
| `--skip-disclaimer` | 跳过授权声明（仅自动化测试） | 不跳过 |
| `-t, --threads` | 并发线程数（1-50） | 5 |

### 7. 输出结果说明

- **控制台输出**：
  - `破解成功！`：在屏幕上显示用户名和密码。
  - `破解失败！`：字典尝试完毕仍未命中。
  - 同时打印耗时和总尝试次数统计。

- **文件记录**：
  破解成功后，结果写入 `result.txt`。

- **审计日志**：
  所有操作详情记录在 `dvwa_brute.log`，包含时间戳、线程名、日志级别和消息。可通过 `--log-file` 自定义路径。

- **测试报告**（可选）：
  - `--report json`：生成 `report_YYYYMMDD_HHMMSS.json`，包含目标 URL、安全等级、成功状态、尝试次数、耗时等结构化数据。
  - `--report html`：生成 `report_YYYYMMDD_HHMMSS.html`，可视化展示测试结果。

### 8. 安全测试

运行安全测试套件：

```sh
pytest tests/test_security.py -v
```

覆盖 32 个测试用例：输入校验（9）、Cookie 安全（6）、线程安全（4）、日志系统（2）、报告生成（4）、常量配置（5）、无裸 except 检查（1）。

### 9. 局限性

- **难度限制**：支持 Low/Medium/High 三级。Impossible 等级使用了账号锁定机制，不在本工具测试范围内。
- **网络依赖**：若线程数设置过高且靶场响应慢，可能导致请求丢包，建议根据实际响应速度调整 `-t` 和 `--delay` 参数。
- **Token 提取**：High 等级的 CSRF token 通过正则匹配页面 HTML 提取，如果 DVWA 版本差异导致 HTML 结构变化，token 提取可能失败（此时会自动降级为无 token 请求并记录日志）。
- **日志隐私**：审计日志以明文记录尝试的用户名和密码，用于完整的审计追踪。建议测试完成后及时清理或妥善保管日志文件。
