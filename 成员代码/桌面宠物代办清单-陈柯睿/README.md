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
cd /Users/apple/Documents/Playground/pet-todo
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

[app.py](/Users/apple/Documents/Playground/pet-todo/app.py) 负责几件事：

- 渲染首页
- 从 `data/state.json` 读取和保存待办数据
- 根据完成数量计算宠物等级和状态
- 提供待办相关接口

目前包含的主要接口：

- `GET /api/state` 获取当前页面状态
- `POST /api/todos` 新增任务
- `PATCH /api/todos/<todo_id>` 更新任务完成状态
- `DELETE /api/todos/<todo_id>` 删除任务
- `POST /api/todos/clear-done` 清除已完成任务
- `POST /api/pet/pat` 点击“摸摸它”后的宠物反馈

### 前端

[templates/index.html](/Users/apple/Documents/Playground/pet-todo/templates/index.html) 是页面模板，结构比较简单，主要分成宠物面板和待办面板两部分。

[static/script.js](/Users/apple/Documents/Playground/pet-todo/static/script.js) 负责：

- 页面初始化时请求后端状态
- 提交表单新增任务
- 勾选任务时调用接口同步状态
- 删除任务和清除已完成任务
- 根据接口返回结果重新渲染页面

[static/styles.css](/Users/apple/Documents/Playground/pet-todo/static/styles.css) 主要处理布局、宠物造型和不同心情状态下的动画表现。

## 数据存储

项目没有接数据库，任务数据默认保存在：

[data/state.json](/Users/apple/Documents/Playground/pet-todo/data/state.json)

里面会记录：

- `todos`
- `completed_total`
- `growth`

这种方式足够轻，适合这个体量的项目。如果后面想继续扩展，可以再换成 `SQLite`。

## 适合继续扩展的方向

- 给任务增加优先级
- 给任务增加截止日期
- 让宠物在不同时间段显示不同状态
- 增加多个宠物形态
- 把 `state.json` 改成 `SQLite`

## 备注

这个项目现在更偏“轻量演示 + 练手项目”，重点是结构清楚、功能完整、好改动。如果后面要继续加功能，建议优先把后端状态逻辑拆成单独模块，再补一点测试。
