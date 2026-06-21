# AI 生成结果检查记录

## 检查范围

- `scanner/policy.py`：授权配置和 URL/DNS/IP 校验。
- `scanner/credentials.py`：Cookie 解析和请求头构造。
- `scanner/http_client.py`：重定向、代理、请求额度、速率和响应大小限制。
- `scanner/detector.py`：Payload 变异、基线采样、布尔差分和分级证据。
- `scanner/reporting.py`：报告脱敏与原子写入。
- `scanner/cli.py`：凭据入口、执行顺序和报告路径边界。

## 第一层：对照 Prompt 检查

1. 功能并非只有注释或文档：目标校验在 CLI 启动和 `SafeHttpClient.get` 中均实际调用。
2. Cookie 不存在明文 CLI 参数：命令行仅允许隐藏输入或环境变量。
3. 重定向安全约束已落实：`NoRedirectHandler` 使 3xx 返回安全中止。
4. 资源约束已落实：请求前检查额度，响应使用上限加一字节的有界读取。
5. 延时检测已默认关闭：需要配置与 CLI 双重授权。
6. 报告不包含 Cookie 与 Query 值：`ScanResult` 不接收凭据，目标只保留 Scheme、Host、Port 和 Path。

## 第二层：人工审查发现

### 问题 1：HTTPError 资源未显式释放

- **发现：** 重定向测试结束时出现 `ResourceWarning`。
- **风险：** 长时间扫描中可能积累未关闭的响应资源。
- **整改：** 在 `HTTPError` 分支使用 `finally` 显式调用 `exc.close()`。
- **复验：** 重定向测试通过，不再出现资源警告。

### 问题 2：IPv6 回环地址可能被误拒绝

- **发现：** 通用 `is_reserved` 检查可能将已授权的 `::1` 拒绝。
- **风险：** `localhost` 优先解析为 IPv6 时，合法的本地 DVWA 无法扫描。
- **整改：** 对明确在授权网段中的 loopback 地址优先放行，其他 reserved 地址仍拒绝。
- **复验：** 新增 IPv6 回环用例并通过。

### 问题 3：系统代理可能获取 Cookie

- **发现：** `urllib.request.build_opener` 默认读取 `HTTP_PROXY` 等环境配置。
- **风险：** 误配或恶意代理可能收到本地 DVWA 请求与 Cookie。
- **整改：** 显式使用 `ProxyHandler({})` 禁用环境代理。
- **复验：** 本地 HTTP 正常请求、重定向、大响应和额度测试全部通过。

### 问题 4：Query 和报告路径约束不足

- **发现：** 初始实现未限制 Query 名称/值长度与解码后控制字符；`--report-dir` 可指向个人作业外部。
- **风险：** 过长输入消耗资源，控制字符影响日志，外部路径可能覆盖非目标文件。
- **整改：** 限制 URL、Query 名称和值长度，拒绝控制字符；将报告路径限制在个人 `reports/` 内。
- **复验：** 新增编码换行 Query 拒绝测试，测试通过。

## 结论

AI 生成的初始实现完成了主要功能，但人工审查和动态测试仍发现了资源释放、IPv6 兼容性、代理信任边界和输出路径问题。上述问题已整改并通过针对性复验，证明安全审查并非仅形式化对照 Prompt。
