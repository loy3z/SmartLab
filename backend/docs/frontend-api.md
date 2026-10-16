# Sprint 1 前端交接

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
| 管理员资格审核 | 审核列表、查看资料、通过／拒绝和原因；显示后端返回的有效期 | 修改资格、自动设定有效期；通过时重新判断等待资格的预约，拒绝时自动拒绝该学生依赖此资格的 Pending 预约 |
| 管理员预约审核 | 审核队列、详情、通过／拒绝和原因、显示冲突错误 | 批准前再次检查资格与冲突 |
| 审计记录 | Admin／Manager 按资源、学生、操作、时间筛选并分页查看；预约详情可显示该预约的历史 | 记录并查询申请、审批、改期、取消和资格审核轨迹 |
| 人员与角色管理（仅 Manager） | 人员列表、按角色筛选；Add staff | 只允许 Manager；角色创建后固定，不能互转；不能改自己；至少保留一个 Manager；写审计 |
| Manager 审批期限 | 按资源显示和修改审批期限分钟数 | 角色校验、规则保存和审计；Admin 不能读取或修改 |

隐藏按钮只能改善体验；身份、资格和冲突均由后端执行。前端不能直接设置预约状态、资格状态或用户角色。

演示学生注册需要 `zid`、`display_name`、`university_email`，缺少或格式错误的邮箱返回 400。登录／注册响应中的用户对象以及 `auth/me/` 均返回邮箱。演示模式不验证邮箱所有权；正式 SSO 的邮箱及角色必须由后端从可信身份来源映射。

## 两个登录入口（staff 登录）

- **学生**：`POST auth/demo-login/`（模拟大学登录，只要 zID）。staff 的 zID 返回 403 `USE_STAFF_SIGN_IN`。
- **Admin／Manager**：`POST auth/staff-sign-in/`，请求 `{"zid":"z9000002","password":"…"}`，返回与学生登录相同的 `{access_token, user, …}`。错误：401 `INVALID_CREDENTIALS`（zID 或密码不对）、403 `ACCOUNT_NOT_ACTIVATED`（还没激活）、403 `ACCOUNT_DEACTIVATED`、403 `STUDENT_USES_SSO`（学生用了 staff 入口）。
- **首次激活**：`POST auth/staff-activate/`，请求 `{"zid":"…","invite_code":"K7Q4-9MZD","password":"至少 8 位"}`。邀请码不区分大小写，可以不带横线；成功后直接登录并作废邀请码。错误：400 `INVALID_INVITE_CODE`、400 `VALIDATION_ERROR`（密码太短）、403 `ACCOUNT_DEACTIVATED`。
- **邀请码从哪来**：Manager 用 Add staff 新建账号后，`admin/users/` 里该员工的 `activation_status` 为 `AWAITING_ACTIVATION`，`invite_code` 就是邀请码；激活后变成 `ACTIVATED`，`invite_code` 为 `null`。学生这两个字段都是 `null`。
- **重置**：`POST admin/users/{id}/reset-access/`（仅 Manager，不能对自己，不能对学生：409 `STUDENT_USES_SSO`），旧密码失效并生成新邀请码，返回更新后的用户。
- `auth/config/` 新增 `staff_sign_in_enabled`。两个入口目前都只在演示模式（`DEBUG` + `ENABLE_DEMO_AUTH`）可用；接入学校 SSO 后再替换。
- 演示账号：z9000001（Admin）、z9000002（Manager），密码 `smartlab-staff-demo`。

## 角色（第 5 周起）

- **Student**：唯一会预约的角色，可以看到资源、预约和 induction 页面。
- **Admin**（员工）：审核 induction 和预约申请，查看审计；**不预约**，也不能访问任何 Manager 页面或接口（403）。
- **Manager**（员工）：拥有 Admin 的全部权限，另外管理人员、资源状态、审批期限和所有预约；**不预约**。
- Student、Admin、Manager 是三种分开的账号，角色在创建时确定：学生不会被“升级”为 Admin，Admin 和 Manager 也不能互相切换。员工账号由 Manager 用 Add staff 创建，以后可由学校身份系统提供。员工调用 `POST bookings/`、`POST qualifications/` 返回 403 `FORBIDDEN`。
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

### 审计记录（OpenAPI 1.3.0 起）

