# 前端接口说明

API 基础路径为 `/api/v1/`，所有路径末尾都有 `/`。正式结构见 [openapi.json](openapi.json)，启动后的 `GET /api/schema/` 返回相同定义。

## 前端需要完成的功能

| 页面／交互 | 前端职责 | 后端负责 |
| --- | --- | --- |
| 登录与角色入口 | 学生：大学登录（模拟 SSO）；Admin／Manager：staff 登录页（zID + 密码、首次用邀请码激活）；保存 token，按角色显示菜单 | 校验身份和角色；两个入口互相拒绝对方的账号；接口权限 |
| 资源与时段查询 | 房间／设备筛选、日期和时长选择、时段展示 | 查询资源、生成时段、检查冲突 |
| 学生 dashboard | 显示资格、预约状态和数量，刷新结果 | 返回当前学生的数据与汇总 |
| Induction 提交 | 选择资格要求，填写说明，上传文件，展示审核结果 | 检查附件、保存提交、保护下载权限 |
| 预约申请 | 选择资源和时间，填写用途，提交后显示服务端状态 | 验证资格门槛、时间规则、自动／人工审批 |
| 我的预约 | 显示详情、改期／取消确认、操作后刷新 | 判断归属及状态，重新校验并执行改期／取消 |
| 管理员资格审核 | 审核列表、查看资料、通过／拒绝和原因；显示后端返回的有效期 | 修改资格、自动设定有效期；拒绝时自动拒绝该学生依赖此资格的未决预约（待审批和候补） |
| 管理员预约审核 | 审核队列、详情、通过／拒绝和原因、显示冲突错误 | 批准前再次检查资格与冲突 |
| 通知、日历订阅、到场确认 | 顶部铃铛；“我的预约”里的订阅链接、I'm here 按钮、冻结提示和解冻申请 | 生成通知和订阅内容、记录缺席、冻结和取消 |
| 冻结管理、重复预约（员工） | Booking freezes 页面；资源卡片上的 Repeat weekly | 解冻审批；逐日检查并直接批准重复预约 |
| 审计记录 | Admin／Manager 按资源、学生、操作、时间筛选并分页查看；预约详情可显示该预约的历史 | 记录并查询申请、审批、改期、取消和资格审核轨迹 |
| 人员与角色管理（仅 Manager） | 人员列表、按角色筛选；Add staff | 只允许 Manager；角色创建后固定，不能互转；不能改自己；至少保留一个 Manager；写审计 |
| Manager 审批期限 | 按资源显示和修改审批期限分钟数 | 角色校验、规则保存和审计；Admin 不能读取或修改 |
| 资源管理（仅 Manager） | Resources 页面：新增、编辑、下架、恢复房间和设备；显示不再符合新规则的预约 | 校验资源规则、保存、审计；列出受影响的预约（不自动取消） |
| 预约记录与使用情况（Admin／Manager） | Booking Records 页面：Records 标签按日期、资源、状态、姓名／zID 筛选并导出 CSV；Usage statistics 标签显示每个资源的数字 | 筛选、导出 CSV、统计预约、时长、到场率 |
| 邮件通知 | 无（后端在请求结束后发出） | 按 `EMAIL_MODE` 给预约人发邮件，见 [email-setup.md](email-setup.md) |
| 修改密码（员工） | Account 页面的表单 | 校验当前密码、保存新密码哈希 |

隐藏按钮只能改善体验；身份、资格和冲突均由后端执行。前端不能直接设置预约状态、资格状态或用户角色。

演示学生注册需要 `zid`、`display_name`、`university_email`，缺少或格式错误的邮箱返回 400。登录／注册响应中的用户对象以及 `auth/me/` 均返回邮箱。演示模式不验证邮箱所有权；正式 SSO 的邮箱及角色必须由后端从可信身份来源映射。

## 两个登录入口（staff 登录）

- **学生**：`POST auth/demo-login/`（模拟大学登录，只要 zID）。staff 的 zID 返回 403 `USE_STAFF_SIGN_IN`。
- **Admin／Manager**：`POST auth/staff-sign-in/`，请求 `{"zid":"z9000002","password":"…"}`，返回与学生登录相同的 `{access_token, user, …}`。错误：401 `INVALID_CREDENTIALS`（zID 或密码不对）、403 `ACCOUNT_NOT_ACTIVATED`（还没激活）、403 `ACCOUNT_DEACTIVATED`、403 `STUDENT_USES_SSO`（学生用了 staff 入口）。
- **首次激活**：`POST auth/staff-activate/`，请求 `{"zid":"…","invite_code":"K7Q4-9MZD","password":"至少 8 位"}`。邀请码不区分大小写，可以不带横线；成功后直接登录并作废邀请码。错误：400 `INVALID_INVITE_CODE`、400 `VALIDATION_ERROR`（密码太短）、403 `ACCOUNT_DEACTIVATED`。
- **邀请码从哪来**：Manager 用 Add staff 新建账号后，`admin/users/` 里该员工的 `activation_status` 为 `AWAITING_ACTIVATION`，`invite_code` 就是邀请码；激活后变成 `ACTIVATED`，`invite_code` 为 `null`。学生这两个字段都是 `null`。
- **重置**：`POST admin/users/{id}/reset-access/`（仅 Manager，不能对自己，不能对学生：409 `STUDENT_USES_SSO`），旧密码失效并生成新邀请码，返回更新后的用户。
- `auth/config/` 的 `staff_sign_in_enabled` 表示 staff 入口是否可用。两个入口目前都只在演示模式（`DEBUG` + `ENABLE_DEMO_AUTH`）可用；接入学校 SSO 后再替换。
- 演示账号：z9000001（Admin）、z9000002（Manager），密码 `123`。

## 角色

- **Student**：预约自己的资源，上传自己的 induction。
- **Admin**（员工）：审核 induction 和预约申请，查看审计；**也可以预约**（给自己，或代别人预约），不能访问任何 Manager 页面或接口（403）。
- **Manager**（员工）：拥有 Admin 的全部权限，另外管理人员、资源状态、审批期限和所有预约；**只有 Manager 能改期**，也只有 Manager 能决定紧急申请。
- 所有人用同一套规则：资格（induction，含前置）、开放时间、预约窗口和冲突规则对员工同样适用，induction 不能绕过。日常申请无论角色都可以在审批期限结束时自动批准。
- Student、Admin、Manager 是三种分开的账号，角色在创建时确定：学生不会被“升级”为 Admin，Admin 和 Manager 也不能互相切换。员工账号由 Manager 用 Add staff 创建，以后可由学校身份系统提供。

### 代他人预约与紧急申请

- **代他人预约**：Admin／Manager 在 `POST bookings/` 里加 `on_behalf_of_zid`。预约属于这个人（`student_id`，检查**他的** induction），`created_by` 记录创建者，审计 `BOOKING_CREATED` 的 `details.booked_for` 是被预约人。学生传这个字段返回 403 `FORBIDDEN`；找不到 zID 404 `PERSON_NOT_FOUND`；账号停用 409 `ACCOUNT_INACTIVE`。
- 提交前可用 `GET people/lookup/?zid=z1234567`（仅员工）确认是谁；`GET resources/{id}/availability/?for_zid=...` 按被预约人返回 `can_request`、`qualification_status`、`requested_by_me`，并带 `booking_for`。
- 预约响应带 `created_by`、`booked_for`、`created_by_user`（`id`、`zid`、`display_name`、`role`）、`on_behalf`。`GET bookings/` 对员工返回“给我的”加“我替别人建的”；被预约人自己也能看到并取消。
- 不能审批“给自己的”或“自己创建的”申请（403 `SELF_REVIEW_FORBIDDEN`）。
- **紧急申请**：`urgent: true` 加 `urgent_reason`（必填，≤500 字）。只用于开始时间早于最短提前期（默认 7 天）的申请，落在正常窗口内返回 400 `URGENT_NOT_NEEDED`；最晚日期照常检查。时段必须空闲（有冲突 409 `BOOKING_CONFLICT`，不进候补）。状态 `PENDING_APPROVAL`、`reason_code=URGENT_AWAITING_MANAGER`、`review_due_at=null`、`hold_until=start`：**只能由 Manager 决定**（Admin 403 `URGENT_NEEDS_MANAGER`），不会自动批准，开始前没人决定就过期。availability 加 `urgent=true` 时，提前期内的时段显示为可选。
- **改期仅 Manager**：`POST bookings/{id}/reschedule/` 其他角色 403 `FORBIDDEN`。Manager 可改任何人已批准的未来预约，不受最短提前期限制（最晚日期、induction、开放时间、冲突照常检查），`reason_code=RESCHEDULED_BY_MANAGER`。
- 待客户确认：“override an existing booking”具体指什么；紧急申请是否只允许某些角色提交（目前所有人都可以提交，只有 Manager 能批）。
- 人员列表（`admin/users/`）中的用户带 `is_staff`（Admin 或 Manager 为 `true`）；前端按 `auth/me/` 的 `role` 判断。

## 建议调用顺序

