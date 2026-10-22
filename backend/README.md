# SmartLab 预约后端

Django 5.2 + Django REST Framework 3.16。提供学生时段查询、房间／单台设备预约、induction 资料提交、资格审核和预约审核的 REST API。前端交接说明见 [frontend-api.md](docs/frontend-api.md)，完整接口定义见 [openapi.json](docs/openapi.json)。运行后也可读取 `GET /api/schema/`；该地址返回 OpenAPI JSON。

## 功能与规则

- **所有人用同一套规则预约**：学生、Admin、Manager 都可以预约，**只有对应 induction 已通过且有效期覆盖整个预约时才能提交申请**；资料还在审核、被拒或已过期都不能申请，员工也不例外。induction 只能由 Admin／Manager 人工审核，不能审核自己的。
- **代他人预约**：Admin／Manager 可以用 `on_behalf_of_zid` 替别人预约。预约属于被预约人（`student_id`，检查他的 induction），`created_by` 记录创建者，审计同时记两个人。不能审批给自己的或自己创建的申请。
- **紧急申请**：开始时间早于最短提前期（默认 7 天）的申请可以标为紧急（必须写原因）。只跳过提前期，induction、开放时间和冲突照常检查（时段必须空闲，不进候补）；只有 Manager 能决定，不自动批准，开始前没人决定就过期。
- **只有 Manager 能改期**：改任何人已批准的未来预约，不受最短提前期限制（`RESCHEDULED_BY_MANAGER`）。
- **前置 induction**：一项 induction 可以要求先通过另一项（`QualificationRequirement.prerequisite_ids`，数据库列 `prerequisite_ids uuid[]`）。演示数据中 Advanced laboratory training 要求先有 General laboratory induction：General 未通过时不能提交 Advanced 资料，Admin 也不能通过 Advanced；预约 Advanced 资源时，General 和 Advanced **都必须有效并覆盖整个预约**（缺 General 时 `qualification_status=PREREQUISITE_REQUIRED`）。Manager 可用 `PATCH /api/v1/admin/qualification-requirements/{id}/` 设置 `{"prerequisite_ids":[...]}`，不允许形成循环。
- **统一规则检查**：创建申请、Admin 批准、超时自动处理、候补递补、改期都调用同一个 `BookingService.rule_violation`，按顺序检查账号是否启用、资源是否可用、时间是否合法、（创建和改期时）预约窗口、资格及前置资格。任何路径都不会绕过其中一项。
- **账号状态**：停用学生账号时，该学生所有未决申请（待审批和候补）立即拒绝（`ACCOUNT_DEACTIVATED`）并递补下一位；已批准的预约保留，由 Manager 决定是否取消。批准或自动处理时也会再次检查账号是否启用（`AUTO_REJECTED_ACCOUNT_INACTIVE`）。
- **房间和设备**：设备记录所在房间（`room_id`），页面按房间分组显示。房间维修／关闭只暂停该房间本身的预约，**不影响**房间里设备的借用；设备有自己的状态。
- **每个申请都先进入待审批 `PENDING_APPROVAL`**（`reason_code=AWAITING_REVIEW`），不算确认，但在审批期限内为申请人占住时段（`hold_until` = `review_due_at`）。Admin／Manager 可以随时批准或拒绝；审批期限（资源的 `pending_hold_minutes`，默认 1440 分钟即 24 小时，Manager 可按资源调整，且不晚于预约开始）到了还没人处理，系统自动处理：资格仍覆盖整个预约、资源可用、时段无已批准冲突就批准（`AUTO_APPROVED_AFTER_REVIEW_WINDOW`），否则拒绝（`AUTO_REJECTED_*`，`decision_reason` 写明原因），`reviewed_by` 为 `SYSTEM`。批准后才写入 Outlook。
- 预约至少提前 7 天、最多提前 30 天（团队提议，待客户确认）。这些数字不写死在代码里，见下文“可配置规则”。管理员批准时重新检查资格和冲突，不能重复批准相同时段。
- 同一时段严格先到先得：已批准预约和审批期内的待审批申请占用时段；之后的重叠申请进入等待名单 `WAITLISTED`（`TIME_CONFLICT`／`TEMPORARY_HOLD_CONFLICT`），管理员不能直接批准候补，但可以拒绝。时段空出来时（取消、被拒、过期、改期、资源重新开放），系统按提交顺序递补：申请人资格仍有效就转为新的待审批申请（`PROMOTED_FROM_WAITLIST`，重新计算审批期限），否则拒绝。前一位获批后，候补保留为后备，到开始时间仍未轮到则 `EXPIRED`。资料被拒时，该学生依赖这项资格的所有未决申请（包括候补）会被一并拒绝（`QUALIFICATION_REJECTED`）。
- 同一学生不能为同一资源重复提交时间重叠的有效申请；已有 `PENDING_APPROVAL`、`WAITLISTED` 或 `APPROVED` 记录时返回 `DUPLICATE_BOOKING`。取消、拒绝或过期后可重新申请；不同资源在同一时间仍可分别预约。
- 学生查看自己的 dashboard、资格和预约，取消尚未开始的有效预约。员工的“我的预约”还包括自己替别人建的申请。Admin／Manager 查看审批队列并作出决定，也可以取消任何人的预约（`CANCELLED_BY_STAFF`）；Manager 可以改期（可以改时长）。
- Manager 可以把房间或设备设为维修中／关闭（`PATCH /api/v1/admin/resources/{id}/status/`，需填原因）：暂停新申请、批准和递补，已有预约保留并列出供 Manager 决定是否取消；改回可用后候补自动递补。
- Admin／Manager 可用 `GET /api/v1/admin/bookings/?status=ALL` 按资源、学生、日期查看所有人的预约（带学生 zID 和姓名）；Manager 可用 `GET /api/v1/admin/bookings/export/` 导出 CSV。
- **Manager 拥有 Admin 的全部权限**，另外独有审批期限配置、资源状态和人员管理；**Admin 不能访问任何 Manager 页面和接口**（包括读取审批期限）。人员管理：`GET /api/v1/admin/users/` 查看人员名单（带 `is_staff` 和学生的 induction 状态）；Add staff（`POST /api/v1/admin/users/staff/`，`role` 为 `ADMIN` 或 `MANAGER`）新建员工账号；`PATCH /api/v1/admin/users/{id}/` 停用或恢复账号。**Student、Admin、Manager 是三种分开的账号，角色在创建时确定，之后不能互换**（学生不能升为员工，Admin 和 Manager 也不能互相切换，`ROLE_CHANGE_NOT_ALLOWED` 409）；要换人就新建账号、停用旧账号。不能修改自己，至少保留一个启用的 Manager，修改写审计。`POST /api/v1/admin/users/managers/` 等同于 Add staff 选 Manager（兼容接口）。
- Admin／Manager 可通过 `GET /api/v1/admin/audit/` 按资源、学生、操作类型和时间查看审计记录（申请、审批、改期、取消、资格审核等），满足客户对操作轨迹的要求。

