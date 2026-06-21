# 整改前后对比说明

## 整改前

- 页面打开后直接请求 `/api/state`。
- `/api/state`、`/api/todos`、`/api/todos/<todo_id>` 等接口无需登录即可访问。
- 所有待办数据保存在同一份状态文件中，缺少用户身份和权限边界。
- 如果 Flask 服务暴露到其他网络环境，其他人可以读取或修改本地待办数据。

## 整改后

- 页面启动时先请求 `/api/session` 判断是否已登录。
- 未登录用户只能看到注册/登录面板，不能读取待办数据。
- 新增 `/api/register`、`/api/login`、`/api/logout`。
- 后端使用 `@login_required` 保护待办数据接口。
- 新增 `/api/account/summary`，必须登录后才能访问。
- 用户密码使用 PBKDF2 和随机盐保存哈希，不保存明文密码。
- 待办数据按用户 ID 保存，避免不同用户相互访问。
- 默认状态通过 `create_default_state()` 深拷贝生成，避免多个新用户共享同一个待办列表引用。
- 登出后会话被清除，再次访问接口会返回 `401`。

## 关键代码变化

- 新增用户文件：`data/users.json`
- 新增用户状态目录：`data/user-states/`
- 新增注册/登录接口：`/api/register`、`/api/login`
- 新增认证装饰器：`login_required`
- 新增默认状态工厂：`create_default_state`
- 新增受保护功能接口：`GET /api/account/summary`
- 受保护的现有接口：
  - `GET /api/state`
  - `POST /api/todos`
  - `PATCH /api/todos/<todo_id>`
  - `DELETE /api/todos/<todo_id>`
  - `POST /api/todos/clear-done`
  - `POST /api/pet/pat`

## 安全收益

- 降低未授权读取和篡改待办数据的风险。
- 避免明文或硬编码保存密码。
- 增加用户间数据隔离，降低横向越权风险。
- 修复默认状态浅拷贝导致的潜在跨用户数据串扰。
- 将安全控制放在后端接口层，而不是仅依赖前端页面隐藏。

## 回归验证

已在 `成员代码/桌面宠物待办清单-陈柯睿` 下执行：

```bash
pytest -q
```

结果：`13 passed in 0.27s`。