1. 读取 `GET auth/config/` 判断认证模式；学生调用 `auth/demo-login/` 或 `auth/demo-register/`，Admin／Manager 调用 `auth/staff-sign-in/`（首次用 `auth/staff-activate/`），然后使用响应 token 调用 `GET auth/me/`。
2. 调用 `GET resources/` 和 `GET qualification-requirements/`，展示资源及其要求。
3. 学生通过 `GET qualifications/` 或 `GET dashboard/` 查看自己的资格。未提交对应资料时，显示上传入口。
4. 使用 `multipart/form-data` 调用 `POST qualifications/`，字段为 `requirement_id`、`title`、`notes`、`file`。不要手写 multipart 的 Content-Type boundary，由浏览器处理。
5. 调用 `GET resources/{id}/availability/?date=YYYY-MM-DD&duration_minutes=60` 展示时段，并读取 `can_request`／`qualification_status`。日期是资源当地的日历日期。
6. 调用 `POST bookings/`，发送 `resource_id`、`start`、`end`、`purpose`。时间必须携带时区，例如 `2026-10-07T09:00:00+11:00`；不要发送无时区字符串。
7. 按响应 `status` 显示结果，再刷新 dashboard 和可用性。HTTP 201 表示请求创建成功，重复幂等请求返回 200；只有 `APPROVED` 表示预约已经获批。
8. Admin 使用 `admin/qualifications/` 审核 induction；审核响应包含 `submission` 和 `updated_bookings`，刷新相关列表。随后用 `admin/bookings/` 审核预约。

### 审计记录

`GET admin/audit/` 仅 Admin／Manager 可用，学生返回 403。返回 `{ count, limit, offset, results }`，`count` 是筛选后的总数（分页前），`results` 按时间从新到旧。每条记录含 `action`、`entity_type`、`entity_id`、`at`、`details`，以及 `actor`（`zid`、`display_name`、`role`；系统自动处理时 `actor_id` 为 `SYSTEM`、`actor` 为 `null`）。

- 某个预约的完整历史：`?entity_id={booking_id}`。
- 某个资源：`?resource_id=...`，包括该资源所有预约的记录和占位规则修改。
- 某个学生：`?student_id=...`，包括该学生的操作及其预约、资料和账号相关记录。
- 其他筛选：`action`（如 `BOOKING_CANCELLED`）、`entity_type`（`booking|qualification|resource|principal`）、`actor_id`、`since`／`until`（必须带时区，`until` 不包含）。
- 分页：`limit` 1–500，默认 100；`offset` 默认 0。未知参数返回 400。

`details` 的字段随动作不同，例如创建预约有 `status`、`reason_code`、`hold_until`，改期有 `old_start`／`new_start` 等。前端可直接显示键值，不要依赖固定字段。

### 人员与角色管理（仅 Manager）

只有 **Manager** 能查看人员名单、新建员工、修改员工角色或停用账号；Admin 和学生访问这些接口返回 403。

- `GET admin/users/`：返回 `{ count, results }`，每项含 `id`、`zid`、`display_name`、`role`、`is_staff`、`active`、`university_email`，以及 `inductions`（每项 induction 的 `name`、`status`：`NOT_SUBMITTED`／`PENDING`／`VERIFIED`／`REJECTED`／`EXPIRED`、`valid_until`）和 `induction_status`（全部有效为 `VERIFIED`，否则 `INCOMPLETE`）。员工也可以预约，同样要有有效的 induction。可用 `role`、`active=true|false`、`q`（匹配 zID／姓名／邮箱）筛选。
- **Add staff**：`POST admin/users/staff/`，请求 `{"zid":"z5123456","display_name":"…","university_email":"…","role":"ADMIN"}`（`role` 为 `ADMIN` 或 `MANAGER`），成功 201 返回该用户，写 `ADMIN_CREATED`／`MANAGER_CREATED` 审计。zID 已存在返回 409 `USER_EXISTS`（现有学生不能变成员工）。兼容接口 `POST admin/users/managers/` 等同于 `role=MANAGER`。
- `PATCH admin/users/{id}/`：用来停用或恢复账号（`active`）。角色在创建时确定，不能修改：请求里的 `role` 与当前角色不同时返回 409 `ROLE_CHANGE_NOT_ALLOWED`（与当前相同则忽略）。要换人就用 Add staff 新建账号，再停用旧账号。修改在该用户的**下一次请求**生效；被停用的用户再请求会得到 401，前端应跳回登录页。
- **停用学生**会立即拒绝该学生所有未决申请（待审批和候补，`reason_code=ACCOUNT_DEACTIVATED`）并递补下一位；已批准的预约保留，由 Manager 决定是否取消。
- 不能修改自己（`SELF_MODIFICATION_FORBIDDEN`，403），系统至少保留一个启用的 Manager（`LAST_MANAGER`，409）。每次修改都会写一条 `USER_UPDATED` 审计记录。
- 列表里只有已经存在于系统中的用户（演示时由数据库预先写入，或登录／注册过一次）。

`dashboard` 返回 `{ bookings, qualifications, counts }`。两个列表是数组，`counts` 的键为七种大写预约状态，例如 `counts.APPROVED`；它不是资格数量或预约总数。其他列表接口使用 `{ count, results }`。

`qualification_status=NOT_CONFIGURED` 表示资源尚未设置 induction 要求，不能申请；需要维护资源数据后再开放。`qualification_status=PREREQUISITE_REQUIRED` 表示该资源的 induction 需要先通过另一项（如 Advanced 需要 General），此时 `missing_prerequisite_id` 给出缺少的那一项，前端可以直接链接到 `/induction?requirement=<id>`。

### 前置 induction

- `GET qualification-requirements/` 每项带 `prerequisite_ids`（数组）。演示数据中 Advanced laboratory training 的 `prerequisite_ids` 是 General laboratory induction。
- 前置未通过时，提交该项资料返回 409 `PREREQUISITE_REQUIRED`（`details.prerequisite_id`），Admin 通过该项资料也返回同一错误；学生页面应显示“先完成 General”，并禁用上传。
- 预约需要该项 induction 的资源时，**前置和本项都必须有效并覆盖整个预约**；缺前置时 `POST bookings/` 返回 403 `QUALIFICATION_REQUIRED`，`details.qualification_status=PREREQUISITE_REQUIRED`、`details.prerequisite_id`、`details.prerequisite_status`。
- Manager 可用 `PATCH admin/qualification-requirements/{id}/` 设置 `{"prerequisite_ids":["<uuid>"]}`（最多 20 项，不能包含自己，不能形成循环：409 `PREREQUISITE_CYCLE`），写 `REQUIREMENT_PREREQUISITES_UPDATED` 审计。
- 1.16.0：每项还带四段说明 `how_to_complete`、`accepted_evidence`、`reviewer`、`contact`（空字符串表示还没写），Induction & Training 页面在每项下面显示“How to get this induction”。Manager 在 **Lab setup** 页面（`/manager/setup`）用 `POST admin/qualification-requirements/`（`name` 必填，其余可选）新建，用同一个 `PATCH` 改 `name`、`description` 和四段说明（可以和 `prerequisite_ids` 一起发）。名称不能重复（忽略大小写，409 `REQUIREMENT_NAME_TAKEN`），说明每段最多 2000 字；改文字不影响已经通过的人。

### 房间和设备

资源的 `room_id`：设备所在房间的 ID，房间本身为 `null`。前端按房间分组设备（“该房间的 N 台设备”）。房间的维修／关闭**只影响房间本身**，房间里的设备仍按各自的 `status` 预约。房间和设备**分开预约**：订房间不包含里面的设备，订设备也不占用房间（1.16.0 起页面上写明）。

1.16.0：资源另有 `capacity`（只有房间，容纳人数，`null` 表示没填）和 `details`（`[{label, value}]`，Manager 自己定的“标签：内容”，例如型号、楼层，最多 12 行）。资源卡片显示容量和前 3 行，预约表单显示全部；房间列表可以按“至少 N 人”筛选（没填容量的房间不会被筛掉）。

可用性查询是当时的快照，提交前后仍可能有人占用时段。显示 `available=false` 的时段不能提示“可立即预约”；学生仍可对已被占用的时段提交申请，但会进入等待名单，界面应明确说明。每个资源的 `required_qualification_id` 可以不同，前端必须读取资源要求，不能用一个全局“已完成 induction”开关判断所有资源的资格。

`slots[]` 的 `reason_code` 为 `START_TIME_PASSED`、`RESOURCE_UNAVAILABLE`（维修／关闭）、`TOO_SOON`（不足 7 天）、`TOO_FAR_AHEAD`（超过 30 天）、`BOOKED`、`TEMPORARILY_HELD` 或 `null`。响应顶层另有 `earliest_date`、`latest_date`、`min_advance_days`、`max_advance_days`，供日期选择器限制范围。临时占位时返回 `hold_until`（UTC 截止时间）和 `held_by_me`（是否为当前学生自己的占位）；`requested_by_me` 表示当前学生已经对同一资源提交了与该时段重叠的有效申请，前端应禁用再次提交。接口不返回其他学生身份。可显示占位倒计时，到期刷新查询，最终以服务端响应为准；`can_request` 只有在当前用户是学生、账号启用、对应 induction（及其前置）已通过且有效、资源开放时才为 `true`，不代表所选时段会获批；为 `false` 时应禁用提交按钮并提示先完成 induction。`review_window_minutes` 是该资源的审批期限（默认 1440 分钟）。

### 审批流程

