# 整改前后对比说明

## 整改前

- 页面打开后直接请求 `/api/state`。
- `/api/state`、`/api/todos`、`/api/todos/<todo_id>` 等接口无需登录即可访问。
- 如果 Flask 服务暴露到其他网络环境，其他人可以读取或修改本地待办数据。

## 整改后

- 页面启动时先请求 `/api/session` 判断是否已登录。
- 未登录用户只能看到登录面板，不能读取待办数据。
- 后端使用 `@login_required` 保护待办数据接口。
- 访问密码来自 `PET_TODO_PASSWORD` 环境变量，避免硬编码凭据。
- 登出后会话被清除，再次访问接口会返回 `401`。

## 关键代码变化

- 新增会话接口：`/api/session`、`/api/login`、`/api/logout`
- 新增认证装饰器：`login_required`
- 受保护接口：
  - `GET /api/state`
  - `POST /api/todos`
  - `PATCH /api/todos/<todo_id>`
  - `DELETE /api/todos/<todo_id>`
  - `POST /api/todos/clear-done`
  - `POST /api/pet/pat`

## 安全收益

- 降低未授权读取和篡改待办数据的风险。
- 避免将访问密码写入仓库。
- 将安全控制放在后端接口层，而不是仅依赖前端页面隐藏。
