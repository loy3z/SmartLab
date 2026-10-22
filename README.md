# SmartLab：实验室与房间预约

UNSW COMP9900 小组项目（9900-F15E-BREAD）。学生、Admin、Manager 在网站上预约实验室房间和单台设备。系统会检查 induction 资格、开放时间、预约窗口和时间冲突，按审批流程处理申请，已批准的预约单向同步到 Outlook 日历。

- 后端：Django 5.2 + Django REST Framework，目录 [backend/](backend/)
- 前端：React + TypeScript + Vite，目录 [frontend/](frontend/)
- 数据库：默认用内存演示数据；也可以接本地 PostgreSQL，见 [backend/database/README.md](backend/database/README.md)

## 快速启动（Windows PowerShell，内存演示模式）

后端（在 `backend` 目录）：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DEBUG = "true"
$env:ENABLE_DEMO_AUTH = "true"
$env:DJANGO_SECRET_KEY = "local-demo-only-change-this-key"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

前端（另开一个终端，在 `frontend` 目录）：

```powershell
npm ci
npm run dev
```

打开 Vite 显示的网址（通常是 `http://localhost:5173`）。

| zID | 角色 | 登录方式 |
| --- | --- | --- |
| `z1000001` | Student（已有 General induction） | 大学登录（演示版，只填 zID） |
| `z1000002` | Student（还没有 induction） | 大学登录（演示版） |
| `z9000001` | Admin | Staff sign-in，演示密码 `123` |
| `z9000002` | Manager | Staff sign-in，演示密码 `123` |

全部是编造的演示账号。

## 测试

```powershell
# backend
.\.venv\Scripts\python.exe manage.py test
# frontend
npm test
npm run lint
npm run build
npm run test:e2e
```

PostgreSQL 集成测试的运行方法见 [backend/database/README.md](backend/database/README.md) 第 6 节。

## 文档

| 文档 | 内容 |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 整体结构、一次请求怎么走、加功能改哪里 |
| [CHANGELOG.md](CHANGELOG.md) | 历次改动和原因 |
| [backend/README.md](backend/README.md) | 功能与规则、配置、登录方式、交接说明 |
| [frontend/README.md](frontend/README.md) | 前端路由、登录流程、检查命令 |
| [backend/docs/frontend-api.md](backend/docs/frontend-api.md) | 前端调用接口的说明和错误码 |
| [backend/docs/openapi.json](backend/docs/openapi.json) | 完整接口定义（运行后也可读 `GET /api/schema/`） |
| [backend/docs/database-interface.md](backend/docs/database-interface.md) | 数据库适配器要遵守的约定 |
| [backend/database/README.md](backend/database/README.md) | 本地 PostgreSQL 搭建和升级 |
| [backend/docs/outlook-setup.md](backend/docs/outlook-setup.md) | Outlook 同步的配置和实测 |

## 注意

- 不要把 `.env`、数据库密码、微软 Token 或 `backend/.local/` 提交进 Git。
- 提交时按具体文件路径 `git add`，不要 `git add backend`（会带上 `.local`）。