Pending 不算确认，但在审批期限内占住时段，后来的人不能抢走正在审核的时段；冲突的申请进入等待名单，不占位。每个资源关联一项资格要求（可带前置），资格有效期必须覆盖预约结束时间。

Manager 可通过 `GET /api/v1/admin/resources/{id}/booking-policy/` 查看审批期限，并用 `PATCH` 提交 `{"pending_hold_minutes":1440}`。支持整数 1–20160 分钟（默认 1440，即 24 小时），只影响之后进入待审批的申请；Admin 不能读取或修改。新种子资源的默认值来自可配置规则 `default_review_window_minutes`。

## 可配置规则（给客户留的接口）

客户以后可能调整的全局数字集中在 `booking/rules.py` 的 `BookingRules`，业务代码只通过 `RulesProvider.current()` 读取，每次检查都重新读取：

| 规则 | 字段 | 默认值 | 环境变量 |
| --- | --- | --- | --- |
| 最少提前天数 | `min_advance_days` | 7 | `MIN_ADVANCE_DAYS` |
| 最多提前天数 | `max_advance_days` | 30 | `MAX_ADVANCE_DAYS` |
| induction 有效天数 | `qualification_validity_days` | 120 | `QUALIFICATION_VALIDITY_DAYS` |
| 新资源默认审批期限（分钟） | `default_review_window_minutes` | 1440 | `DEFAULT_PENDING_HOLD_MINUTES` |

- 现在：默认的 `SettingsRulesProvider` 读取上面的环境变量，改值后重启即可。
- 以后：如果客户要在 Manager 页面上修改，新建一个读取数据库表的类，实现 `current()` 返回 `BookingRules`，再把环境变量 `RULES_PROVIDER` 指向它（例如 `RULES_PROVIDER=my_app.rules.DatabaseRulesProvider`）。预约、审批和资格代码都不需要改。
- 属于单个资源的规则（开放时间、时段长度、最长时长、审批期限、所需 induction、状态）仍保存在资源记录上。审批期限不晚于预约开始时间，刷新页面、重复提交同一幂等请求都不会延长期限。