- **只有 induction 已通过且有效的人才能申请**（员工同样适用）。资料还在审核（`PENDING`）、被拒或已过期时，`POST bookings/` 返回 403 `QUALIFICATION_REQUIRED`，`details.qualification_status` 说明原因；有效期必须覆盖整个预约，否则为 `EXPIRES_BEFORE_END`。induction 只能由 Admin／Manager 人工审核，审核通过不会自动批准任何预约。
- **每个申请都先进入 `PENDING_APPROVAL`**（`reason_code=AWAITING_REVIEW`）：不算确认、不写 Outlook，但在审批期限内为申请人占住时段。`review_due_at`（与 `hold_until` 相同）是审批截止时间：进入待审批时加上资源的 `pending_hold_minutes`（默认 24 小时），不晚于预约开始。
- **Admin／Manager 在截止前批准或拒绝**（`POST admin/bookings/{id}/review/`，不能审批给自己的或自己创建的申请；紧急申请只有 Manager 能决定）。
- **截止时仍无人处理**：系统自动处理，`reviewed_by="SYSTEM"`。账号启用、资格（含前置）仍覆盖整个预约、资源开放、时段无已批准冲突 → `APPROVED`（`AUTO_APPROVED_AFTER_REVIEW_WINDOW`）；否则 `REJECTED`（`AUTO_REJECTED_ACCOUNT_INACTIVE`／`AUTO_REJECTED_QUALIFICATION`／`AUTO_REJECTED_RESOURCE_UNAVAILABLE`／`AUTO_REJECTED_BOOKING_RULES`／`AUTO_REJECTED_CONFLICT`，`decision_reason` 写明原因）。由服务端在下一次访问、`admin/process-due/` 或定时命令 `manage.py process_due` 时处理，前端只需刷新。
- **同一套规则**：创建、人工批准、自动处理、候补递补、改期都使用后端同一个规则检查，结果一致。
- 改期（仅 Manager）：已批准的未来预约可以改日期、时间和时长（受最晚日期和资格限制，不受最短提前期限制），直接生效。选时段时传 `exclude_booking_id=<正在改的预约>`、`for_zid=<预约人>`、`urgent=true`，原来的时间会显示为可选。
- Manager 通过 `PATCH admin/resources/{id}/booking-policy/` 按资源设置审批期限 `{"pending_hold_minutes":1440}`（1–20160 分钟）。

**房间／设备状态**：`PATCH admin/resources/{id}/status/`（仅 Manager），请求 `{"status":"MAINTENANCE","reason":"Fume hood repair"}`；状态为 `AVAILABLE`／`MAINTENANCE`／`CLOSED`，后两者必须填原因。
- 资源列表和详情带 `status`、`status_reason`，维修／关闭的资源仍然显示，前端应标出“维修中／已关闭”和原因。
- 维修／关闭时：新申请返回 409 `RESOURCE_UNAVAILABLE`（`details.resource_status`、`status_reason`），时段查询所有时段为 `RESOURCE_UNAVAILABLE`、`can_request=false`；不批准、不递补。**已有预约保留**，响应的 `affected_bookings` 列出仍需处理的未来预约，Manager 可逐个用 `POST bookings/{id}/cancel/` 取消（`reason_code=CANCELLED_BY_STAFF`）。改回 `AVAILABLE` 后候补自动递补。

**所有人的预订**：`GET admin/bookings/` 支持筛选 `status`（单个、逗号分隔多个或 `ALL`）、`resource_id`、`student_id`、`since`、`until`（带时区的时间，返回与该时段重叠的预约），按开始时间排序；每项带 `student`（`id`、`zid`、`display_name`、`university_email`）、`resource_name`、`resource_kind`。不带参数时返回人工审批队列。`GET admin/bookings/export/`（仅 Manager）用相同筛选导出 CSV（默认 `ALL`，UTF-8 带 BOM，可直接用 Excel 打开）；“打印”可由前端对列表页调用浏览器打印。

**Add staff**（人员管理页右上角按钮）：见上文“人员与角色管理”。删除人员请用停用（`PATCH active=false`），以保留预约和审计历史。

## 状态与界面文字

| 资格状态 | 显示含义 | 可以提交该资源预约？ |
| --- | --- | --- |
| 无提交记录 | 请先提交 induction 资料 | 否 |
| `PENDING` | 资料等待管理员审核 | 否，审核通过后才能申请 |
| 有效 `VERIFIED` | 已具备该资源资格 | 是 |
| `REJECTED` 或已过期 | 资料被拒绝／资格已过期，请重新提交 | 否 |

最新提交决定当前资格。`status` 是资料审核状态，额外的 `effective_status` 表示当前有效性，界面应结合该字段显示过期情况。有效期需要覆盖预约结束时间；在当前时刻有效，不一定覆盖用户选择的预约。已有 PENDING 提交或仍有效的 VERIFIED 提交时，不能重复上传相同要求的资料；拒绝或过期后可重新提交。

**有效期**：审核通过时后端自动设定 `valid_until = 审核时间 + QUALIFICATION_VALIDITY_DAYS`，默认 120 天（约一个学期）。审核请求不接受 `valid_until`（带上返回 400），审核页只显示响应里的 `valid_until`；学生端可显示“资格有效至 …”，并提示超过该时间的预约无法提交。资格过期前不能提前续期，过期后重新上传。

| 预约状态 | 建议显示 | 是否占时段 |
| --- | --- | --- |
| `PENDING_APPROVAL` | 等待管理员审批，显示审批截止时间 `review_due_at`，并说明超时后系统按规则自动处理 | 审批期内占位（`hold_active=true`） |
| `WAITLISTED` | 候补中，显示“候补第 `waitlist_position` 位” | 否 |
| `APPROVED` | 预约已批准 | 是 |
| `REJECTED` | 预约被拒绝 | 否 |
| `CANCELLED` | 预约已取消 | 否 |
| `EXPIRED` | 申请已过期 | 否 |

所有预约响应都带 `hold_until`（可空截止时间）、`hold_active`（当前占位是否有效）和 `blocks_slot`（当前是否阻挡重叠预约）。`APPROVED` 的 `blocks_slot=true`，即使 `hold_active=false`。不要只用非空 `hold_until` 判断占用：该值保留为历史，取消、拒绝或批准后临时占位不再有效。`WAITING_QUALIFICATION` 只出现在早期数据中，现在的流程不会产生。

### 先到先得与等待名单

同一资源、时间重叠的申请严格按提交顺序处理：

- **时段空着**（没有已批准预约，也没有别人的待审批申请）：新申请成为该时段的待审批申请并占位。
- **时段被占**：新申请进入 `WAITLISTED`（`reason_code` 为 `TIME_CONFLICT` 或 `TEMPORARY_HOLD_CONFLICT`），不占时段，响应带 `waitlist_position`（重叠候补中的第几位）。管理员不能直接批准候补（`REQUEST_WAITLISTED`），但可以拒绝。
- **递补**：时段一空出来（取消、被拒、过期、改期、资源重新开放），后端按提交顺序取下一位放得下的候补：仍符合规则 → 转为新的 `PENDING_APPROVAL`（`reason_code=PROMOTED_FROM_WAITLIST`，重新计算审批截止时间），由 Admin 审批或超时自动处理；不符合 → `REJECTED`，`reason_code` 为对应的错误码（如 `QUALIFICATION_REQUIRED`、`ACCOUNT_INACTIVE`）。时间部分重叠时，先检查提交更早的候补，放得下就先给它。
- 前一位获批后，候补保持 `WAITLISTED` 作为后备；若获批的人之后取消，或被 Admin／Manager 取消，下一位递补。候补到预约开始时间仍未轮到则 `EXPIRED`。
- 递补不会主动通知，学生需要刷新“我的预约”或 dashboard 才能看到状态变化，前端可轮询。

**限制**：
- **预约窗口**：预约开始日期（资源当地日期）必须在“今天 + 7 天”到“今天 + 30 天”之间（默认值，来自后端可配置规则 `RulesProvider`，见 backend/README“可配置规则”），即至少提前一周、最多提前一个月。例：周六 10/10 最早能约下周六 10/17，最晚 11/9。太近返回 400 `BOOKING_TOO_SOON`，太远返回 400 `BOOKING_TOO_FAR_AHEAD`；两者的 `details` 都有 `earliest_date`、`latest_date`、`min_advance_days`、`max_advance_days`。改期同样受这个窗口限制；已提交的申请不受影响，日期临近后照常审核和递补。
  - 日期选择器：用时段查询响应里的 `earliest_date`／`latest_date` 设置 `<input type="date" min max>`，不要在前端写死天数。
  - 因为至少提前一周，默认 24 小时审批期限总会早于预约开始；只有 Manager 把审批期限设得比提前天数还长时，期限才会被截到预约开始时间。

`TEMPORARILY_HELD` 时段可显示为“有人申请，审核中”，并显示 `hold_until`；学生仍可提交，提交后会进入候补。刷新和幂等重试不会延长占位。

示例（默认 24 小时）：周一 10:00 A（资格有效）申请下周一 10–12 点，进入待审批，占位到周二 10:00 → 周一 11:00 B 申请同一时段，进候补第 1 位 → Admin 若在周二 10:00 前拒绝 A，B 立即转为待审批，重新计时 24 小时；若无人处理，周二 10:00 A 自动获批，B 留在候补作为后备 → 之后 A 取消或被 Manager 取消，B 递补为待审批。

**资料被拒时**（例如资格过期后重新上传的资料被拒）：后端会自动拒绝该学生对“要求这项资格的资源”的所有未决预约（`PENDING_APPROVAL` 和 `WAITLISTED`），并把空出的时段交给候补，状态变为 `REJECTED`，`reason_code` 为 `QUALIFICATION_REJECTED`，`decision_reason` 为资料的拒绝原因，时段立即释放。审核响应的 `updated_bookings` 会包含这些预约。学生端应显示：资料被拒及原因（资格的 `rejection_reason`）→ 相关预约已被拒 → 引导学生重新上传资料，通过或重新提交后再预约。

审批截止时间不会晚于预约开始；仍未获批的申请到开始时间后为 `EXPIRED`。

## 接口速查

