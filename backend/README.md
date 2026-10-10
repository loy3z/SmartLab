# Sprint 1 预约后端

Django 5.2 + Django REST Framework 3.16。提供学生时段查询、房间／单台设备预约、induction 资料提交、资格审核和预约审核的 REST API。前端交接说明见 [frontend-api.md](docs/frontend-api.md)，完整接口定义见 [openapi.json](docs/openapi.json)。运行后也可读取 `GET /api/schema/`；该地址返回 OpenAPI JSON。

## 已实现的范围

- 所有已登录学生可以浏览资源和时段；须先提交对应 induction 资料，才能发送该资源的预约请求。
- 资格有效且时段无冲突时，预约立即 `APPROVED`。
- 资料仍在审核且时段无冲突时，预约为 `WAITING_QUALIFICATION`；从预约提交起满 24 小时后转 `PENDING_APPROVAL`。如果预约开始时间早于／等于该门槛，则直接进入人工审核，避免一直等待到使用开始。
- 预约至少提前 7 天、最多提前 30 天（`MIN_ADVANCE_DAYS`／`MAX_ADVANCE_DAYS`，例：周六最早约下周六）；资料还在审核的学生，每项资格只能有 1 张未决申请（`UNVERIFIED_PENDING_LIMIT`）。管理员批准时重新检查资格和冲突，不能重复批准相同时段。
- 同一时段严格先到先得：`APPROVED` 持续占用时段；时段空着时，资料待审的申请成为第一位并占住时段 30 分钟（Manager 可按资源调整）。占位期间后来的重叠申请进入等待名单 `WAITLISTED`，即使资格已通过也不能插队，管理员也不能直接批准候补。占位到期时资料仍未通过，原申请也进入候补（`HOLD_EXPIRED`），每张申请只有一次占位机会，之后要等资料通过才能被递补。时段空出来时（取消、拒绝、过期、改期、占位到期，或候补学生的资料通过），系统按提交顺序自动递补：资格已通过就直接获批，资料待审且没占过位就成为新的第一位。默认设置下，“24 小时转人工”只在占位超过 24 小时时才会出现。资格审核和预约审核是独立操作；24 小时不会自动获得资格。资料被拒时，该学生依赖这项资格的所有未决预约（包括候补）会被自动拒绝（`QUALIFICATION_REJECTED`，沿用资料的拒绝原因），时段立即交给下一位候补；学生重新上传资料后再预约。
- 学生查看自己的 dashboard、资格和预约，取消尚未开始的有效预约。Admin／Manager 查看审核队列并作出决定。
- **Manager 拥有 Admin 的全部权限**，另外独有占位规则配置和人员管理：通过 `GET /api/v1/admin/users/` 查看人员名单，用 `PATCH /api/v1/admin/users/{id}/` 指定角色（Student／Admin／Manager）或停用账号（不能改自己，至少保留一个 Manager，修改写审计）。
- Admin／Manager 可通过 `GET /api/v1/admin/audit/` 按资源、学生、操作类型和时间查看审计记录（申请、审批、改期、取消、资格审核等），满足客户对操作轨迹的要求。

已补齐客户 2026-10-07 要求的大学邮箱字段和 Pending 临时占位。有效占位阻止后来请求自动获批，管理员也不能越过占位批准重叠预约。冲突请求进入等待名单，不取得新的占位。每个资源目前关联一项资格要求，资格有效期必须覆盖预约结束时间。

Manager 可通过 `GET /api/v1/admin/resources/{id}/booking-policy/` 查看规则，并用 `PATCH` 提交 `{"pending_hold_minutes":30}`。支持整数 1–20160 分钟（默认 30；设为 20160 相当于第一位保持到有结果），只影响之后创建的占位；Admin 可以读取，不能修改。新种子资源的默认值由 `DEFAULT_PENDING_HOLD_MINUTES` 设置，与 24 小时审批等待独立。占位截止时间不晚于预约开始时间，刷新页面、重复提交同一幂等请求和审批升级都不会延长占位。