`GET admin/audit/` 仅 Admin／Manager 可用，学生返回 403。返回 `{ count, limit, offset, results }`，`count` 是筛选后的总数（分页前），`results` 按时间从新到旧。每条记录含 `action`、`entity_type`、`entity_id`、`at`、`details`，以及 `actor`（`zid`、`display_name`、`role`；系统自动处理时 `actor_id` 为 `SYSTEM`、`actor` 为 `null`）。

- 某个预约的完整历史：`?entity_id={booking_id}`。
- 某个资源：`?resource_id=...`，包括该资源所有预约的记录和占位规则修改。
- 某个学生：`?student_id=...`，包括该学生的操作及其预约、资料和账号相关记录。
- 其他筛选：`action`（如 `BOOKING_CANCELLED`）、`entity_type`（`booking|qualification|resource|principal`）、`actor_id`、`since`／`until`（必须带时区，`until` 不包含）。
- 分页：`limit` 1–500，默认 100；`offset` 默认 0。未知参数返回 400。

`details` 的字段随动作不同，例如创建预约有 `status`、`reason_code`、`hold_until`，改期有 `old_start`／`new_start` 等。前端可直接显示键值，不要依赖固定字段。

### 人员与角色管理（OpenAPI 1.8.0 起，仅 Manager）

只有 **Manager** 能查看人员名单、新建员工、修改员工角色或停用账号；Admin 和学生访问这些接口返回 403。

- `GET admin/users/`：返回 `{ count, results }`，每项含 `id`、`zid`、`display_name`、`role`、`is_staff`、`active`、`university_email`，以及 `inductions`（每项 induction 的 `name`、`status`：`NOT_SUBMITTED`／`PENDING`／`VERIFIED`／`REJECTED`／`EXPIRED`、`valid_until`）和 `induction_status`（全部有效为 `VERIFIED`，否则 `INCOMPLETE`）。员工不预约，induction 只对学生有意义。可用 `role`、`active=true|false`、`q`（匹配 zID／姓名／邮箱）筛选。
- **Add staff**：`POST admin/users/staff/`，请求 `{"zid":"z5123456","display_name":"…","university_email":"…","role":"ADMIN"}`（`role` 为 `ADMIN` 或 `MANAGER`），成功 201 返回该用户，写 `ADMIN_CREATED`／`MANAGER_CREATED` 审计。zID 已存在返回 409 `USER_EXISTS`（现有学生不能变成员工）。旧接口 `POST admin/users/managers/` 保留，等同于 `role=MANAGER`。
- `PATCH admin/users/{id}/`：用来停用或恢复账号（`active`）。角色在创建时确定，不能修改：请求里的 `role` 与当前角色不同时返回 409 `ROLE_CHANGE_NOT_ALLOWED`（与当前相同则忽略）。要换人就用 Add staff 新建账号，再停用旧账号。修改在该用户的**下一次请求**生效；被停用的用户再请求会得到 401，前端应跳回登录页。
- **停用学生**会立即拒绝该学生所有未决申请（待审批和候补，`reason_code=ACCOUNT_DEACTIVATED`）并递补下一位；已批准的预约保留，由 Manager 决定是否取消。
- 不能修改自己（`SELF_MODIFICATION_FORBIDDEN`，403），系统至少保留一个启用的 Manager（`LAST_MANAGER`，409）。每次修改都会写一条 `USER_UPDATED` 审计记录。
- 列表里只有已经存在于系统中的用户（演示时由数据库预先写入，或登录／注册过一次）。

`dashboard` 返回 `{ bookings, qualifications, counts }`。两个列表是数组，`counts` 的键为六种大写预约状态，例如 `counts.APPROVED`；它不是资格数量或预约总数。其他列表接口使用 `{ count, results }`。

`qualification_status=NOT_CONFIGURED` 表示资源尚未设置 induction 要求，不能申请；需要维护资源数据后再开放。`qualification_status=PREREQUISITE_REQUIRED` 表示该资源的 induction 需要先通过另一项（如 Advanced 需要 General），此时 `missing_prerequisite_id` 给出缺少的那一项，前端可以直接链接到 `/induction?requirement=<id>`。

### 前置 induction（OpenAPI 1.8.0 起）