下面路径均以 `/api/v1/` 开头。除健康、认证配置、登录、注册和 staff 激活外，需要 Bearer token。列表统一返回 `{ "count": 0, "results": [] }`。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `health/` | 服务状态 |
| GET | `auth/config/` | 当前认证配置 |
| POST | `auth/demo-register/` | 本地创建学生账号：`zid`、`display_name`、`university_email` |
| POST | `auth/demo-login/` | 学生的模拟大学登录：`zid`（staff 会被拒绝） |
| POST | `auth/staff-sign-in/` | Admin／Manager 登录：`zid`、`password` |
| POST | `auth/staff-activate/` | staff 首次激活：`zid`、`invite_code`、`password` |
| GET | `auth/me/` | 当前用户 |
| GET | `resources/?kind=ROOM&q=lab&category=` | 筛选资源；`kind` 也可为 `EQUIPMENT`；`category` 为设备类别 |
| GET | `resources/day-overview/?date=YYYY-MM-DD&duration_minutes=60` | 预约页"Find a free time"：所有符合筛选的资源当天的空闲情况（见下文） |
| GET | `resources/{id}/` | 资源详情 |
| GET | `resources/{id}/availability/?date=YYYY-MM-DD&duration_minutes=60` | 可用性及申请资格；员工可加 `for_zid`，紧急申请加 `urgent=true` |
| GET | `people/lookup/?zid=` | 仅员工：代预约前确认对方账号 |
| GET | `qualification-requirements/` | Induction 要求列表 |
| GET / POST | `qualifications/` | 我的提交／上传资料 |
| GET | `qualifications/{id}/` | 资料提交详情 |
| GET | `qualifications/{id}/file/` | 带权限的附件下载 |
| GET / POST | `bookings/` | 我的预约列表（员工还包括替别人建的）／创建预约（可带 `on_behalf_of_zid`、`urgent`、`urgent_reason`） |
| POST | `bookings/{id}/change/` | 1.16.0：预约人申请把自己已批准的预约改到新时间（见下文“申请改期”） |
| GET / PATCH | `site/contact/` | 1.16.0：实验室联系方式；所有人可读，Manager 修改 |
| POST | `admin/qualification-requirements/` | 1.16.0：Manager 新建 induction |
| GET | `admin/overview/` | 1.16.0：员工首页 Today 的数字和清单 |
| GET | `bookings/{id}/` | 预约详情 |
| POST | `bookings/{id}/cancel/` | 取消预约 |
| POST | `bookings/{id}/reschedule/` | 仅 Manager：改期已批准且尚未开始的预约：`start`、`end` |
| GET | `dashboard/` | 我的预约、资料与数量 |
| GET | `admin/qualifications/?status=PENDING` | 管理员资格队列（`PENDING`／`VERIFIED`／`REJECTED`）；每条带 `student`（`id`、`zid`、`display_name`、`university_email`），审核页直接显示姓名和 zID |
| POST | `admin/qualifications/{id}/review/` | `decision: VERIFIED\|REJECTED`，可带 `reason`；不接受 `valid_until`，有效期由后端设定 |
| GET | `admin/bookings/?status=PENDING_APPROVAL` | 待审批队列（默认）；`status=WAITLISTED` 查看候补；`status=ALL&resource_id=&student_id=&q=&since=&until=` 查看所有人的预约（带学生和资源名）；`q` 是 zID 或姓名的一部分（预约人或创建人，不分大小写） |
| GET | `admin/bookings/export/?status=ALL` | Admin／Manager：按相同筛选（含 `q`）导出 CSV，最后两列是 Weekly series 和 Attendance |
| POST | `admin/bookings/{id}/review/` | `decision: APPROVED\|REJECTED`，可带 `reason`；候补只能拒绝，不能批准 |
| GET | `admin/users/?role=&active=&q=` | 仅 Manager：人员列表 |
| POST | `admin/users/staff/` | 仅 Manager：Add staff，`zid`、`display_name`、`university_email`、`role`（`ADMIN`／`MANAGER`）；响应带 `invite_code` |
| POST | `admin/users/{id}/reset-access/` | 仅 Manager：重置员工登录，生成新邀请码 |
| POST | `admin/users/managers/` | 仅 Manager：兼容接口，等同于 Add staff 选 Manager |
| PATCH | `admin/users/{id}/` | 仅 Manager：`{"active":false}` 停用／`{"active":true}` 恢复；角色不能修改 |
| PATCH | `admin/qualification-requirements/{id}/` | 仅 Manager：`{"prerequisite_ids":[...]}` 设置前置 induction |
| GET | `admin/audit/?resource_id=&student_id=&action=&since=&until=&limit=100&offset=0` | Admin／Manager 查看审计记录（申请、审批、改期、取消等），最新在前 |
| POST | `admin/process-due/` | 立即处理已到审批截止时间（自动批准或拒绝）／开始时间的请求 |
| GET / PATCH | `admin/resources/{id}/booking-policy/` | 仅 Manager：读取和修改审批期限 `pending_hold_minutes` |
| PATCH | `admin/resources/{id}/status/` | 仅 Manager：`AVAILABLE`／`MAINTENANCE`／`CLOSED` + `reason` |
| GET | `admin/outlook/` | Admin／Manager：Outlook 配置、统计和每个预约的同步／检查状态（不调用微软） |
| POST | `admin/outlook/check/` | 测试微软登录和日历权限，`{}` |
| POST | `admin/outlook/process/` | 处理等待中的日历更新，`{"limit":1}`（最多 5） |
| POST | `admin/bookings/{id}/outlook-retry/` | 立即重试失败的日历更新，`{}` |
| POST | `bookings/{id}/check-in/` | 本人确认到场（I'm here），`{}` |
| POST | `bookings/series/preview/` | 员工：预览重复预约的每个日期 |
| POST | `bookings/series/` | 员工：创建重复预约（直接批准），`skip_dates` 列出要跳过的日期 |
| GET | `bookings/series/{id}/` | 重复预约及其每次预约（员工或受益人） |
| POST | `bookings/series/{id}/cancel/` | 员工：取消整组剩下的日期 |
| GET | `calendar/link/` | 我的日历订阅地址（首次调用时生成） |
| POST | `calendar/link/reset/` | 重新生成订阅地址，旧地址立即失效 |
| GET | `calendar/{token}.ics` | 订阅内容（iCalendar），不需要登录 |
| GET | `notifications/?unread=&limit=50` | 我的通知，最新在前，带 `unread_count` |
| POST | `notifications/{id}/read/` | 标为已读 |
| POST | `notifications/read-all/` | 全部标为已读 |
| GET | `notifications/preferences/` | 我的五类站内／邮件开关及网站邮件能力；见 1.19.0 |
| PUT | `notifications/preferences/` | 保存开关：`{"preferences": {"bookings": true, "reminders": false}}`，未知类别返回 400 |
| GET / POST | `account/unfreeze-requests/` | 我的解冻申请／提交解冻申请 `{"reason": "…"}` |
| GET | `admin/unfreeze-requests/?status=PENDING` | Admin／Manager：解冻申请 |
| POST | `admin/unfreeze-requests/{id}/review/` | Admin／Manager：`decision: APPROVED\|REJECTED`，拒绝要写 `reason` |
| GET | `admin/frozen-users/` | Admin／Manager：当前被冻结的人 |
| POST | `admin/users/{id}/unfreeze/` | Admin／Manager：直接解冻 |
| GET / POST | `admin/resources/` | 仅 Manager：所有资源（含已下架）／新增房间或设备 |
| PATCH | `admin/resources/{id}/` | 仅 Manager：修改资源（只发要改的字段），返回 `resource` 和 `bookings_outside_rules` |
| POST | `admin/resources/{id}/archive/`、`…/restore/` | 仅 Manager：下架／恢复，`{}` |
| GET | `admin/reports/usage/?first_date=&last_date=` | Admin／Manager：使用情况报表 |
| POST | `auth/change-password/` | Admin／Manager：修改自己的密码 `current_password`、`new_password` |

`POST bookings/` 可带 `Idempotency-Key`，同一用户重试同一请求时复用同一 key；提交不同预约时生成新 key。key 最多 128 个字符，仅可使用字母、数字、点、下划线、冒号、连字符。禁止只依赖禁用按钮防止重复请求。字段 `start`、`end` 表示区间 `[start,end)`。取消仅允许尚未开始的有效请求；重复取消已取消记录返回原记录。改期只允许 Manager 操作未来 `APPROVED` 预约；后端重新检查时间规则、资格有效期与冲突。成功后 `revision` 增加，并更新原 Outlook 事件。

时段查询默认时长为 30 分钟。普通预约按 30 分钟一个公平使用 slot 计算，最多选择 6 个 slots（3 小时）；资源本身可以设置更短的技术上限。资源和 availability 响应返回 `booking_slot_minutes`、`max_booking_slots`、`selection_step_minutes` 与 `effective_max_booking_minutes`，前端必须使用这些服务端值限制选择。同一预约不能跨当地日期。

Manager 规则页发送 `PATCH admin/resources/{id}/booking-policy/`，请求 `{"pending_hold_minutes":1440}`（字段名沿用数据库列名，含义是 Admin 审批期限，单位分钟）；GET／PATCH 均返回 `{"resource_id":"<uuid>","pending_hold_minutes":1440}`。范围为整数 1–20160，默认 1440（24 小时）。期限到了仍无人处理时，系统按规则自动批准或拒绝（见上文“审批流程”）。修改只影响之后进入待审批的申请；已有截止时间不变。资源详情包含 `pending_hold_minutes`，时段查询响应包含同值的 `review_window_minutes`。请求必须带 `pending_hold_minutes`，带 `auto_approve_max_minutes` 返回 400。

