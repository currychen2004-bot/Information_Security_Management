# 安全扫描与测试报告

## 基本信息

- 验证日期：2026-06-21
- 验证模块：受控授权的 DVWA SQL 注入扫描器
- 验证范围：授权策略、Cookie 校验、HTTP 资源限制、SQLi 证据、报告脱敏
- 真实凭据：未使用、未记录

## 执行结果

| 类别 | 数量 | 结果 |
| --- | ---: | --- |
| Cookie 安全 | 4 | 全部通过 |
| 目标授权与 SSRF | 8 | 全部通过 |
| 检测与报告 | 4 | 全部通过 |
| 本地 HTTP 安全边界 | 4 | 全部通过 |
| **合计** | **20** | **全部通过** |

## 关键安全用例

- 公网主机不在授权白名单时被拒绝。
- 即使将配置网段误设为 `0.0.0.0/0`，公网 IP 仍被硬性策略拒绝。
- 云元数据地址 `169.254.169.254` 被拒绝。
- URL 内嵌用户名/密码、编码路径穿越、非 HTTP Scheme 被拒绝。
- Cookie CR/LF 请求头注入、非法片段和重复名称被拒绝。
- 恶意 HTTP 302 重定向到云元数据地址时，扫描器不跟随。
- 4096 字节响应在 1024 字节上限策略下被中止。
- 请求数超过配置额度时被中止。
- 测试标记 Cookie 和 Query 值均未进入 JSON/Markdown 报告。
- 伪造的可控漏洞响应能产生 SQL 报错与布尔差分两类证据。

## 命令行安全验证

使用公网目标调用 CLI，工具在发出网络请求前终止：

```text
[!] 安全中止: 目标主机不在授权白名单中。
```

进程退出码为 2，符合默认拒绝要求。

## 真实 DVWA 集成状态

检查仓库 Compose 配置后确认 DVWA 应运行在 `127.0.0.1:4280`，并已将 4280 加入授权端口。验证时 Docker 守护进程未运行，80、8080 和 4280 均无 DVWA 服务，因此本报告不声称已完成真实 DVWA 登录态扫描。


## DVWA 真实运行准备

### 1. 启动靶场

在仓库根目录执行：

```bash
docker compose -f "漏洞靶场/DVWA/compose.yml" up -d
```

然后访问 `http://127.0.0.1:4280/setup.php`，完成数据库初始化并登录 DVWA。

### 2. 设置安全级别

对比测试需要分别设置：

- `Low`：用于验证扫描器能够发现明显 SQL 注入迹象。
- `Impossible`：用于验证对参数化查询和 CSRF Token 的处理边界。

Cookie 应通过 `--prompt-cookie` 隐藏输入，不应粘贴到命令、报告或截图中。

## 场景一：DVWA Low 级别扫描

### 后端代码依据

Low 级别的 `source/low.php` 直接将 `id` 拼接到 SQL 语句：

```php
$id = $_REQUEST[ 'id' ];
$query = "SELECT first_name, last_name FROM users WHERE user_id = '$id';";
```

输入没有类型校验、转义或参数化处理。当扫描器在 `id=1` 后追加单引号时，最终 SQL 包含不闭合引号，MySQL 错误文本会直接返回页面。

### 执行命令

```bash
cd "刘佳仑-期末作业"
python3 -m scanner.cli --url "http://127.0.0.1:4280/vulnerabilities/sqli/?id=1&Submit=Submit" --prompt-cookie
```

### 预期终端结果

```text
[*] 已通过授权校验的目标: http://127.0.0.1:4280/vulnerabilities/sqli/
[*] 延时测试: 禁用
[*] 请求数: 9
[*] 可疑点: 1
[*] JSON 报告: <个人作业路径>/reports/generated/latest-scan.json
[*] Markdown 报告: <个人作业路径>/reports/generated/latest-scan.md
```

请求数为 9 的原因：

- 重复基线请求 2 次。
- `id` 参数的第一个报错 Payload 即命中，然后执行布尔真/假请求，共 3 次。
- `Submit` 参数不进入 SQL，两个报错 Payload 和两个布尔 Payload 均会执行，共 4 次。

### 预期生成报告

`latest-scan.md` 的关键内容预期如下，扫描编号、时间和耗时为运行时动态值：

```text
# 受控 SQL 注入扫描报告

- 脱敏目标: http://127.0.0.1:4280/vulnerabilities/sqli/
- 参数名: id, Submit
- 请求数: 9
- 延时测试: disabled
- 状态: 扫描完成

## 可疑点

| 参数 | 类型 | 置信度 | 证据 |
| id | sql-error-disclosure | high | 响应命中 2 个 SQL 报错特征。 |
```

具体命中数与 DVWA 所使用的数据库后端和错误文本有关。仓库默认使用 MySQL/MariaDB，其错误页预计同时命中通用 `SQL syntax` 和完整 `You have an error in your SQL syntax` 两个模式。

### 对结果的安全判断

- `id` 为高置信度可疑参数。
- 错误页暴露了数据库错误细节，同时证明用户输入影响了 SQL 语句结构。
- `Submit` 未产生可疑点，符合该参数只用于触发处理逻辑、不进入 SQL 查询的源码行为。
- 报告仍应表述为「高置信度可疑点」，最终结论需结合后端源码人工确认。