- `GET qualification-requirements/` 每项新增 `prerequisite_ids`（数组）。演示数据中 Advanced laboratory training 的 `prerequisite_ids` 是 General laboratory induction。
- 前置未通过时，提交该项资料返回 409 `PREREQUISITE_REQUIRED`（`details.prerequisite_id`），Admin 通过该项资料也返回同一错误；学生页面应显示“先完成 General”，并禁用上传。
- 预约需要该项 induction 的资源时，**前置和本项都必须有效并覆盖整个预约**；缺前置时 `POST bookings/` 返回 403 `QUALIFICATION_REQUIRED`，`details.qualification_status=PREREQUISITE_REQUIRED`、`details.prerequisite_id`、`details.prerequisite_status`。
- Manager 可用 `PATCH admin/qualification-requirements/{id}/` 设置 `{"prerequisite_ids":["<uuid>"]}`（最多 20 项，不能包含自己，不能形成循环：409 `PREREQUISITE_CYCLE`），写 `REQUIREMENT_PREREQUISITES_UPDATED` 审计。

### 房间和设备（OpenAPI 1.8.0 起）

资源新增 `room_id`：设备所在房间的 ID，房间本身为 `null`。前端按房间分组设备（“该房间的 N 台设备”）。房间的维修／关闭**只影响房间本身**，房间里的设备仍按各自的 `status` 预约。

可用性查询是当时的快照，提交前后仍可能有人占用时段。显示 `available=false` 的时段不能提示“可立即预约”；学生仍可对已被占用的时段提交申请，但会进入等待名单，界面应明确说明。每个资源的 `required_qualification_id` 可以不同，前端必须读取资源要求，不能用一个全局“已完成 induction”开关判断所有资源的资格。

`slots[]` 的 `reason_code` 为 `START_TIME_PASSED`、`RESOURCE_UNAVAILABLE`（维修／关闭）、`TOO_SOON`（不足 7 天）、`TOO_FAR_AHEAD`（超过 30 天）、`BOOKED`、`TEMPORARILY_HELD` 或 `null`。响应顶层另有 `earliest_date`、`latest_date`、`min_advance_days`、`max_advance_days`，供日期选择器限制范围。临时占位时返回 `hold_until`（UTC 截止时间）和 `held_by_me`（是否为当前学生自己的占位）；`requested_by_me` 表示当前学生已经对同一资源提交了与该时段重叠的有效申请，前端应禁用再次提交。接口不返回其他学生身份。可显示占位倒计时，到期刷新查询，最终以服务端响应为准；`can_request` 只有在当前用户是学生、账号启用、对应 induction（及其前置）已通过且有效、资源开放时才为 `true`，不代表所选时段会获批；为 `false` 时应禁用提交按钮并提示先完成 induction。`review_window_minutes` 是该资源的审批期限（默认 1440 分钟）。

### 审批流程（OpenAPI 1.7.0 起，按客户要求）

- **只有 induction 已通过且有效的学生才能申请**（员工不预约）。资料还在审核（`PENDING`）、被拒或已过期时，`POST bookings/` 返回 403 `QUALIFICATION_REQUIRED`，`details.qualification_status` 说明原因；有效期必须覆盖整个预约，否则为 `EXPIRES_BEFORE_END`。induction 只能由 Admin／Manager 人工审核，审核通过不会自动批准任何预约。
- **每个申请都先进入 `PENDING_APPROVAL`**（`reason_code=AWAITING_REVIEW`）：不算确认、不写 Outlook，但在审批期限内为申请人占住时段。`review_due_at`（与 `hold_until` 相同）是审批截止时间：进入待审批时加上资源的 `pending_hold_minutes`（默认 24 小时），不晚于预约开始。
- **Admin／Manager 在截止前批准或拒绝**（`POST admin/bookings/{id}/review/`，不能审批自己的申请）。
- **截止时仍无人处理**：系统自动处理，`reviewed_by="SYSTEM"`。账号启用、资格（含前置）仍覆盖整个预约、资源开放、时段无已批准冲突 → `APPROVED`（`AUTO_APPROVED_AFTER_REVIEW_WINDOW`）；否则 `REJECTED`（`AUTO_REJECTED_ACCOUNT_INACTIVE`／`AUTO_REJECTED_QUALIFICATION`／`AUTO_REJECTED_RESOURCE_UNAVAILABLE`／`AUTO_REJECTED_BOOKING_RULES`／`AUTO_REJECTED_CONFLICT`，`decision_reason` 写明原因）。由服务端在下一次访问、`admin/process-due/` 或定时命令 `manage.py process_due` 时处理，前端只需刷新。
- **同一套规则**：创建、人工批准、自动处理、候补递补、改期都使用后端同一个规则检查，结果一致。
- 原来的“120 分钟以内立即批准”、`auto_approve_max_minutes`、`needs_review`、`DURATION_REVIEW`、`RESCHEDULE_NEEDS_REVIEW`、资料审核中先预约（`WAITING_QUALIFICATION`、30 分钟占位、`HOLD_EXPIRED`、`PENDING_REQUEST_LIMIT`）都已移除。
- 改期：已批准的未来预约可以改日期、时间和时长（受预约窗口和资格限制），直接生效。选时段时传 `exclude_booking_id=<正在改的预约>`，学生自己原来的时间会显示为可选。
- Manager 通过 `PATCH admin/resources/{id}/booking-policy/` 按资源设置审批期限 `{"pending_hold_minutes":1440}`（1–20160 分钟）。