附件支持 PDF、PNG、JPEG，最大 5 MiB。后端检查大小、扩展名、MIME 和文件格式特征。资料中的 `file_url` 是受保护的 API 路径，下载仍需带 Authorization；前端可请求为 Blob 后显示／下载，不能假设 `<img src>` 或普通链接会自动附带 Bearer token。附件没有公开地址。

## 错误和时间

错误统一为：

```json
{
  "error": {
    "code": "BOOKING_CONFLICT",
    "message": "This time slot is already booked.",
    "details": {}
  }
}
```

前端依据 `error.code` 和 HTTP 状态处理，不依赖英文 message 的固定内容。`details` 可包含字段错误或冲突信息，用户提示不得泄露其他学生的资料。

| HTTP 状态 | 前端处理 |
| --- | --- |
| 400 | 展示字段、时间或文件校验错误 |
| 401 | 登录失效，重新登录 |
| 403 | 无权限或未满足提交资料门槛 |
| 404 | 记录不存在／当前身份无法访问 |
| 409 | 冲突、重复请求或当前状态无法执行；刷新数据 |

常见业务错误：

| `error.code` | HTTP | 前端动作 |
| --- | --- | --- |
| `QUALIFICATION_REQUIRED` | 403 | 只有 induction 已审核通过且在有效期内才能提交；`details.qualification_status` 为 `PENDING` 时提示“资料审核中，通过后才能预约”，其他状态引导去上传 |
| `QUALIFICATION_NOT_VERIFIED` | 409 | 管理员先处理资格，不能直接批准预约；`details.qualification_status` 说明原因（含 `PREREQUISITE_REQUIRED`） |
| `ACCOUNT_INACTIVE` | 409 | 申请人账号已停用，不能批准，也不能代他预约 |
| `PERSON_NOT_FOUND` | 404 | 代预约的 zID 不存在 |
| `URGENT_REASON_REQUIRED` | 400 | 紧急申请要写原因 |
| `URGENT_NOT_NEEDED` | 400 | 时间在正常预约窗口内，发普通申请 |
| `URGENT_NEEDS_MANAGER` | 403 | 紧急申请只有 Manager 能决定 |
| `BOOKING_CONFLICT` | 409 | 人工批准或紧急申请失败：时段已有获批预约（紧急申请时也包括待审批占位） |
| `BOOKING_HOLD_CONFLICT` | 409 | 人工批准失败，提示时段仍临时占用；`details.hold_until` 为当前占位截止时间 |
| `REQUEST_WAITLISTED` | 409 | 候补不能直接批准，会按顺序自动递补；管理员可以拒绝 |
| `SELF_REVIEW_FORBIDDEN` | 403 | 不能审核自己的 induction 资料、给自己的或自己创建的预约申请，交给其他 Admin 或 Manager |
| `RESOURCE_POLICY_NOT_CONFIGURED` | 409 | 资源没有配置所需 induction，暂不能预约；提示联系 Manager |
| `RESOURCE_UNAVAILABLE` | 409 | 资源维修或关闭；显示 `details.status_reason`，暂停新预约 |
| `USER_EXISTS` | 409 | Add staff 时 zID 已存在 |
| `USE_STAFF_SIGN_IN` | 403 | staff 用了学生登录，引导去 staff 登录页 |
| `STUDENT_USES_SSO` | 403／409 | 学生用了 staff 登录（或对学生重置 staff 登录），引导去大学登录 |
| `INVALID_CREDENTIALS` | 401 | staff 登录 zID 或密码不对 |
| `ACCOUNT_NOT_ACTIVATED` | 403 | staff 还没用邀请码激活 |
| `INVALID_INVITE_CODE` | 400 | zID 或邀请码不对，找 Manager 要新码 |
| `ACCOUNT_DEACTIVATED` | 403 | 账号已停用 |
| `ROLE_CHANGE_NOT_ALLOWED` | 409 | 角色创建后固定，Student／Admin／Manager 不能互转 |
| `PREREQUISITE_REQUIRED` | 409 | 先通过前置 induction（如 General）再提交／通过这一项；`details.prerequisite_id` |
| `PREREQUISITE_CYCLE` | 409 | 前置设置会形成循环 |
| `FORBIDDEN` | 403 | 学生代别人预约、非 Manager 改期，或 Admin 调用 Manager 接口 |
| `BOOKING_TOO_SOON` | 400 | 需至少提前 7 天；`details.earliest_date` 为最早可约日期 |
| `BOOKING_TOO_FAR_AHEAD` | 400 | 最多提前 30 天；`details.latest_date` 为最晚可约日期 |
| `QUALIFICATION_ALREADY_PENDING`／`QUALIFICATION_ALREADY_VERIFIED` | 409 | 保留当前资料，刷新资格状态 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同一 key 不能用于另一份请求；新操作生成新 key |
| `DUPLICATE_BOOKING` | 409 | 当前学生已对同一资源提交重叠时段的有效申请；显示已有申请而不是再次加入候补 |
| `REQUEST_NOT_REVIEWABLE`／`ALREADY_REVIEWED` | 409 | 队列状态已改变，刷新列表 |
| `REQUEST_NOT_CANCELLABLE` | 409 | 预约已开始或请求已结束，刷新预约 |
| `REQUEST_NOT_RESCHEDULABLE` | 409 | 只有未来且已批准的预约可以改期，刷新预约 |
| `INVALID_TIME`／`INVALID_TIME_INCREMENT`／`INVALID_SLOT_COUNT`／`OUTSIDE_OPENING_HOURS`／`DURATION_LIMIT` | 400 | 根据资源与普通预约 slot 规则修正时间 |
| `VALIDATION_ERROR` | 400 | 在对应字段展示 `details` 错误，包括附件格式／大小问题 |
| `TOKEN_EXPIRED`／`INVALID_TOKEN` | 401 | 重新登录 |
| `ACCOUNT_FROZEN` | 403 | 这个人因多次缺席被冻结，`details.frozen_until`；引导去“我的预约”提交解冻申请 |
| `WEEKLY_LIMIT_REACHED` | 409 | 本周有效申请加上本次申请会超过 24 个半小时 slots；读取 `limit_slots`、`used_slots`、`requested_slots`、`remaining_slots`、`slot_minutes`、`week_start` |
| `FUTURE_BOOKING_LIMIT_REACHED` | 409 | 这个人已有 8 个有效未来预约；读取 `limit`、`used`、`requested`、`remaining`，引导用户取消一个不再需要的预约 |
| `RESOURCE_NAME_TAKEN` | 409 | 资源管理：另一个未下架的资源已经用了这个名称 |
| `KIND_IS_FIXED` | 409 | 资源管理：房间和设备之间不能互改，新建一个再下架旧的 |
| `RESOURCE_HAS_BOOKINGS`／`ROOM_HAS_EQUIPMENT` | 409 | 下架被拒：还有未来预约（`details.booking_count`）／房间里还有设备（`details.equipment`） |
| `CHECK_IN_NOT_OPEN`／`CHECK_IN_CLOSED` | 409 | 还没到确认时间（`details.check_in_opens_at`）／已经过了 |
| `NOT_FROZEN`／`UNFREEZE_ALREADY_REQUESTED` | 409 | 没有被冻结／已有待处理的解冻申请 |
| `SERIES_TOO_LONG`／`SERIES_EMPTY` | 400 | 重复预约超过 14 周／没有符合的日期 |
| `SERIES_CONFLICT` | 409 | 有问题的日期没有放进 `skip_dates`；重新预览 |

学生提交冲突请求会得到 201 和 `WAITLISTED`；`BOOKING_CONFLICT` 是管理员试图批准仍冲突的请求时的错误。不要把“收到 201”或“等待管理员”显示成已获批准。

API 输出时间为 ISO 8601 UTC `Z`。前端用 `Australia/Sydney` 显示，支持夏令时；不能硬编码全年 `+10:00`。availability 的 `date` 是资源时区日期，`slots` 的时间仍是 UTC。前端应标明本地时区。

预约相关读取／操作会由服务器推进到期状态（审批期限到期后的自动决定、过期、候补递补），浏览器不需要自己计时。需要轮询或用户刷新才能更新屏幕；人工审批后的实时通知尚未实现。

## 与后续接入的边界

前端只调用 API，不读取数据库，不直接连接 Outlook。数据库由后端的 `Repository` 适配器负责（内存或 PostgreSQL），以后接入学校 SSO 时由后端验证身份并映射用户。接入这些时，接口结构和状态保持不变。

演示身份选择仅在本地开发模式开启，不代表正式 SSO。正式前端不得保留任意 zID 登录或选择管理员身份的演示入口。内存模式的数据在后端重启后丢失，也不能跨多个后端进程共享；需要保留数据时用 PostgreSQL 模式。

## 日历订阅链接

- `GET calendar/link/` 返回 `{ path, created_at }`。`path` 是相对地址（例如 `/api/v1/calendar/<随机码>.ics`），前端拼上 `window.location.origin` 得到完整地址，让用户复制。
- 用户在 Outlook 里选“添加日历 → 从 Internet 订阅”，粘贴地址即可，不需要登录微软。Google 日历和苹果日历也能用。
- 订阅内容是本人作为预约人的**已批准**预约（包括员工替他建的），从 60 天前结束的开始。每条预约 UID 固定（`<预约 ID>@smartlab`），改期是更新，取消后消失。
- 地址里的随机码是唯一的钥匙：`POST calendar/link/reset/` 生成新地址，旧地址立即返回 404。页面上要提醒用户别把链接发给别人。
- 更新频率由日历软件决定，可能要几个小时。