已提供 Microsoft Graph 的真实 Outlook 日历适配器：预约批准后创建事件，Manager 改期时更新同一个事件，取消时删除事件；同步状态独立于预约状态，失败可重试。系统从不读取 Outlook 里的修改，**预约永远以网站为准**；用户在自己日历里删掉事件，只有 Manager 改期时才会按新时间重建。默认只邀请 `OUTLOOK_ALLOWED_ATTENDEES` 里列出的邮箱。Admin／Manager 可以在 Calendar Sync 页面（开发用）查看连接和同步状态。默认关闭；配置、个人账号登录（可自动续期）和实测命令 `manage.py outlook_live_check` 见 [outlook-setup.md](docs/outlook-setup.md)。自动化测试使用模拟响应，真实连通需要在本机完成微软授权。

预约页有两种方式：浏览资源卡片，或 **Find a free time**（按日期、时长、类型、房间、设备类别筛选，一张表看所有资源当天的空闲时间，点空闲时间直接预约；接口 `GET resources/day-overview/`，见 [frontend-api.md](docs/frontend-api.md)）。设备有 `category` 字段（演示类别是编的）。

**尚未实现**：真实学校 SSO、邮件通知、设备领取／归还、资源增删改后台、重复预约、更完整的 Manager 规则配置。

**两种存储**：默认是内存演示适配器，演示数据、附件和日历事件对应关系在进程重启后丢失，只能单进程运行；PostgreSQL 适配器会持久保存，见 [database/README.md](database/README.md)。

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

`ENABLE_DEMO_AUTH` 默认关闭，只有 `DEBUG=true` 且显式开启时，登录接口才可用。token 有效期 3600 秒，使用 `Authorization: Bearer <access_token>`。

**两个登录入口**（角色始终由账号决定，不由入口决定）：

- **学生**：大学登录（目前是模拟 SSO，`POST /api/v1/auth/demo-login/`，只填 zID，不检查密码）。staff 的 zID 在这里会被拒绝（403 `USE_STAFF_SIGN_IN`）。
- **Admin／Manager**：staff 登录页，zID + 密码（`POST /api/v1/auth/staff-sign-in/`）。学生的 zID 在这里会被拒绝（403 `STUDENT_USES_SSO`）。
- **新 staff 怎么来**：Manager 在人员管理页 Add staff，系统生成一个邀请码（如 `K7Q4-9MZD`），在人员列表里显示，直到对方激活。对方在 staff 登录页选"首次激活"，填 zID、邀请码和自己设的密码（至少 8 位，`POST /api/v1/auth/staff-activate/`），激活后邀请码作废。
- **忘记密码**：Manager 点 Reset access（`POST /api/v1/admin/users/{id}/reset-access/`），旧密码失效，生成新邀请码，对方重新激活。角色不变。
- 密码只存 Django 的密码哈希，单独存在 `StaffCredential`／`staff_credential` 表里，不会出现在任何接口响应中。这是拿到学校 SSO 之前的原型方案；staff 也接入 SSO 后，替换登录方式即可，角色判断不用改。

演示身份：

| zID | 角色 | 登录方式 |
| --- | --- | --- |
| `z1000001` | STUDENT | 大学登录（模拟）；已有有效 General induction |
| `z1000002` | STUDENT | 大学登录（模拟）；需要先上传 induction |
| `z9000001` | ADMIN | staff 登录，演示密码 `123` |
| `z9000002` | MANAGER | staff 登录，演示密码 `123` |

调用 `POST /api/v1/auth/demo-login/` 并发送 `{"zid":"z1000001"}` 即可获得学生 token；staff 调用 `POST /api/v1/auth/staff-sign-in/` 并发送 `{"zid":"z9000002","password":"123"}`。演示密码只用于这两个假账号。`demo-register` 只能创建 STUDENT，不允许请求体决定管理员角色。可以用 [demo.http](demo.http) 演示完整调用流程。

演示注册必须提供 `zid`、`display_name`、`university_email`。演示邮箱只检查格式，不验证学校归属或邮箱所有权；正式认证由可信 SSO 声明提供。种子身份使用对应 `zID@ad.unsw.edu.au` 演示地址。