**房间／设备状态**：`PATCH admin/resources/{id}/status/`（仅 Manager），请求 `{"status":"MAINTENANCE","reason":"Fume hood repair"}`；状态为 `AVAILABLE`／`MAINTENANCE`／`CLOSED`，后两者必须填原因。
- 资源列表和详情新增 `status`、`status_reason`，维修／关闭的资源仍然显示，前端应标出“维修中／已关闭”和原因。
- 维修／关闭时：新申请返回 409 `RESOURCE_UNAVAILABLE`（`details.resource_status`、`status_reason`），时段查询所有时段为 `RESOURCE_UNAVAILABLE`、`can_request=false`；不批准、不递补。**已有预约保留**，响应的 `affected_bookings` 列出仍需处理的未来预约，Manager 可逐个用 `POST bookings/{id}/cancel/` 取消（`reason_code=CANCELLED_BY_STAFF`）。改回 `AVAILABLE` 后候补自动递补。

**所有人的预订**：`GET admin/bookings/` 新增筛选 `status`（单个、逗号分隔多个或 `ALL`）、`resource_id`、`student_id`、`since`、`until`（带时区的时间，返回与该时段重叠的预约），按开始时间排序；每项新增 `student`（`id`、`zid`、`display_name`、`university_email`）、`resource_name`、`resource_kind`。不带参数时仍是人工审批队列，原有页面不受影响。`GET admin/bookings/export/`（仅 Manager）用相同筛选导出 CSV（默认 `ALL`，UTF-8 带 BOM，可直接用 Excel 打开）；“打印”可由前端对列表页调用浏览器打印。

**Add staff**（人员管理页右上角按钮）：见上文“人员与角色管理”。删除人员请用停用（`PATCH active=false`），以保留预约和审计历史。

## 状态与界面文字

| 资格状态 | 显示含义 | 可以提交该资源预约？ |
| --- | --- | --- |
| 无提交记录 | 请先提交 induction 资料 | 否 |
| `PENDING` | 资料等待管理员审核 | 否，审核通过后才能申请 |
| 有效 `VERIFIED` | 已具备该资源资格 | 是 |
| `REJECTED` 或已过期 | 资料被拒绝／资格已过期，请重新提交 | 否 |

最新提交决定当前资格。`status` 是资料审核状态，额外的 `effective_status` 表示当前有效性，界面应结合该字段显示过期情况。有效期需要覆盖预约结束时间；在当前时刻有效，不一定覆盖用户选择的预约。已有 PENDING 提交或仍有效的 VERIFIED 提交时，不能重复上传相同要求的资料；拒绝或过期后可重新提交。

**有效期（OpenAPI 1.3.0 起）**：审核通过时后端自动设定 `valid_until = 审核时间 + QUALIFICATION_VALIDITY_DAYS`，默认 120 天（约一个学期）。审核请求不再接受 `valid_until`，带上该字段会返回 400。前端资格审核页去掉有效期输入框，改为显示响应里的 `valid_until`；学生端可显示“资格有效至 …”，并提示超过该时间的预约无法提交。资格过期前不能提前续期，过期后重新上传。

| 预约状态 | 建议显示 | 是否占时段 |
| --- | --- | --- |
| `PENDING_APPROVAL` | 等待管理员审批，显示审批截止时间 `review_due_at`，并说明超时后系统按规则自动处理 | 审批期内占位（`hold_active=true`） |
| `WAITLISTED` | 候补中，显示“候补第 `waitlist_position` 位” | 否 |
| `APPROVED` | 预约已批准 | 是 |
| `REJECTED` | 预约被拒绝 | 否 |
| `CANCELLED` | 预约已取消 | 否 |
| `EXPIRED` | 申请已过期 | 否 |

