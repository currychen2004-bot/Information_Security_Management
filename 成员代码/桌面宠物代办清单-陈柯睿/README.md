# 桌面宠物待办

一个用 `Flask` 写的轻量待办小项目。

页面左侧是一只会根据任务进度变化状态的桌面宠物，右侧是当天待办列表。完成任务之后，宠物会成长、升级，也会给出简单反馈。整个项目没有引入复杂框架，后端只负责模板渲染、任务数据读写和几条 JSON 接口，适合当作一个小型练手项目来看。

## 功能

- 添加、完成、删除待办
- 清除已完成任务
- 宠物根据任务数量和完成情况切换状态
- 使用本地 `JSON` 文件保存数据
- 前后端分离得比较轻：页面由 Flask 提供，交互通过 `fetch` 调接口完成

## 运行方式

先进入项目目录：

```bash
cd 成员代码/桌面宠物代办清单-陈柯睿
```

创建虚拟环境：

```bash
python3 -m venv .venv
```

安装依赖：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

启动项目：

```bash
python app.py
```

如需本地调试模式，可以显式开启：

```bash
FLASK_DEBUG=1 python app.py
```

启动后在浏览器打开：

```text
http://127.0.0.1:5000
```

## 项目结构

```text
pet-todo/
├── app.py
├── requirements.txt
├── data/
│   └── state.json
├── templates/
│   └── index.html
└── static/
    ├── styles.css
    └── script.js
```

## 代码说明

### 后端

[app.py](app.py) 负责几件事：

- 渲染首页
- 从 `data/state.json` 读取和保存待办数据
- 根据完成数量计算宠物等级和状态
- 提供待办相关接口
- 通过具名常量控制任务最大长度、宠物升级进度和任务过多阈值，避免魔法数字散落在业务逻辑中

目前包含的主要接口：

- `GET /api/state` 获取当前页面状态
- `POST /api/todos` 新增任务
- `PATCH /api/todos/<todo_id>` 更新任务完成状态
- `DELETE /api/todos/<todo_id>` 删除任务
- `POST /api/todos/clear-done` 清除已完成任务
- `POST /api/pet/pat` 点击“摸摸它”后的宠物反馈

### 前端

[templates/index.html](templates/index.html) 是页面模板，结构比较简单，主要分成宠物面板和待办面板两部分。

[static/script.js](static/script.js) 负责：

- 页面初始化时请求后端状态
- 提交表单新增任务
- 勾选任务时调用接口同步状态
- 删除任务和清除已完成任务
- 根据接口返回结果重新渲染页面

[static/styles.css](static/styles.css) 主要处理布局、宠物造型和不同心情状态下的动画表现。

## 数据存储

项目没有接数据库，任务数据默认保存在：

[data/state.json](data/state.json)

里面会记录：

- `todos`
- `completed_total`
- `growth`

## 安全与提交说明

- 不要把 `.env`、密钥、证书或真实部署配置提交到仓库，根目录 `.gitignore` 已补充相关规则。
- `data/state.json` 是本地演示数据，不适合保存真实隐私内容；如果需要保存个人数据，建议改用数据库并增加访问控制。
- Flask 调试模式会暴露交互式调试器，默认不会开启；只应在本机开发环境通过 `FLASK_DEBUG=1` 临时启用。

## 验证方式

可以先做语法检查：

```bash
python3 -m py_compile app.py
```

再启动项目，手动验证添加、完成、删除、清除已完成任务和点击宠物反馈是否正常。