已提供 Microsoft Graph 的真实 Outlook 日历适配器：批准预约后自动尝试创建事件，取消已批准预约时删除事件；同步状态独立于预约状态，失败可重试。默认关闭，个人账号演示步骤见 [outlook-setup.md](docs/outlook-setup.md)。真实连通需要本地配置微软授权，自动化测试使用模拟响应。

真实学校 SSO、正式数据库、邮件通知、设备领取／归还、报表和资源管理后台待后续接入。重复预约及更完整的 Manager 规则配置安排到 Sprint 2（改期和等待名单已提前实现）。现在使用仓储和文件存储接口搭配内存演示适配器；演示数据、附件和日历事件对应关系在进程重启后丢失，只能使用单进程运行。

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

演示注册必须提供 `zid`、`display_name`、`university_email`。演示邮箱只检查格式，不验证学校归属或邮箱所有权；正式认证由可信 SSO 声明提供。种子身份使用对应 `zID@ad.unsw.edu.au` 演示地址。

按客户原型要求，种子数据包含 2 间实验室（`101`、`102`）和 20 台示例设备（`201`–`220`），每台设备都是独立资源，有自己的可用性。`101` 和放在 Lab Room 1 的普通设备要求基础 induction `00000000-0000-0000-0000-000000000001`；`102` 和 Lab Room 2 的专业设备（如 `202` Camera 001、3D 打印机、激光切割机）要求高级培训 `00000000-0000-0000-0000-000000000002`。资源完整 ID 前缀均为 `00000000-0000-0000-0000-000000000`，清单见 `booking/runtime.py` 的 `DEMO_RESOURCES`。学生 `z1000001` 仅具备基础资格，因此不能直接申请高级资源。实际名称和规则以 `GET resources/` 返回为准。

## 检查

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

依赖的已验证精确版本保存在 `requirements-lock.txt`，可用它重建相同环境。

这些测试使用临时内存数据，覆盖资格门槛、24 小时流转、自动／人工审批、临时占位与到期释放、并发冲突、Manager 规则权限、身份邮箱和 API 契约。数据库同学接入后，需要对自己的适配器额外运行事务和并发测试。

## 接入正式数据库

业务逻辑依赖 [booking/repository.py](booking/repository.py) 的 `Repository` Protocol，不直接查询 Django ORM。数据库适配器需实现用户、资源、资格要求、提交资料、预约和审计记录的读写接口；实体字段见 [booking/domain.py](booking/domain.py)，新增字段、占位查询和事务约定见 [database-interface.md](docs/database-interface.md)。本 Sprint 所有可预约资源必须设置 induction 要求；未配置要求的资源会拒绝创建申请，防止配置遗漏绕过资格门槛。附件通过 [booking/storage.py](booking/storage.py) 的 `FileStorage` 接入私有文件服务。

`Repository.atomic(resource_ids, student_ids)` 必须是真实事务，并同时协调以下操作：

1. 对资源和学生的锁定顺序保持一致。
2. 在事务内重读最新资格，通过 `list_blocking_bookings` 查询已批准预约和未到期 Pending 占位，检查区间冲突，再保存状态和审计。
3. 创建请求、人工批准、资格审核触发的重新判断使用相同锁定规则。
4. 失败时完整回滚，避免两个并发请求都获批准。不能先查询可用性再独立写入预约。

区间采用 `[start, end)`，前一预约的结束时间可等于后一预约的开始时间。数据库用带时区时间，API 输出 UTC；资源规则按 `Australia/Sydney` 解释。设备按独立单台建资源，不是设备型号的库存数量。

通过 `REPOSITORY_FACTORY` 和 `FILE_STORAGE_FACTORY` 配置可导入的 factory 路径；factory 应返回实现相应 Protocol 的实例。内存适配器不需要建表或运行迁移。正式适配器可选择 Django ORM、PostgreSQL 或其他数据库，但需要保持上述接口和事务保证。正式环境应在启动时替换内存实例，不能多进程部署当前演示仓储。`SEED_DEMO_DATA` 控制演示种子数据，仅在 DEBUG 模式允许加载。