所有预约响应增加 `hold_until`（可空截止时间）、`hold_active`（当前占位是否有效）和 `blocks_slot`（当前是否阻挡重叠预约）。`APPROVED` 的 `blocks_slot=true`，即使 `hold_active=false`。不要只用非空 `hold_until` 判断占用：该值保留为历史，取消、拒绝或批准后临时占位不再有效。`WAITING_QUALIFICATION` 只可能出现在旧数据里，新流程不再产生。

### 先到先得与等待名单

同一资源、时间重叠的申请严格按提交顺序处理：

- **时段空着**（没有已批准预约，也没有别人的待审批申请）：新申请成为该时段的待审批申请并占位。
- **时段被占**：新申请进入 `WAITLISTED`（`reason_code` 为 `TIME_CONFLICT` 或 `TEMPORARY_HOLD_CONFLICT`），不占时段，响应带 `waitlist_position`（重叠候补中的第几位）。管理员不能直接批准候补（`REQUEST_WAITLISTED`），但可以拒绝。
- **递补**：时段一空出来（取消、被拒、过期、改期、资源重新开放），后端按提交顺序取下一位放得下的候补：仍符合规则 → 转为新的 `PENDING_APPROVAL`（`reason_code=PROMOTED_FROM_WAITLIST`，重新计算审批截止时间），由 Admin 审批或超时自动处理；不符合 → `REJECTED`，`reason_code` 为对应的错误码（如 `QUALIFICATION_REQUIRED`、`ACCOUNT_INACTIVE`）。时间部分重叠时，先检查提交更早的候补，放得下就先给它。
- 前一位获批后，候补保持 `WAITLISTED` 作为后备；若获批的人之后取消，或被 Admin／Manager 取消，下一位递补。候补到预约开始时间仍未轮到则 `EXPIRED`。
- 递补不会主动通知，学生需要刷新“我的预约”或 dashboard 才能看到状态变化，前端可轮询。

**限制**：
- **预约窗口（OpenAPI 1.5.0 起）**：预约开始日期（资源当地日期）必须在“今天 + 7 天”到“今天 + 30 天”之间（默认值，来自后端可配置规则 `RulesProvider`，见 backend/README“可配置规则”），即至少提前一周、最多提前一个月。例：周六 10/10 最早能约下周六 10/17，最晚 11/9。太近返回 400 `BOOKING_TOO_SOON`，太远返回 400 `BOOKING_TOO_FAR_AHEAD`；两者的 `details` 都有 `earliest_date`、`latest_date`、`min_advance_days`、`max_advance_days`。改期同样受这个窗口限制；已提交的申请不受影响，日期临近后照常审核和递补。
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
| GET | `resources/?kind=ROOM&q=lab` | 筛选资源；`kind` 也可为 `EQUIPMENT` |
| GET | `resources/{id}/` | 资源详情 |
| GET | `resources/{id}/availability/?date=YYYY-MM-DD&duration_minutes=60` | 可用性及申请资格 |
| GET | `qualification-requirements/` | Induction 要求列表 |
| GET / POST | `qualifications/` | 我的提交／上传资料 |
| GET | `qualifications/{id}/` | 资料提交详情 |
| GET | `qualifications/{id}/file/` | 带权限的附件下载 |
| GET / POST | `bookings/` | 我的预约列表／创建预约 |
| GET | `bookings/{id}/` | 预约详情 |
| POST | `bookings/{id}/cancel/` | 取消预约 |
| POST | `bookings/{id}/reschedule/` | 改期已批准且尚未开始的预约：`start`、`end` |
| GET | `dashboard/` | 我的预约、资料与数量 |
| GET | `admin/qualifications/?status=PENDING` | 管理员资格队列（`PENDING`／`VERIFIED`／`REJECTED`）；每条带 `student`（`id`、`zid`、`display_name`、`university_email`），审核页直接显示姓名和 zID |
| POST | `admin/qualifications/{id}/review/` | `decision: VERIFIED\|REJECTED`，可带 `reason`；不接受 `valid_until`，有效期由后端设定 |
| GET | `admin/bookings/?status=PENDING_APPROVAL` | 待审批队列（默认）；`status=WAITLISTED` 查看候补；`status=ALL&resource_id=&student_id=&since=&until=` 查看所有人的预约（带学生和资源名） |
| GET | `admin/bookings/export/?status=ALL` | 仅 Manager：按相同筛选导出 CSV |
| POST | `admin/bookings/{id}/review/` | `decision: APPROVED\|REJECTED`，可带 `reason`；候补只能拒绝，不能批准 |
| GET | `admin/users/?role=&active=&q=` | 仅 Manager：人员列表 |
| POST | `admin/users/staff/` | 仅 Manager：Add staff，`zid`、`display_name`、`university_email`、`role`（`ADMIN`／`MANAGER`）；响应带 `invite_code` |
| POST | `admin/users/{id}/reset-access/` | 仅 Manager：重置员工登录，生成新邀请码 |
| POST | `admin/users/managers/` | 仅 Manager：旧接口，等同于 Add staff 选 Manager |
| PATCH | `admin/users/{id}/` | 仅 Manager：`{"active":false}` 停用／`{"active":true}` 恢复；角色不能修改 |
| PATCH | `admin/qualification-requirements/{id}/` | 仅 Manager：`{"prerequisite_ids":[...]}` 设置前置 induction |
| GET | `admin/audit/?resource_id=&student_id=&action=&since=&until=&limit=100&offset=0` | Admin／Manager 查看审计记录（申请、审批、改期、取消等），最新在前 |
| POST | `admin/process-due/` | 立即处理已到审批截止时间（自动批准或拒绝）／开始时间的请求 |
| GET / PATCH | `admin/resources/{id}/booking-policy/` | 仅 Manager：读取和修改审批期限 `pending_hold_minutes` |
| PATCH | `admin/resources/{id}/status/` | 仅 Manager：`AVAILABLE`／`MAINTENANCE`／`CLOSED` + `reason` |