## 场景二：DVWA Impossible 级别扫描

### 后端代码依据

Impossible 级别实现了三项关键防护：

```php
checkToken( $_REQUEST[ 'user_token' ], $_SESSION[ 'session_token' ], 'index.php' );

if(is_numeric( $id )) {
    $id = intval ($id);
    $data = $db->prepare(
        'SELECT first_name, last_name FROM users WHERE user_id = (:id) LIMIT 1;'
    );
    $data->bindParam( ':id', $id, PDO::PARAM_INT );
}
```

- `is_numeric` 和 `intval` 将输入限制为数字。
- PDO 预编译与整数类型绑定防止输入改变 SQL 结构。
- 表单要求 CSRF Token，且 `generateSessionToken()` 会在每次页面请求后生成新 Token。

### 执行方式

从 Impossible 页面的隐藏字段获取当前 `user_token`，并在不展示真实值的前提下执行：

```bash
python3 -m scanner.cli --url "http://127.0.0.1:4280/vulnerabilities/sqli/?id=1&Submit=Submit&user_token=<CURRENT_TOKEN>" --prompt-cookie
```

### 预期终端结果

```text
[*] 已通过授权校验的目标: http://127.0.0.1:4280/vulnerabilities/sqli/
[*] 延时测试: 禁用
[*] 请求数: 2
[*] 可疑点: 0
[!] 扫描已安全中止: 安全策略已阻止 HTTP 重定向。
```

该结果的执行过程是：

1. 第一次基线请求使用有效 Token，DVWA 处理请求后立即轮换 Session Token。
2. 第二次基线请求仍使用 URL 中的旧 Token。
3. `checkToken` 判定 Token 无效，DVWA 返回到 `index.php` 的 302 重定向。
4. 扫描器的 `NoRedirectHandler` 不跟随重定向，将本次扫描标记为安全中止。

### 预期生成报告

```text
- 参数名: id, Submit, user_token
- 请求数: 2
- 状态: 安全中止

## 安全中止原因

安全策略已阻止 HTTP 重定向。

## 可疑点

未发现符合当前启发式规则的可疑点。该结果不代表目标绝对安全。
```

### 对结果的正确解释

`0` 个可疑点**不能解释为 Impossible 级别已被扫描器完整验证为安全**。扫描在 Payload 阶段之前就因 CSRF Token 轮换而中止，因此结果应归类为「未完成扫描」。

Impossible 级别不存在与 Low 相同的 SQL 注入风险，其根据来自人工源码审查：数字类型校验、`intval`、PDO 预编译和 `PDO::PARAM_INT` 绑定，而不是这次未完成的动态扫描。

## 其他 DVWA 安全级别的边界

| 级别 | 请求形式 | 当前扫描器支持情况 | 结论 |
| --- | --- | --- | --- |
| Low | GET Query | 支持 | 预期发现 `id` 的高置信度 SQL 报错证据 |
| Medium | POST 表单 | 不支持 | 不应使用当前 GET 扫描结果下结论 |
| High | 独立 Session 输入页 | 不完整支持 | 需要专门的会话流程适配 |
| Impossible | GET + 轮换 CSRF Token | 目标可校验，但扫描会安全中止 | 不能将 0 个可疑点当作完整安全证明 |

## Low 与 Impossible 结果对比

| 对比项 | Low | Impossible |
| --- | --- | --- |
| 用户输入进入 SQL 的方式 | 字符串直接拼接 | 整数校验后参数化绑定 |
| CSRF Token | 不要求 | 要求且每次请求轮换 |
| 预期请求数 | 9 | 2 |
| 预期扫描状态 | 扫描完成 | 安全中止 |
| 预期可疑点 | `id` 高置信度 SQL 报错 | 0，但不能作为安全结论 |
| 人工源码审查 | 存在 SQL 拼接 | 使用 PDO 预编译和整数绑定 |

## 真实运行后的证据保留要求

当 DVWA 实际启动后，应保留以下证据：

1. Docker Compose 中 DVWA 容器为运行状态的截图，截图不包含 Cookie。
2. DVWA Low 级别页面和扫描终端摘要截图。
3. `reports/generated/latest-scan.md` 中脱敏的 Low 扫描结果。
4. DVWA Impossible 级别页面和「重定向被阻止」终端摘要截图。
5. Impossible 后端使用整数校验和参数化查询的人工审查记录。

截图或报告在提交前必须检查是否包含 `PHPSESSID`、`security` Cookie 值或 `user_token` 值。

## 结论

已通过 20 项自动化用例确认主要安全约束落实在代码逻辑中。基于 DVWA 源码与扫描器规则的对照，Low 级别在真实运行时预期产生 `id` 参数的高置信度 SQL 报错证据；Impossible 级别则会因 CSRF Token 轮换触发重定向阻断，属于未完成扫描，必须结合参数化查询源码完成人工判断。

这一对比同时说明了工具的能力与边界：安全扫描报告既要记录发现的问题，也要明确未完成的检测和不能由动态结果支持的结论。