## 接入真实 SSO 与后台时间处理

真实 SSO 应验证学校提供的凭证，再映射为本地 `Principal`：`id`、`zid`、`display_name`、`university_email`、`role`、`active`。身份角色来自受信任的学校声明或本地管理记录，不能采用浏览器提交的角色。是否完成 induction 由资格记录判断，不能因 SSO 登录成功就视为已合格。

`AUTH_PROVIDER` 是真实认证适配器的配置入口：配置可无参数实例化的 provider 类，实现 `resolve_bearer(token: str) -> Principal`。provider 应验证凭证签名、有效期和受众，并将可信身份映射为数据库中的用户记录。当前演示 Bearer 认证不能代替学校 SSO。完成接入后，前端保留相同 `/auth/me/` 和业务接口，登录跳转／token 获取方式根据学校方案调整。

24 小时计算依据服务器保存的 `created_at`，`APPROVAL_WAIT_HOURS` 默认 `24`。预约查询及操作会推进到期的状态，Admin 也可调用 `POST /api/v1/admin/process-due/`。这保证 API 再次访问时可看到正确状态；如果需要在无人访问系统时准时处理，正式部署应增加定时任务，调用同一个时间处理服务。

资料仅本人和 Admin／Manager 能通过受保护下载接口读取。正式文件存储必须保持私有权限；同时补齐部署配置、SSO、数据库、后台任务与文件服务后，才能作为真实校园服务使用。

## 资格来源与有效期

Sprint 1 采用固定规则：资格审核通过后，有效期为审核时间加 `QUALIFICATION_VALIDITY_DAYS` 天（默认 120 天，约一个学期），审核人不能自行填写有效期。预约结束时间必须不晚于有效期。当前不支持在资格仍有效时提前续期；拒绝或到期后可以重新提交。资格续期和撤销可在后续扩展。120 天是演示默认值，不是客户确认的政策。

有效期计算集中在 `BookingService.qualification_expiry`；如以后改为按学期结束日或按资格类型设定，只需修改这一处。所有预约路径（创建、审批、改期、可用性查询）都通过 `BookingService.qualification_state` 判断资格，它只读取该资源要求的最新 `QualificationSubmission`。

以后如果客户希望由 Moodle 课程完成记录自动判断资格，可以新增一个资格来源适配器：读取学校提供的完成记录（zID、对应课程／模块、完成时间），为对应的 `requirement_id` 保存一条 `VERIFIED` 的 `QualificationSubmission`，`reviewed_by` 标明来源，`valid_until` 使用 `qualification_expiry`。预约、审批、冲突和占位规则无需修改。Moodle 对接需要学校提供接口与数据授权，由客户方实现和维护；当前项目不连接 Moodle。

## Outlook 与数据库交接

`booking/outlook.py` 定义 `CalendarProvider` 和真实 Microsoft Graph 适配器。`booking/calendar_sync.py` 负责事件对应关系、失败退避重试、取消补偿和处理租约。个人演示将所有资源预约写到一个账号的默认日历；`OUTLOOK_MAILBOX`、`OUTLOOK_CALENDAR_ID` 可指定 Microsoft 365 日历。Sprint 1 不读取 Outlook 外部占用，也不接收 Outlook 编辑；演示预约在本系统操作。

数据库适配器新增 `get_outlook_sync(booking_id)`、`list_outlook_sync()`、`save_outlook_sync(record)`，实体为 `OutlookSyncRecord`。预约、同步记录、审计必须在同一 `atomic` 事务内保存。通过相同资源／学生锁领取处理租约，网络调用发生在事务外，完成后重读版本再更新；保留取消预约的事件对应关系。

内存演示通过预约 API 自动尝试同步，管理员可用 `admin/outlook/process/` 和 `admin/bookings/{id}/outlook-retry/` 处理失败。接入共享数据库后，可定时执行 `python manage.py process_outlook --limit 10`；独立进程不能读取演示服务器的内存，因此该命令拒绝内存适配器。