按客户原型要求，种子数据包含 2 间实验室（`101`、`102`）和 20 台示例设备（`201`–`220`），每台设备都是独立资源，有自己的可用性。`101` 和放在 Lab Room 1 的普通设备要求基础 induction `00000000-0000-0000-0000-000000000001`；`102` 和 Lab Room 2 的专业设备（如 `202` Camera 001、3D 打印机、激光切割机）要求高级培训 `00000000-0000-0000-0000-000000000002`。资源完整 ID 前缀均为 `00000000-0000-0000-0000-000000000`，清单见 `booking/runtime.py` 的 `DEMO_RESOURCES`。学生 `z1000001` 仅具备基础资格，因此不能直接申请高级资源。实际名称和规则以 `GET resources/` 返回为准。

## 检查

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

依赖的已验证精确版本保存在 `requirements-lock.txt`，可用它重建相同环境。

这些测试使用临时内存数据，覆盖资格门槛、待审批与审批期限、人工审批与超时自动处理、等待名单递补、并发冲突、Manager 规则权限、身份邮箱和 API 契约。数据库同学接入后，需要对自己的适配器额外运行事务和并发测试。

## 业务代码的位置

整体结构见仓库根目录的 [ARCHITECTURE.md](../ARCHITECTURE.md)，历次改动见 [CHANGELOG.md](../CHANGELOG.md)。

所有业务规则都在 `booking/services/` 里，对外只有一个入口 `BookingService`（`from booking.services import BookingService`）。它按主题拆成几个文件，方法都挂在同一个对象上，互相直接用 `self.xxx` 调用：

| 文件 | 内容 |
| --- | --- |
| `base.py` | 时钟、规则读取、角色检查、审计写入、资源查找、状态分组常量 |
| `accounts.py` | 用户列表与停用、员工账号（邀请码、登录）、查找代订对象 |
| `resources.py` | Manager 的资源设置（审批期限、维护/关闭）和预约报表 |
| `qualifications.py` | induction 上传、审核、有效期、前置资格 |
| `checks.py` | 所有路径共用的规则检查 `rule_violation` 和冲突查询 |
| `bookings.py` | 创建（含代订、紧急）、审批、取消、Manager 改期 |
| `waitlist.py` | 过期处理、超时自动决定、候补递补 |
| `availability.py` | 单个资源某天的时段，以及预约页的全天总览 |
| `audit.py` | 审计记录查询 |

新功能放进对应主题的文件；如果是全新主题，新建一个 mixin 文件并加进 `booking/services/__init__.py` 的 `BookingService` 继承列表。

## 接入正式数据库

业务逻辑依赖 [booking/repository.py](booking/repository.py) 的 `Repository` Protocol，不直接查询 Django ORM。数据库适配器需实现用户、资源、资格要求、提交资料、预约和审计记录的读写接口；实体字段见 [booking/domain.py](booking/domain.py)，新增字段、占位查询和事务约定见 [database-interface.md](docs/database-interface.md)。所有可预约资源必须设置 induction 要求；未配置要求的资源会拒绝创建申请，防止配置遗漏绕过资格门槛。附件通过 [booking/storage.py](booking/storage.py) 的 `FileStorage` 接入私有文件服务。

`Repository.atomic(resource_ids, student_ids)` 必须是真实事务，并同时协调以下操作：

1. 对资源和学生的锁定顺序保持一致。
2. 在事务内重读最新资格，通过 `list_blocking_bookings` 查询已批准预约和未到期 Pending 占位，检查区间冲突，再保存状态和审计。
3. 创建请求、人工批准、超时自动处理和等待名单递补使用相同锁定规则。
4. 失败时完整回滚，避免两个并发请求都获批准。不能先查询可用性再独立写入预约。

区间采用 `[start, end)`，前一预约的结束时间可等于后一预约的开始时间。数据库用带时区时间，API 输出 UTC；资源规则按 `Australia/Sydney` 解释。设备按独立单台建资源，不是设备型号的库存数量。

通过 `REPOSITORY_FACTORY` 和 `FILE_STORAGE_FACTORY` 配置可导入的 factory 路径；factory 应返回实现相应 Protocol 的实例。内存适配器不需要建表或运行迁移。正式适配器可选择 Django ORM、PostgreSQL 或其他数据库，但需要保持上述接口和事务保证。正式环境应在启动时替换内存实例，不能多进程部署当前演示仓储。`SEED_DEMO_DATA` 控制演示种子数据，仅在 DEBUG 模式允许加载。

## 接入真实 SSO 与后台时间处理