`POST bookings/` 可带 `Idempotency-Key`，同一用户重试同一请求时复用同一 key；提交不同预约时生成新 key。key 最多 128 个字符，仅可使用字母、数字、点、下划线、冒号、连字符。禁止只依赖禁用按钮防止重复请求。字段 `start`、`end` 表示区间 `[start,end)`。取消仅允许尚未开始的有效请求；重复取消已取消记录返回原记录。改期只允许预约所有者操作未来 `APPROVED` 预约；后端重新检查时间规则、资格有效期与冲突。成功后 `revision` 增加，并更新原 Outlook 事件。

时段查询默认时长为 30 分钟。前端应依据资源返回的 `slot_minutes` 和 `max_booking_minutes` 限制选择；当前种子规则是 30 分钟粒度、08:00–20:00、最长 480 分钟，同一预约不能跨当地日期。这些是演示配置，客户确认规则后可通过资源数据调整。

Manager 规则页发送 `PATCH admin/resources/{id}/booking-policy/`，请求 `{"pending_hold_minutes":1440}`（字段名沿用数据库列名，含义是 Admin 审批期限，单位分钟）；GET／PATCH 均返回 `{"resource_id":"<uuid>","pending_hold_minutes":1440}`。范围为整数 1–20160，默认 1440（24 小时）。期限到了仍无人处理时，系统按规则自动批准或拒绝（见上文“审批流程”）。修改只影响之后进入待审批的申请；已有截止时间不变。资源详情包含 `pending_hold_minutes`，时段查询响应包含同值的 `review_window_minutes`。旧字段 `auto_approve_max_minutes` 已删除，再发送会返回 400；请求必须带 `pending_hold_minutes`。

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
| `ACCOUNT_INACTIVE` | 409 | 申请人账号已停用，不能批准 |
| `BOOKING_CONFLICT` | 409 | 人工批准失败，提示时段已有获批预约 |
| `BOOKING_HOLD_CONFLICT` | 409 | 人工批准失败，提示时段仍临时占用；`details.hold_until` 为当前占位截止时间 |
| `REQUEST_WAITLISTED` | 409 | 候补不能直接批准，会按顺序自动递补；管理员可以拒绝 |
| `SELF_REVIEW_FORBIDDEN` | 403 | Admin 不能审核自己的 induction 资料或预约申请，交给其他 Admin 或 Manager |
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
| `FORBIDDEN` | 403 | 员工调用学生专用接口（预约、上传资料）或 Admin 调用 Manager 接口 |
| `BOOKING_TOO_SOON` | 400 | 需至少提前 7 天；`details.earliest_date` 为最早可约日期 |
| `BOOKING_TOO_FAR_AHEAD` | 400 | 最多提前 30 天；`details.latest_date` 为最晚可约日期 |
| `QUALIFICATION_ALREADY_PENDING`／`QUALIFICATION_ALREADY_VERIFIED` | 409 | 保留当前资料，刷新资格状态 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同一 key 不能用于另一份请求；新操作生成新 key |
| `DUPLICATE_BOOKING` | 409 | 当前学生已对同一资源提交重叠时段的有效申请；显示已有申请而不是再次加入候补 |
| `REQUEST_NOT_REVIEWABLE`／`ALREADY_REVIEWED` | 409 | 队列状态已改变，刷新列表 |
| `REQUEST_NOT_CANCELLABLE` | 409 | 预约已开始或请求已结束，刷新预约 |
| `REQUEST_NOT_RESCHEDULABLE` | 409 | 只有未来且已批准的预约可以改期，刷新预约 |
| `INVALID_TIME`／`INVALID_TIME_INCREMENT`／`OUTSIDE_OPENING_HOURS`／`DURATION_LIMIT` | 400 | 根据资源规则修正时间 |
| `VALIDATION_ERROR` | 400 | 在对应字段展示 `details` 错误，包括附件格式／大小问题 |
| `TOKEN_EXPIRED`／`INVALID_TOKEN` | 401 | 重新登录 |

