# Sprint 1 预约后端

Django 5.2 + Django REST Framework 3.16。提供学生时段查询、房间／单台设备预约、induction 资料提交、资格审核和预约审核的 REST API。前端交接说明见 [frontend-api.md](docs/frontend-api.md)，完整接口定义见 [openapi.json](docs/openapi.json)。运行后也可读取 `GET /api/schema/`；该地址返回 OpenAPI JSON。

## 已实现的范围

- 所有已登录学生可以浏览资源和时段；须先提交对应 induction 资料，才能发送该资源的预约请求。
- 资格有效且时段无冲突时，预约立即 `APPROVED`。
- 资料仍在审核且时段无冲突时，预约为 `WAITING_QUALIFICATION`；从预约提交起满 24 小时后转 `PENDING_APPROVAL`。如果预约开始时间早于／等于该门槛，则直接进入人工审核，避免一直等待到使用开始。
- 与已批准预约冲突的请求立即进入 `PENDING_APPROVAL`。管理员批准时重新检查资格和冲突，不能重复批准相同时段。
- 只有 `APPROVED` 占用时段。资格审核和预约审核是独立操作；24 小时不会自动获得资格。
- 学生查看自己的 dashboard、资格和预约，取消尚未开始的有效预约。Admin／Manager 查看审核队列并作出决定。

真实学校 SSO、正式数据库、Outlook、邮件、设备领取／归还、报表和资源管理后台待后续接入。现在使用仓储和文件存储接口搭配内存演示适配器；所有演示数据和附件在进程重启后丢失，只能使用单进程运行。

## 本地启动（PowerShell）

在本目录执行：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DEBUG = "true"
$env:ENABLE_DEMO_AUTH = "true"
$env:DJANGO_SECRET_KEY = "local-demo-only-change-this-key"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1"
$env:CORS_ALLOWED_ORIGINS = "http://localhost:3000,http://localhost:5173"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

环境变量示例在 [.env.example](.env.example)。将其复制为 `.env` 不会自动加载，请设置进程环境变量，或自行使用环境加载工具。

`ENABLE_DEMO_AUTH` 默认关闭，只有 `DEBUG=true` 且显式开启时，演示登录／注册接口才可用。演示登录仅供本地演示：它不检查密码，不能开放给真实用户。演示 token 有效期 3600 秒，使用 `Authorization: Bearer <access_token>`。

演示身份：

| zID | 角色 | 用途 |
| --- | --- | --- |
| `z1000001` | STUDENT | 已有有效 induction 的学生 |
| `z1000002` | STUDENT | 需要先上传 induction 的学生 |
| `z9000001` | ADMIN | 审核资格与预约 |
| `z9000002` | MANAGER | 审核资格与预约 |

调用 `POST /api/v1/auth/demo-login/` 并发送 `{"zid":"z1000001"}` 即可获得 token。`demo-register` 只能创建 STUDENT，不允许请求体决定管理员角色。可以用 [demo.http](demo.http) 演示完整调用流程。

所有种子资源要求通用 induction：`00000000-0000-0000-0000-000000000001`。房间 ID 末尾 `101`、`102`；单台设备 ID 末尾 `201`、`202`，完整 ID 前缀均为 `00000000-0000-0000-0000-000000000`。实际名称和规则以 `GET resources/` 返回为准。

## 检查

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

依赖的已验证精确版本保存在 `requirements-lock.txt`，可用它重建相同环境。

这些测试使用临时内存数据，覆盖资格门槛、24 小时流转、自动／人工审批、时段冲突、权限和 API 契约。数据库同学接入后，需要对自己的适配器额外运行事务和并发测试。

## 接入正式数据库

业务逻辑依赖 [booking/repository.py](booking/repository.py) 的 `Repository` Protocol，不直接查询 Django ORM。数据库适配器需实现用户、资源、资格要求、提交资料、预约和审计记录的读写接口；实体字段见 [booking/domain.py](booking/domain.py)。本 Sprint 所有可预约资源必须设置 induction 要求；未配置要求的资源会拒绝创建申请，防止配置遗漏绕过资格门槛。附件通过 [booking/storage.py](booking/storage.py) 的 `FileStorage` 接入私有文件服务。

`Repository.atomic(resource_ids, student_ids)` 必须是真实事务，并同时协调以下操作：

1. 对资源和学生的锁定顺序保持一致。
2. 在事务内重读最新资格和已批准预约，检查区间冲突，再保存状态和审计。
3. 创建请求、人工批准、资格审核触发的重新判断使用相同锁定规则。
4. 失败时完整回滚，避免两个并发请求都获批准。不能先查询可用性再独立写入预约。

区间采用 `[start, end)`，前一预约的结束时间可等于后一预约的开始时间。数据库用带时区时间，API 输出 UTC；资源规则按 `Australia/Sydney` 解释。设备按独立单台建资源，不是设备型号的库存数量。

通过 `REPOSITORY_FACTORY` 和 `FILE_STORAGE_FACTORY` 配置可导入的 factory 路径；factory 应返回实现相应 Protocol 的实例。内存适配器不需要建表或运行迁移。正式适配器可选择 Django ORM、PostgreSQL 或其他数据库，但需要保持上述接口和事务保证。正式环境应在启动时替换内存实例，不能多进程部署当前演示仓储。`SEED_DEMO_DATA` 控制演示种子数据，仅在 DEBUG 模式允许加载。

## 接入真实 SSO 与后台时间处理

真实 SSO 应验证学校提供的凭证，再映射为本地 `Principal`：`id`、`zid`、`display_name`、`role`、`active`。身份角色来自受信任的学校声明或本地管理记录，不能采用浏览器提交的角色。是否完成 induction 由资格记录判断，不能因 SSO 登录成功就视为已合格。

`AUTH_PROVIDER` 是真实认证适配器的配置入口：配置可无参数实例化的 provider 类，实现 `resolve_bearer(token: str) -> Principal`。provider 应验证凭证签名、有效期和受众，并将可信身份映射为数据库中的用户记录。当前演示 Bearer 认证不能代替学校 SSO。完成接入后，前端保留相同 `/auth/me/` 和业务接口，登录跳转／token 获取方式根据学校方案调整。

当前不支持在资格仍有效时提前续期；拒绝或到期后可以重新提交。资格续期和撤销可在后续扩展。

24 小时计算依据服务器保存的 `created_at`，`APPROVAL_WAIT_HOURS` 默认 `24`。预约查询及操作会推进到期的状态，Admin 也可调用 `POST /api/v1/admin/process-due/`。这保证 API 再次访问时可看到正确状态；如果需要在无人访问系统时准时处理，正式部署应增加定时任务，调用同一个时间处理服务。

资料仅本人和 Admin／Manager 能通过受保护下载接口读取。正式文件存储必须保持私有权限；同时补齐部署配置、SSO、数据库、后台任务与文件服务后，才能作为真实校园服务使用。