真实 SSO 应验证学校提供的凭证，再映射为本地 `Principal`：`id`、`zid`、`display_name`、`university_email`、`role`、`active`。身份角色来自受信任的学校声明或本地管理记录，不能采用浏览器提交的角色。是否完成 induction 由资格记录判断，不能因 SSO 登录成功就视为已合格。

`AUTH_PROVIDER` 是真实认证适配器的配置入口：配置可无参数实例化的 provider 类，实现 `resolve_bearer(token: str) -> Principal`。provider 应验证凭证签名、有效期和受众，并将可信身份映射为数据库中的用户记录。当前演示 Bearer 认证不能代替学校 SSO。完成接入后，前端保留相同 `/auth/me/` 和业务接口，登录跳转／token 获取方式根据学校方案调整。

审批期限保存在每张申请的 `review_due_at`（进入待审批时按资源的 `pending_hold_minutes` 计算）。预约查询及操作会推进到期的状态（超时自动处理、开始时间已过则过期），Admin 也可调用 `POST /api/v1/admin/process-due/`。这保证 API 再次访问时可看到正确状态；如果需要在无人访问系统时准时处理，正式部署应增加定时任务，调用同一个时间处理服务。

资料仅本人和 Admin／Manager 能通过受保护下载接口读取。正式文件存储必须保持私有权限；同时补齐部署配置、SSO、数据库、后台任务与文件服务后，才能作为真实校园服务使用。

## 资格来源与有效期

资格审核通过后，有效期为审核时间加 `QUALIFICATION_VALIDITY_DAYS` 天（默认 120 天，约一个学期），审核人不能自行填写有效期。预约结束时间必须不晚于有效期。资格仍有效时不能提前续期；拒绝或到期后可以重新提交。资格撤销尚未实现。120 天是演示默认值，不是客户确认的政策。

有效期计算集中在 `BookingService.qualification_expiry`（`booking/services/qualifications.py`）；如以后改为按学期结束日或按资格类型设定，只需修改这一处。所有预约路径（创建、审批、改期、可用性查询）都通过 `BookingService.qualification_state` 判断资格，它只读取该资源要求的最新 `QualificationSubmission`。

以后如果客户希望由 Moodle 课程完成记录自动判断资格，可以新增一个资格来源适配器：读取学校提供的完成记录（zID、对应课程／模块、完成时间），为对应的 `requirement_id` 保存一条 `VERIFIED` 的 `QualificationSubmission`，`reviewed_by` 标明来源，`valid_until` 使用 `qualification_expiry`。预约、审批、冲突和占位规则无需修改。Moodle 对接需要学校提供接口与数据授权，由客户方实现和维护；当前项目不连接 Moodle。

## Outlook 与数据库交接

`booking/outlook.py` 定义 `CalendarProvider` 和真实 Microsoft Graph 适配器。`booking/calendar_sync.py` 负责事件对应关系、失败退避重试、取消补偿和处理租约。个人演示将所有资源预约写到一个账号的默认日历；`OUTLOOK_MAILBOX`、`OUTLOOK_CALENDAR_ID` 可指定 Microsoft 365 日历。同步是单向的：系统不读取 Outlook 里的修改，也不把任何 Outlook 改动写回预约；预约只能在本系统操作。

数据库适配器需要实现 `get_outlook_sync(booking_id)`、`list_outlook_sync()`、`save_outlook_sync(record)`，实体为 `OutlookSyncRecord`。预约、同步记录、审计必须在同一 `atomic` 事务内保存。通过相同资源／学生锁领取处理租约，网络调用发生在事务外，完成后重读版本再更新；保留取消预约的事件对应关系。

内存演示通过预约 API 自动尝试同步，管理员可用 Calendar Sync 页面（或 `admin/outlook/process/`、`admin/bookings/{id}/outlook-retry/`）处理失败。接入共享数据库后，可定时执行 `python manage.py process_outlook --limit 10`；独立进程不能读取演示服务器的内存，因此该命令拒绝内存适配器。

## 定时处理到期申请

审批期限到了的申请需要有人触发自动处理。网页请求会顺带处理，但没人访问时不会执行。使用 PostgreSQL 时请定时运行（例如每分钟一次，Windows 任务计划或 cron）：

```powershell
.\.venv\Scripts\python.exe manage.py process_due
```

输出 `Decided or expired N request(s).`。启用 Outlook 时还会处理等待中的同步（`--outlook-limit`，默认 10）。该命令同样拒绝内存适配器。