学生提交冲突请求会得到 201 和 `WAITLISTED`；`BOOKING_CONFLICT` 是管理员试图批准仍冲突的请求时的错误。不要把“收到 201”或“等待管理员”显示成已获批准。

API 输出时间为 ISO 8601 UTC `Z`。前端用 `Australia/Sydney` 显示，支持夏令时；不能硬编码全年 `+10:00`。availability 的 `date` 是资源时区日期，`slots` 的时间仍是 UTC。前端应标明本地时区。

预约相关读取／操作会由服务器推进到期状态（审批期限到期后的自动决定、过期、候补递补），浏览器不需要自己计时。需要轮询或用户刷新才能更新屏幕；人工审批后的前端实时通知不在本 Sprint 范围内。

## 与后续接入的边界

前端使用 API，不读取数据库，不直接连接 Outlook。数据库同学实现 `Repository`、私有 `FileStorage` 和事务锁；SSO 同学提供服务端验证及可信用户映射。接口结构和状态应保持不变。

演示身份选择仅在本地开发模式开启，不代表正式 SSO。正式前端不得保留任意 zID 登录或选择管理员身份的演示入口。内存数据和 token 登录流程用于联调；数据重启丢失，无法跨多个后端进程共享。

## Sprint 1 Outlook 同步

所有预约响应（列表、详情、dashboard、创建、取消和审核结果）新增 `outlook_sync`，原有预约 `status` 保持不变：

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
| `NOT_REQUIRED` | 当前申请无需写入日历 |
| `PENDING`／`IN_PROGRESS` | 日历等待同步／同步中 |
| `SYNCED` + `CREATE` | 已创建 Outlook 事件；可显示“打开日历”链接 |
| `SYNCED` + `UPDATE` | 改期已更新到同一个 Outlook 事件；可显示“打开日历”链接 |
| `SYNCED` + `DELETE` | 取消已同步到 Outlook |
| `FAILED` | 预约结果已保存，日历同步失败；提示联系管理员 |

只依据预约 `status` 判断是否批准／取消，不把日历失败提示为“预约失败”，也不要自动重新创建预约。更新界面可轮询预约详情或 dashboard；读取接口不自动执行日历网络请求。只有创建／更新成功且未取消的事件返回 `web_link`。

Admin／Manager 的接口：`GET admin/outlook/` 查询配置及记录；`POST admin/outlook/process/` 处理到期任务（`{"limit":1}`，最多 5）；`POST admin/bookings/{id}/outlook-retry/` 立即重试（`{}`）。配置存在不代表权限验证成功，以 Graph 操作结果为准。学生不能调用这些管理接口。

个人账号的授权在开发者本机完成，不需要学生 dashboard 出现 Microsoft 授权按钮，也不要把微软 Token 放进前端。步骤见 [outlook-setup.md](outlook-setup.md)。Sprint 1 是系统写入 Outlook 的单向同步，已覆盖创建、改期和取消；Pending 占位不会创建日历事件。等待名单、重复预约及更完整的规则管理在 Sprint 2 完善。