## 站内通知

- `GET notifications/` 返回 `{ count, unread_count, results }`，最新在前；`unread=true` 只看未读，`limit` 1–200（默认 50）。`unread_count` 是全部站内可见的未读数，不含只发邮件的记录（Sprint 3，1.19.0）。
- 每条有 `kind`、`title`、`body`、`created_at`、`link`（站内页面，例如 `/bookings`、`/induction`、`/admin/bookings`）、`booking_id`、`read_at`。
- 会发通知的事：
  - 给预约人：`BOOKING_SUBMITTED`（自己提交的申请已收到，说明现在等审批还是在候补）、`BOOKING_APPROVED`、`BOOKING_REJECTED`（含系统自动决定、候补递补时不合格、资料被拒连带拒绝）、`BOOKING_PROMOTED`（候补转为待审批）、`BOOKING_RESCHEDULED`、`BOOKING_CANCELLED`（被员工取消）、`BOOKING_CREATED_FOR_YOU`、`SERIES_CREATED`（员工自己的重复预约）、`SERIES_CREATED_FOR_YOU`、`QUALIFICATION_VERIFIED`／`QUALIFICATION_REJECTED`、`NO_SHOW_RECORDED`、`ACCOUNT_FROZEN`、`UNFREEZE_APPROVED`／`UNFREEZE_REJECTED`、`ACCOUNT_UNFROZEN`，以及提醒：`BOOKING_REMINDER`（已批准的预约开始前 24 小时，提醒点 I'm here）、`INDUCTION_EXPIRING`（已通过的 induction 14 天内到期，链接到 `/induction?requirement=…`）、`BOOKING_EXPIRED`（候补或待审批的申请到开始时间还没轮到或没人决定）。每条提醒只发一次。
  - 给 Manager：`URGENT_REQUEST`。
  - 1.16.0 新增：`CHANGE_REQUESTED`／`CHANGE_APPROVED`／`CHANGE_REJECTED`（申请改期），`RESOURCE_OUT_OF_SERVICE`（你有预约或申请的资源进入维修或关闭，带 Manager 写的原因；每个预约一条）和 `RESOURCE_REOPENED`（重新开放）。这些也在默认的邮件类型里。
- 普通新申请不通知管理员（看审批队列）；自己取消不通知。
- 前端：顶部铃铛显示未读数，打开页面、切回页面和每 60 秒读一次。点一条就 `POST notifications/{id}/read/` 并跳到 `link`；“全部标为已读”用 `POST notifications/read-all/`。只跳站内路径。
- 邮件：后端打开邮件渠道后（`EMAIL_ENABLED=true`），上面列出的预约结果、提醒和确认类通知也会发到预约人的大学邮箱，见 [email-setup.md](email-setup.md)。是否发邮件还取决于本人该类别的 `email` 偏好；邮件类型和站点配置仍然生效。独立渠道接口见下面 1.19.0。

## 到场确认与冻结

- 预约响应新带：`attendance`（`CHECKED_IN`／`NO_SHOW`／`EXCUSED`／`NOT_TRACKED`／`null`）、`checked_in_at`、`check_in_open`、`check_in_opens_at`、`check_in_closes_at`。
- `check_in_open=true` 且当前用户就是预约人（`student_id`）时，“我的预约”显示 **I'm here** 按钮，调用 `POST bookings/{id}/check-in/`（`{}`）。窗口默认是开始前 15 分钟到开始后 30 分钟（不超过结束时间）。别人点返回 404，太早 409 `CHECK_IN_NOT_OPEN`，太晚 409 `CHECK_IN_CLOSED`。
- 窗口结束仍未确认，服务器记为 `NO_SHOW`；那段时间资源维修或关闭的记为 `EXCUSED`，不算缺席。
- 第 4 次缺席时冻结 30 天：`auth/me/` 的 `booking_frozen=true`、`frozen_until`，`no_show_count` 清零；这个人之后所有的预约和申请被取消（`reason_code=ACCOUNT_FROZEN`）；冻结期间新申请返回 403 `ACCOUNT_FROZEN`，员工也不能替他建，时段查询的 `can_request=false` 并带 `frozen_until`。员工被冻结时仍可以审批别人。
- 被冻结的人在页面上看到冻结提示，可以提交解冻申请：`POST account/unfreeze-requests/` `{"reason":"…"}`（1–1000 字，同一时间只能有一个待处理），`GET account/unfreeze-requests/` 看结果。
- Admin／Manager 的 **Booking freezes** 页面（`/admin/freezes`）：`GET admin/unfreeze-requests/?status=PENDING`、`GET admin/frozen-users/`；`POST admin/unfreeze-requests/{id}/review/` 同意或拒绝（拒绝要写原因），`POST admin/users/{id}/unfreeze/` 直接解冻。不能处理自己的申请（403 `SELF_REVIEW_FORBIDDEN`／`SELF_MODIFICATION_FORBIDDEN`）。解冻后被取消的预约不会恢复。

## 每周上限

- 同一受益人在同一周（资源当地时间周一到周日）里最多占用 24 个半小时 slots（12 小时）。待审批、候补、已批准和员工创建的循环预约都按实际时长计入；超过时 `POST bookings/` 返回 409 `WEEKLY_LIMIT_REACHED`，details 包含 `limit_slots`、`used_slots`、`requested_slots`、`remaining_slots`、`slot_minutes`、`week_start`。Manager 改期到超额周也一样。
- 取消、被拒、过期后 slots 自动释放；员工代建算在受益人头上。服务端在同一个数据库事务内重新计算额度，不能通过并发提交绕过。

## 有效未来预约数上限

- 同一受益人最多同时持有 8 个尚未开始的有效预约。`PENDING_APPROVAL`、`WAITLISTED`、`APPROVED` 和循环预约的每个日期都计入；第 9 个申请返回 409 `FUTURE_BOOKING_LIMIT_REACHED`。
- 取消、拒绝、过期或到达开始时间后名额自动释放；员工代建和紧急申请都算在受益人头上。一个已批准预约及其待处理改期申请合计只算一个，Manager 原地改期也不会额外占名额。
- 服务端在锁定受益人记录的数据库事务中重新计数；默认 8 来自 `MAX_ACTIVE_FUTURE_BOOKINGS`，可随客户政策调整。

## 重复预约（只有员工）

- 资源卡片上的 **Repeat weekly** 按钮（只有 Admin／Manager 看得到）打开表单：预约给谁（自己／输入 zID 替别人）、每周几（1=周一 … 7=周日）、开始时间、时长、起止日期（最长 14 周）、用途。
- 先 `POST bookings/series/preview/`（`resource_id`、`weekdays`、`start_time` 如 `"09:00"`、`duration_minutes`、`first_date`、`last_date`、可选 `on_behalf_of_zid`），返回每个日期的 `available` 和 `reason_code`。
- 再 `POST bookings/series/`（同样的字段加 `purpose`、`skip_dates`）。预览里不可用的日期必须放进 `skip_dates`，否则 409 `SERIES_CONFLICT`（重新预览）。冲突的日期不进候补。
- 创建后每个日期直接是 `APPROVED`（`reason_code=SERIES_CREATED_BY_STAFF`，带 `series_id`），不走审批。可以突破“最多提前 30 天”，其余规则照常检查；每个保留日期计入对应周的 24-slot 上限和 8 个有效未来预约上限，超额日期在预览中分别显示 `WEEKLY_LIMIT_REACHED` 或 `FUTURE_BOOKING_LIMIT_REACHED`；到场确认照常要求。
- 取消单次用 `POST bookings/{id}/cancel/`；取消整组剩下的用 `POST bookings/series/{id}/cancel/`（员工）。`GET bookings/series/{id}/` 返回这组的所有日期。

## 资源管理（只有 Manager）

页面 **Resources**（`/manager/resources`）。规则都在后端 `booking/services/resources.py`，前端 `features/manager/resource-form.ts` 只是提前给出同样的提示。

- `GET admin/resources/`：所有资源，包括已下架的（`active=false`）。普通的 `GET resources/` 只返回未下架的。
- `POST admin/resources/`：`kind`（`ROOM`／`EQUIPMENT`）、`name`、`location`、`required_qualification_id` 必填；可选 `description`、`room_id`、`category`（只有设备能填）、`slot_minutes`（15／30／60，默认 30）、`max_booking_minutes`（默认 480）、`opening_time`／`closing_time`（`"HH:MM"`，默认 08:00／20:00）、`pending_hold_minutes`（默认 1440）。成功 201 返回资源。
- `PATCH admin/resources/{id}/`：只发要改的字段。返回 `{resource, bookings_outside_rules}`。后者是不再符合新规则的未来预约（每项是带 `student`、`resource_name` 和 `problem` 的预约，`problem` 如 `OUTSIDE_OPENING_HOURS`），它们**不会被自动取消**，页面应提示 Manager 去处理。发 `kind` 返回 409 `KIND_IS_FIXED`。
- `POST admin/resources/{id}/archive/`：下架，`{}`。还有未来预约（409 `RESOURCE_HAS_BOOKINGS`）或房间里还有未下架的设备（409 `ROOM_HAS_EQUIPMENT`）时被拒。`POST …/restore/` 恢复（名称仍须没被占用）。
- 校验错误是 400 `VALIDATION_ERROR`，`details` 里是出错的字段名，例如 `{"max_booking_minutes": ["…"]}`。

## 预约记录与使用情况（Admin 和 Manager）

页面 **Booking Records**（`/admin/records`），两个标签：

