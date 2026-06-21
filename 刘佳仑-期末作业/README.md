# 受控授权的 DVWA SQL 注入扫描器

本项目是刘佳仑的「AI 辅助开发过程中的安全管理实践」期末作业，基于现有的 `成员代码/DVWA SQL 注入简易扫描工具-刘佳仑/` 进行实质性安全加固。

## 改造内容

- 通过 JSON 授权策略限制主机、IP 网段、端口和路径。
- 拒绝公网、云元数据地址、URL 内嵌凭据和越界路径。
- 禁止自动重定向和环境 HTTP 代理，避免请求与 Cookie 离开靶场边界。
- Cookie 仅通过隐藏输入或环境变量读取，并防止请求头注入。
- 限制请求数、请求速率、超时、参数数量和响应体大小。
- 使用 SQL 报错与布尔真假差分生成分级证据；延时检测需要双重授权。
- 生成不包含 Cookie、Query 值和原始响应的 JSON/Markdown 报告。

## 目录结构

```text
刘佳仑-期末作业/
├── scanner/       # 扫描器实现
├── tests/         # 自动化安全测试
├── config/        # 授权范围配置
├── docs/          # 风险、Prompt、审查与整改记录
└── reports/       # 测试报告与前后对比
```

## 运行条件

- Python 3.10 或更高版本。
- 仓库内的 DVWA 通过 Docker Compose 启动。
- 仅对本地课程靶场或明确获得授权的目标执行测试。

## 启动 DVWA

在仓库根目录执行：

```bash
docker compose -f "漏洞靶场/DVWA/compose.yml" up -d
```

该 Compose 配置将 DVWA 映射到 `http://127.0.0.1:4280`。登录并完成数据库初始化后，将 DVWA Security Level 设置为需要验证的级别。

## 运行扫描

优先使用隐藏输入，避免 Cookie 进入 Shell 历史和进程列表：

```bash
cd "刘佳仑-期末作业"
python3 -m scanner.cli --url "http://127.0.0.1:4280/vulnerabilities/sqli/?id=1&Submit=Submit" --prompt-cookie
```

也可预先将 Cookie 保存到 `DVWA_COOKIE` 环境变量，但不应将真实值写入代码、`.env`、截图或文档。

扫描器默认将脱敏报告写入 `reports/generated/`。延时 Payload 默认禁用；只有将配置中 `allow_time_based_tests` 设为 `true` 并同时传入 `--enable-time-tests` 时才会执行。

## 运行测试

```bash
python3 -m unittest discover -v
python3 -m compileall -q scanner tests
```

## 结果边界

本工具输出的是需要人工复核的启发式可疑点，不是对漏洞的绝对定性。未发现可疑点也不代表目标绝对安全。