- **Records**：`GET admin/bookings/?status=ALL&since=&until=&resource_id=&q=`。日期是悉尼当地日期，前端换成带时区的时间（`since` 是起始日 0 点，`until` 是结束日后一天 0 点）。表格列：时间、资源、预约人（姓名和 zID）、创建人（`on_behalf` 为 false 时显示 Self）、状态、到场。**Export CSV** 用同样的参数调 `admin/bookings/export/`，所以 CSV 和表格一致。
- **Usage statistics**（`?tab=usage`；旧地址 `/manager/usage` 会跳过来）：见下文。

### 使用情况报表

`GET admin/reports/usage/?first_date=2030-01-01&last_date=2030-01-28`（当地日期，都包含，最多 366 天）返回 `{first_date, last_date, days, results, totals}`。`results` 每行一个资源：`approved`、`booked_hours`、`open_hours`、`utilisation`（0–1）、`checked_in`、`no_show`、`excused`、`not_tracked`、`attendance_rate`（还没有可算的时为 `null`）、`cancelled`、`rejected`，以及 `name`、`kind`、`category`、`room_name`、`active`。到场数字只算已经结束的已批准预约。

## 修改密码（Admin／Manager）

Account 页面上的表单：`POST auth/change-password/` `{"current_password": "…", "new_password": "…"}`，成功返回 `{"changed": true}`。当前密码不对 400 `INVALID_CREDENTIALS`；新密码少于 8 位或和当前相同 400 `VALIDATION_ERROR`；学生 403 `STUDENT_USES_SSO`。

## 预约页筛选与一天空闲表

Book a Resource 页面有两个标签：**Browse resources**（资源卡片）和 **Find a free time**。后者先选条件，再在一张表里看所有资源当天的空闲情况，点空闲时间直接打开预约表单（资源和时间已选好）。

- 资源的 `category`（设备类别，例如 `Microscopy`、`Electronics testing`、`Fabrication`；房间为 `null`）。演示类别是编的，以后换成客户的设备清单。`GET resources/` 也可以带 `category=` 筛选。
- `GET resources/day-overview/` 的参数：
  - `date`：必填，悉尼当地日期。
  - `duration_minutes`：默认 60。1.16.0 起，某个资源不能按这个时长预约（超过它的最长时长，或不是它时间步长的倍数）时，这个资源不显示并计入 `too_long`，不再让整个请求 400。
  - `kind`：`ROOM`／`EQUIPMENT`。
  - `room_id`：房间本身加上放在这个房间里的设备。
  - `category`：设备类别。
  - `q`：按名称、地点或类别搜索。
  - `bookable_only=true`：只返回当前用户现在就能申请的资源。
  - `free_at=HH:MM`：只返回从这个时间起、整个时长都空闲的资源。
- 返回内容：
  - `date`、`duration_minutes`、`timezone`
  - 预约窗口：`earliest_date`、`latest_date`、`min_advance_days`、`max_advance_days`
  - `rooms`（`id`、`name`）和 `categories`，用来生成筛选下拉框
  - `count`、`results`。每行是 `resource`（完整资源对象）、`room_name`、`can_request`、`qualification_status`、`resource_status`、`status_reason`、`slots`
  - `slots` 和 `resources/{id}/availability/` 的格式完全相同，规则也是同一套：开放时间、预约窗口、induction、冲突、维修状态。
  - 1.16.0：`too_long`（因时长不显示的资源数）和 `not_bookable`（`bookable_only=true` 时被隐藏的资源，按原因计数，例如 `{"NOT_SUBMITTED": 18, "MAINTENANCE": 1}`；原因是 `MAINTENANCE`／`CLOSED`、`FROZEN` 或 induction 状态）。前端用它说明“为什么什么都没有”，有 induction 原因时给出 Induction & Training 的链接。前端的时长选项到 8 小时。
- 前端点击空闲格子后打开 BookingForm，并传入 `initialDate`、`initialStart`、`initialMinutes`，SlotPicker 会自动选中这段时间。只有当这段时间全部空闲时才会自动选中。

## Outlook 同步

网站是预约的唯一依据，Outlook 里的改动不能变成网站上的预约。

- 系统只做"网站 → Outlook"的单向写入，运行时从不读取 Outlook 里的修改，所以 Outlook 里的改动不可能影响预约。
- 前端只显示同步结果，不连接 Outlook，也不保存任何微软凭证。
- 配置和实测步骤见 [outlook-setup.md](outlook-setup.md)。

所有预约响应（列表、详情、dashboard、创建、取消、审核、改期、`admin/process-due/` 的结果）都带 `outlook_sync`，它和预约的 `status` 互相独立：

```json
{
  "status": "APPROVED",
  "outlook_sync": {
    "status": "SYNCED",
    "action": "CREATE",
    "web_link": "https://outlook.live.com/calendar/item/...",
    "last_error": null
  }
}
```

| outlook_sync.status | 前端显示 |
| --- | --- |
| `DISABLED` | 日历同步未启用；预约状态仍有效 |
| `NOT_REQUIRED` | 当前申请无需写入日历（待审批、候补、被拒等） |
| `PENDING`／`IN_PROGRESS` | 日历等待同步／同步中 |
| `SYNCED` + `CREATE`／`UPDATE` | 已写入 Outlook（改期更新的是同一个事件；如果用户删过事件，就按新时间重建） |
| `SYNCED` + `DELETE` | 取消已同步到 Outlook |
| `FAILED` | 预约结果已保存，日历同步失败；提示联系管理员 |

只按预约的 `status` 判断是否批准或取消，不要把日历同步失败提示成"预约失败"。读取接口不会调用微软；需要刷新时，轮询预约详情或 dashboard 即可。

**员工页面 Calendar Sync**（`/admin/calendar-sync`，Admin 和 Manager）是开发阶段的可视化页面，数据来自 `GET admin/outlook/`，返回内容如下：
- `summary`：`total`、`synced`、`pending`、`failed`。
- `items`：每个已同步的预约一行，失败的排在最前。字段有：
  - `booking_id`、`booking_status`、`start`、`end`、`urgent`
  - `resource`、`booked_for`、`booked_by`（代预约的员工）、`invited`
  - `sync`：`status`、`action`、`attempts`、`last_error`、`next_attempt_at`、`last_success_at`、`web_link`
- `last_check`：最近一次 `POST admin/outlook/check/` 的结果。
- `invite_mode`、`enabled`、`configured`、`mode`、`direction`、`sync_records`。

其他规则：
- 同步未启用时，`outlook-retry` 返回 409 `OUTLOOK_DISABLED`。
- 学生调用这些接口一律返回 403。
- 正式交付前如果删掉这个页面，后端接口可以保留。

## 1.16.0：申请改期、维修通知、联系方式和员工首页

### 申请改期（预约人）

- 已批准、还没开始的预约，预约人本人可以在 My Bookings 点 **Change time**，选新时间后 `POST bookings/{id}/change/` `{"start": "…", "end": "…"}`（可带 `Idempotency-Key`）。同一资源，用途沿用原预约。Manager 仍然用 Reschedule 直接改。
- 后端新建一个申请，`replaces_id` 指向原预约。新时间空闲：`PENDING_APPROVAL`，正常审批；新时间已被别人预约或占着：`WAITLISTED`。前端在选到被占用的时间时先提示“只能进候补”，按钮和确认框也会写明。
- **原预约在新申请批准前一直有效。** 新申请被批准（Admin 手动、审批期到了系统自动、或候补转正后批准）的那一刻，原预约自动取消（`reason_code=REPLACED_BY_CHANGE`），它的时间交给候补队列。新申请被拒、撤回或过期，原预约不变。
- 规则和普通申请相同（预约窗口、开放时间、时长、induction、冻结、每周上限）；原预约本身不算冲突、不算重复、也不在每周上限里多算一次。不支持紧急改期。
- 一个预约同时只能有一个待处理的改期（409 `CHANGE_ALREADY_REQUESTED`，`details.booking_id` 是那个申请）；不是自己的预约 404／403；不是已批准的未来预约 409 `REQUEST_NOT_CHANGEABLE`；时间和现在一样 400。
- 预约 JSON 新字段：`replaces_id`、`replaces_booking`（改期申请指向的原预约：`id`、`start`、`end`、`status`）、`open_change`（原预约上还在等的改期申请，同样四个字段）。My Bookings 用它们在两张卡片上互相说明；Booking Review 在时间下面显示“Change from …”。

### 维修和关闭的通知

- Manager 把资源改成 `MAINTENANCE` 或 `CLOSED` 时，所有在这个资源上有未来预约或申请的人都会收到 `RESOURCE_OUT_OF_SERVICE`（按本人的站内／邮件偏好），内容带 Manager 写的原因；已批准的预约**仍然保留**，由 Manager 决定改期或取消（改期、取消会另发通知）。改回 `AVAILABLE` 时发 `RESOURCE_REOPENED`。只改原因不改状态不重复通知。房间的状态不影响里面的设备，所以设备的预约人不会收到。
- Room Management 的确认框列出受影响的预约，并说明会自动通知；下面的列表把不能照常进行的预约标出来。

### 实验室联系方式

- `GET site/contact/` 返回 `{id, email, phone, hours, note, updated_at, updated_by}`，没设置时都是空字符串。`PATCH site/contact/`（只有 Manager）只改发送的字段，空字符串表示清空，`email` 要像邮箱地址，写 `SITE_CONTACT_UPDATED` 审计。
- 显示在 Help 页面、已批准预约卡片（“Contact the lab”，邮件主题和正文已带资源、时间和预约编号）和每项 induction 的说明下面。只显示填了的字段。

### 员工首页 Today

- Admin 和 Manager 登录后进入 `/admin/today`（以前分别是 Qualification Review 和 Room Management）。
- `GET admin/overview/` 返回：`pending_inductions`、`pending_bookings`（不含紧急）、`urgent_requests`、`waitlisted`、`changes_waiting`、`due_soon`（6 小时内到审批期限的待审申请，最多 10 个）、`unfreeze_requests`、`out_of_service`（`[{resource, affected_bookings}]`）、`today`（今天开始的已批准预约，最多 10 个）、`today_count`、`missed_today`、`can_decide_urgent`。每张卡片链接到处理它的页面。

### 其他界面改动

- Booking Review 列表加了 Purpose 列和 Details 按钮（整行点开也可以）。
- 预约表单：Purpose 标为必填，按钮灰着时直接说还差什么；在最早可约的那天会提示“更早要走紧急申请”，可以一键切换；时间条下面可以直接选开始时间和时长；手机上提交按钮和所选时间固定在弹窗底部。
- 资源设置表单的“最长预约”和“审批期”用小时填写（接口仍是分钟）。
- 日历订阅分别给出 Outlook、Google 和 Apple 的步骤，并说明更新会有延迟、以网站状态为准。

## 1.17.0: functional controls

### Urgent explanation and evidence

Urgent booking requests still require both `purpose` and `urgent_reason` in `POST bookings/`. The UI collects one **Purpose and urgency** value and sends it in both fields (up to 500 characters). Ordinary booking requests retain their separate Purpose field. Qualification submissions still require a multipart `file`; UI validation does not replace the server's size, MIME and file-content validation.

### Opt-in local test session

- `GET auth/config/` adds `test_console_enabled`. It is true only when `DEBUG=true`, `ENABLE_DEMO_AUTH=true`, `ENABLE_TEST_CONSOLE=true`, `AUTH_PROVIDER=booking.authentication.DemoIdentityProvider` and `REPOSITORY_FACTORY=booking.repository.MemoryRepository` (the in-memory store; with PostgreSQL it stays off). Any disabled condition hides the login endpoint (404) and invalidates existing test tokens (401). Default: disabled.
- `POST auth/test-login/` accepts exactly `{ "login_id": "1" }`; no password. Returns the usual session envelope with a signed token and user (`zid="1"`, initial `role="STUDENT"`, `test_account=true`, `bypass_booking_rules=true`). Database `id` remains a UUID. The stored role stays STUDENT.
- `POST auth/test-session/`, authenticated with that test token only, accepts `{ "role": "STUDENT" | "ADMIN" | "MANAGER", "bypass_booking_rules": true | false }`. It returns a fresh signed session. Replace the token and verify with `auth/me/`. Ordinary accounts receive 403 and cannot obtain overrides by adding fields to booking requests. Switching a session does not mutate another tab's already-issued token.
- Bypass applies to the test account's own bookings, moves and staff weekly series. Free valid future times become APPROVED immediately (`TEST_OVERRIDE` for single bookings); account freeze, induction, 7–30 day window, opening hours, resource maximum duration, maintenance/closed status and weekly booking limit are bypassed. Archived resources remain unavailable. Single appointments are limited to 24 h; staff series to 52 weeks. Existing bookings and held requests cannot be displaced. Booking for someone else uses that person's normal rules. Turning bypass off restores normal booking windows and approvals; account 1 retains its automatically granted inductions.
- With bypass, availability and day-overview add `test_bypass=true`; `latest_date=null` means no upper calendar-date restriction and date inputs must omit `max`. `min_advance_days` and `max_advance_days` are 0. Single-resource availability adds `max_booking_minutes=1440` and `review_window_minutes=0`; slots cover the local calendar day and preserve past-time/conflict blocks. Normal sessions continue returning their normal window dates. Display a test-override label.
- Self time changes return APPROVED immediately and cancel the replaced original booking. Test attendance is NOT_TRACKED. Website notifications and audit remain; no test booking is sent to Outlook or external notification channels.

All test UI copy is English. This is a local testing facility; keep it disabled on deployed services.

### 1.17.1: account 1 owns every induction

On login and authenticated test requests, account 1 receives every induction as VERIFIED with `valid_until=null`, including requirements added after sign-in. This applies in Student, Admin and Manager views even with booking-rule bypass off. Grants are idempotent, explicitly marked as test access, have no uploaded file and return `file_id=""`, `file_url=""`. The induction UI omits the upload form for this account. Ordinary users still need valid evidence and manual review. No database migration or external notification is involved; the existing local-memory-only gate remains required.

## 1.19.0：独立通知渠道与公告（Sprint 3）

### 通知设置

三种角色均可访问 `#/settings/notifications`；Account 页只放 **Notification settings** 链接。五类为 `bookings`、`reminders`、`induction`、`account`、`resources`。

`GET notifications/preferences/` 及 `PUT` 的响应为：

```json
{"results":[{"category":"bookings","in_app":true,"email":true}],"email_available":false}
```

示例只列一项，实际固定返回全部五类。没有偏好的类别两列都为 true。`email_available` 来自站点 `EMAIL_ENABLED`，不表示 Gmail／Outlook 已连通或邮件必然送达。为 false 时前端禁用邮件列并整列显示为不勾选，显示 **Email is not switched on for this site.**；接口仍返回并保留已保存的选择。

```json
{"preferences":{"bookings":{"in_app":false,"email":true},"resources":{"email":false}}}
```

PUT 只改传入的列；未知类别、未知列、空的列对象返回 400，整次不保存。偏好按当前登录人保存。四种组合分别为站内及邮件、仅站内、仅邮件、都不发。每条通知记录保存生成时的 `in_app` / `email`：仅邮件的记录不在 `notifications/`、未读数或 read-all 中出现，以后开启站内也不补进铃铛。Manager 的 `URGENT_REQUEST` 不属于可关闭的个人类别。

### 公告接口

| 方法 | 路径 | 权限与返回 |
| --- | --- | --- |
| GET | `announcements/` | 登录人；`{count,results}`，只含未下架、未过期的公告，创建时间降序 |
| GET | `announcements/?include_ended=true` | Admin / Manager；包含已结束记录，学生 403 |
| POST | `announcements/` | Admin / Manager；`{title,body,expires_at?}`，201 |
| PATCH | `announcements/{id}/` | 仅手动公告作者；部分修改 `title`、`body`、`expires_at`，200 |
| POST | `announcements/{id}/remove/` | 作者或 Manager；空对象，软下架，200；重复下架不重复审计 |

学生调用任何公告写接口先返回 403，包括无效请求体；不会先返回表单错误。`title` 为去空白后 1–120 字符，`body` 为 1–1000 字符；`expires_at` 为带时区的 ISO 日期时间或 null（一直保留）。请求不能指定 `kind`、`resource_id`、作者、状态等字段，指定即 400。Manager 可以下架别人的手动公告，不能修改；Admin 不能改或下架别人的。状态公告通过这些写接口返回 403。

每条公告含 `id,title,body,kind,resource_id,created_by,created_at,expires_at,removed_at,removed_by,updated_at,author_role,expected_back`，另带 `author:{id,display_name,role}` 和 `active`。`author_role` 为发布时角色，署名显示姓名及角色。不存在返回 404；已下架的手动公告不能再改（409）。创建、修改、下架均写审计，但不会产生通知。

### 资源状态公告

`PATCH admin/resources/{id}/status/` 仍仅 Manager 可用，Admin 403；请求在原 `status,reason` 上增加可选 `expected_back`（带时区 ISO 或 null）。不提交时视作没有估计。响应结构仍为 `{resource,affected_bookings}`；对应公告通过公告列表读取。

`set_resource_status` 对房间及设备在原事务内创建／更新 `RESOURCE_STATUS` 公告，原因作为正文，状态变更 Manager 作为署名；每个资源同时只保留一条未下架的状态公告。改原因不产生第二条；`AVAILABLE` 自动下架。`expected_back` 单独存储、仅用于展示，不自动过期或重开资源，已过估计时间仍显示公告，直至 Manager 改回可用。原 `RESOURCE_OUT_OF_SERVICE` / `RESOURCE_REOPENED` 通知逻辑保留。

首页 Dashboard / Today 只加载生效公告，空列表不渲染公告区；员工管理页标注 **From room status**，不提供状态公告修改或下架按钮。页面日期输入按 Australia/Sydney 转为 ISO，夏令时不存在的时间显示错误并保留输入；弹窗错误显示在弹窗内。

## 1.20.0：个人历史移除（Sprint 3）

- `POST bookings/{id}/remove-from-history/`：空请求或 `{}`，成功为 `204` 无响应体。重复调用仍为 `204`。
- 仅预约受益人（`student_id`）或创建人（`created_by`）可移除自己的条目。员工也不能移除无关预约的个人历史，返回 `404`。身份由服务端取得，不接受 user_id 等额外字段（`400`）。
- `CANCELLED`、`REJECTED`、`EXPIRED` 或 `end <= now` 可移除；未来／进行中的有效预约返回 `409 BOOKING_NOT_HISTORY`，先取消／撤回。每个重复预约日期独立处理。
- `GET bookings/` 与 `GET dashboard/`（包括 counts）排除当前用户移除的条目。代约的双方互不影响。详情接口、员工 records/CSV/usage、原预约及缺席／冻结、通知、日历均不变；不发取消或移除邮件。
- 前端按钮 `Remove from my history`；确认框说明保留员工记录。失败保留可见条目，成功才移除。My bookings 的 Resource 与状态分类取交集，URL `view` / `resource` 记住条件；不新增后端筛选参数。
