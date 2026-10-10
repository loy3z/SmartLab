# Sprint 1 前端交接

API 基础路径为 `/api/v1/`，所有路径末尾都有 `/`。正式结构见 [openapi.json](openapi.json)，启动后的 `GET /api/schema/` 返回相同定义。

## 前端需要完成的功能

| 页面／交互 | 前端职责 | 后端负责 |
| --- | --- | --- |
| 登录与角色入口 | 接 SSO 页面；演示时提供本地登录／学生注册；保存 token，按角色显示菜单 | 校验身份和角色；演示 token；接口权限 |
| 资源与时段查询 | 房间／设备筛选、日期和时长选择、时段展示 | 查询资源、生成时段、检查冲突 |
| 学生 dashboard | 显示资格、预约状态和数量，刷新结果 | 返回当前学生的数据与汇总 |
| Induction 提交 | 选择资格要求，填写说明，上传文件，展示审核结果 | 检查附件、保存提交、保护下载权限 |
| 预约申请 | 选择资源和时间，填写用途，提交后显示服务端状态 | 验证资格门槛、时间规则、自动／人工审批 |
| 我的预约 | 显示详情、改期／取消确认、操作后刷新 | 判断归属及状态，重新校验并执行改期／取消 |
| 管理员资格审核 | 审核列表、查看资料、通过／拒绝和原因；显示后端返回的有效期 | 修改资格、自动设定有效期；通过时重新判断等待资格的预约，拒绝时自动拒绝该学生依赖此资格的 Pending 预约 |
| 管理员预约审核 | 审核队列、详情、通过／拒绝和原因、显示冲突错误 | 批准前再次检查资格与冲突 |
| 审计记录 | Admin／Manager 按资源、学生、操作、时间筛选并分页查看；预约详情可显示该预约的历史 | 记录并查询申请、审批、改期、取消和资格审核轨迹 |
| 人员与角色管理（仅 Manager） | 人员列表、按角色／状态／zID 筛选，修改角色或停用账号 | 只允许 Manager；不能改自己；至少保留一个 Manager；写审计 |
| Manager 占位规则 | 按资源显示和修改 Pending 占位分钟数 | 角色校验、规则保存和审计；Admin 仅可读取 |

隐藏按钮只能改善体验；身份、资格和冲突均由后端执行。前端不能直接设置预约状态、资格状态或用户角色。

演示学生注册需要 `zid`、`display_name`、`university_email`，缺少或格式错误的邮箱返回 400。登录／注册响应中的用户对象以及 `auth/me/` 均返回邮箱。演示模式不验证邮箱所有权；正式 SSO 的邮箱及角色必须由后端从可信身份来源映射。

## 建议调用顺序

1. 读取 `GET auth/config/` 判断认证模式；演示模式调用 `auth/demo-login/` 或 `auth/demo-register/`，然后使用响应 token 调用 `GET auth/me/`。
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

### 人员与角色管理（OpenAPI 1.4.0 起，仅 Manager）

客户要求角色由系统／实验室负责人指定，所以只有 **Manager** 能查看人员名单、修改角色或停用账号；**Manager 同时拥有 Admin 的全部权限**（审核资格、审核预约、查看队列和审计），另外独有占位规则配置和人员管理。Admin 和学生访问这些接口返回 403。

- `GET admin/users/`：返回 `{ count, results }`，每项含 `id`、`zid`、`display_name`、`role`、`active`、`university_email`。可用 `role`、`active=true|false`、`q`（匹配 zID／姓名／邮箱）筛选。
- `PATCH admin/users/{id}/`：请求体为 `role`（`STUDENT|ADMIN|MANAGER`）和／或 `active`。修改在该用户的**下一次请求**生效：升为 Admin 后马上能看到审核队列；被停用的用户再请求会得到 401，前端应跳回登录页。
- 不能修改自己（`SELF_MODIFICATION_FORBIDDEN`，403），系统至少保留一个启用的 Manager（`LAST_MANAGER`，409）。每次修改都会写一条 `USER_UPDATED` 审计记录。
- 修改角色或停用账号不会自动改动该用户已有的预约。
- 列表里只有已经存在于系统中的用户（演示时由数据库预先写入，或登录／注册过一次）。

`dashboard` 返回 `{ bookings, qualifications, counts }`。两个列表是数组，`counts` 的键为六种大写预约状态，例如 `counts.APPROVED`；它不是资格数量或预约总数。其他列表接口使用 `{ count, results }`。

`qualification_status=NOT_CONFIGURED` 表示资源尚未设置 induction 要求，不能申请；需要维护资源数据后再开放。

可用性查询是当时的快照，提交前后仍可能有人占用时段。显示 `available=false` 的时段不能提示“可立即预约”；如果允许发送冲突人工审核请求，应明确展示“已有预约／临时占位，将进入人工审核”。每个资源的 `required_qualification_id` 可以不同，前端必须读取资源要求，不能用一个全局“已完成 induction”开关判断所有资源的资格。

`slots[]` 的 `reason_code` 为 `START_TIME_PASSED`、`BOOKED`、`TEMPORARILY_HELD` 或 `null`。临时占位时返回 `hold_until`（UTC 截止时间）和 `held_by_me`（是否为当前学生自己的占位）；其他情况分别为 `null`、`false`。不返回其他学生身份。可显示占位倒计时，到期刷新查询，最终以服务端响应为准；`can_request` 表示身份／资料允许提交申请，不代表所选时段能立即获批。

## 状态与界面文字

| 资格状态 | 显示含义 | 可以提交该资源预约？ |
| --- | --- | --- |
| 无提交记录 | 请先提交 induction 资料 | 否 |
| `PENDING` | 资料等待管理员审核 | 是，进入等待资格／人工审核流程 |
| 有效 `VERIFIED` | 已具备该资源资格 | 是 |
| `REJECTED` 或已过期 | 资料被拒绝／资格已过期，请重新提交 | 否 |

最新提交决定当前资格。`status` 是资料审核状态，额外的 `effective_status` 表示当前有效性，界面应结合该字段显示过期情况。有效期需要覆盖预约结束时间；在当前时刻有效，不一定覆盖用户选择的预约。已有 PENDING 提交或仍有效的 VERIFIED 提交时，不能重复上传相同要求的资料；拒绝或过期后可重新提交。

**有效期（OpenAPI 1.3.0 起）**：审核通过时后端自动设定 `valid_until = 审核时间 + QUALIFICATION_VALIDITY_DAYS`，默认 120 天（约一个学期）。审核请求不再接受 `valid_until`，带上该字段会返回 400。前端资格审核页去掉有效期输入框，改为显示响应里的 `valid_until`；学生端可显示“资格有效至 …”，并提示超过该时间的预约无法提交。资格过期前不能提前续期，过期后重新上传。

| 预约状态 | 建议显示 | 是否占时段 |
| --- | --- | --- |
| `WAITING_QUALIFICATION` | 申请已提交，等待资格确认 | 仅 `hold_active=true` 时临时占位 |
| `PENDING_APPROVAL` | 等待管理员审批 | 仅 `hold_active=true` 时临时占位 |
| `WAITLISTED` | 候补中，显示“候补第 `waitlist_position` 位” | 否 |
| `APPROVED` | 预约已批准 | 是 |
| `REJECTED` | 预约被拒绝 | 否 |
| `CANCELLED` | 预约已取消 | 否 |
| `EXPIRED` | 申请已过期 | 否 |

所有预约响应增加 `hold_until`（可空截止时间）、`hold_active`（当前占位是否有效）和 `blocks_slot`（当前是否阻挡重叠预约）。`APPROVED` 的 `blocks_slot=true`，即使 `hold_active=false`。不要只用非空 `hold_until` 判断占用：该值保留为历史，取消、拒绝、批准或截止时间到达后临时占位不再有效。

### 先到先得与等待名单（OpenAPI 1.4.0 起）

同一资源、时间重叠的申请严格按提交顺序处理：

- **时段空着**（没有已批准预约，也没有别人的有效占位）：资格已通过 → 立即 `APPROVED`；资料待审 → 这张申请成为该时段的“第一位”，状态为 `WAITING_QUALIFICATION`（开始时间在 24 小时内则为 `PENDING_APPROVAL`），并**占位 30 分钟**（Manager 可按资源调整）。
- **占位到期时资料仍未通过**：这张申请变为 `WAITLISTED`（`reason_code=HOLD_EXPIRED`），时段重新开放。每张申请只有一次占位机会，之后要等资料通过，才能在时段空着时被递补获批；资料一通过、而时段恰好空着，会立即获批。
- **时段被占**：新申请进入 `WAITLISTED`（`reason_code` 为 `TIME_CONFLICT` 或 `TEMPORARY_HOLD_CONFLICT`），不占时段，响应带 `waitlist_position`（重叠候补中的第几位）。即使资格已通过也要排队，不能插到前面。管理员不能直接批准候补（`REQUEST_WAITLISTED`），但可以拒绝。
- **自动递补**：时段一空出来（取消、被拒、过期、改期、资料被拒、占位到期），或候补学生的资料审核通过时，后端按提交顺序取下一位能放进去的候补自动处理：资格已通过 → `APPROVED`；资料待审且从没占过位 → 成为新的第一位并占位 30 分钟；占过位但资料还没通过 → 跳过、继续等；资格无效 → `REJECTED`（`QUALIFICATION_REQUIRED`）。`reason_code` 为 `PROMOTED_FROM_WAITLIST`。时间部分重叠时，先检查提交更早的候补，放得下就先给它。
- 第一位获批后，候补保持 `WAITLISTED` 作为后备；若获批的人之后取消，下一位自动递补。候补到预约开始时间仍未轮到则 `EXPIRED`。
- 递补不会主动通知，学生需要刷新“我的预约”或 dashboard 才能看到状态变化，前端可轮询。递补获批的预约会和触发它的那次操作一起同步到 Outlook。

**限制**：
- 预约开始日期最多为资源当地日期“今天 + 7 天”（`MAX_ADVANCE_DAYS`），超出返回 400 `BOOKING_TOO_FAR_AHEAD`，`details.latest_date` 为最远可约日期。日期选择器可以直接限制在这个范围内。
- 资料还在审核中的学生，每项资格同时只能有 1 张未决申请（`UNVERIFIED_PENDING_LIMIT`，包括候补）。再提交返回 409 `PENDING_REQUEST_LIMIT`，`details.pending_booking_ids` 是已有的申请。资格已通过的学生不受这个限制。

`TEMPORARILY_HELD` 时段可显示为“审核中，暂不可约”，并显示 `hold_until`；学生仍可提交，提交后会进入候补。刷新、幂等重试和审批升级都不会续占。

示例（默认 30 分钟）：10:00 A（资料待审）申请周五 10–12 点，占位到 10:30 → 10:10 有资格的 B 申请同一时段，进候补，不能直接获批 → 10:30 A 的资料仍未通过，A 进候补（`HOLD_EXPIRED`），B 自动递补获批 → 之后 A 的资料通过，A 仍在候补 → 只有 B 取消后，A 才会被递补获批。如果 B 是 10:40 才来，则直接获批。

资格已验证且时段空着的申请立即批准。“24 小时转人工预约审核”只在 Manager 把占位设到 24 小时以上时才会发生；默认 30 分钟占位下，未通过的申请会先进入候补，资料通过后自动处理，不需要管理员再批一次预约。资格通过后，后端会重新判断仍在等待资格的预约；前端使用后端返回的结果，不自行推算“自动成功”。

**资料被拒时**：后端会自动拒绝该学生对“要求这项资格的资源”的所有未决预约（`WAITING_QUALIFICATION`、`PENDING_APPROVAL` 和 `WAITLISTED`），并把空出的时段交给候补，状态变为 `REJECTED`，`reason_code` 为 `QUALIFICATION_REJECTED`，`decision_reason` 为资料的拒绝原因，时段立即释放。审核响应的 `updated_bookings` 会包含这些预约。学生端应显示：资料被拒及原因（资格的 `rejection_reason`）→ 相关预约已被拒 → 引导学生重新上传资料，通过或重新提交后再预约。

如果预约开始时间早于／等于 24 小时门槛，未验证请求立即进入人工审核。仍未获批准的请求达到开始时间后为 `EXPIRED`。资格获批不会自动批准已经处于 `PENDING_APPROVAL` 的请求，需要管理员另行审核预约。

## 接口速查

下面路径均以 `/api/v1/` 开头。除健康、认证配置与演示登录／注册外，需要 Bearer token。列表统一返回 `{ "count": 0, "results": [] }`。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `health/` | 服务状态 |
| GET | `auth/config/` | 当前认证配置 |
| POST | `auth/demo-register/` | 本地创建学生账号：`zid`、`display_name`、`university_email` |
| POST | `auth/demo-login/` | 本地演示登录：`zid` |
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
| GET | `admin/qualifications/?status=PENDING` | 管理员资格队列 |
| POST | `admin/qualifications/{id}/review/` | `decision: VERIFIED\|REJECTED`，可带 `reason`；不接受 `valid_until`，有效期由后端设定 |
| GET | `admin/bookings/?status=PENDING_APPROVAL` | 管理员预约队列；`status=WAITLISTED` 查看候补 |
| POST | `admin/bookings/{id}/review/` | `decision: APPROVED\|REJECTED`，可带 `reason`；候补只能拒绝，不能批准 |
| GET | `admin/users/?role=&active=&q=` | 仅 Manager：人员列表 |
| PATCH | `admin/users/{id}/` | 仅 Manager：`{"role":"ADMIN"}` 和／或 `{"active":false}` |
| GET | `admin/audit/?resource_id=&student_id=&action=&since=&until=&limit=100&offset=0` | Admin／Manager 查看审计记录（申请、审批、改期、取消等），最新在前 |
| POST | `admin/process-due/` | 处理已到 24 小时门槛／开始时间的请求 |
| GET / PATCH | `admin/resources/{id}/booking-policy/` | Admin／Manager 读取；仅 Manager 修改占位时长 |

`POST bookings/` 可带 `Idempotency-Key`，同一用户重试同一请求时复用同一 key；提交不同预约时生成新 key。key 最多 128 个字符，仅可使用字母、数字、点、下划线、冒号、连字符。禁止只依赖禁用按钮防止重复请求。字段 `start`、`end` 表示区间 `[start,end)`。取消仅允许尚未开始的有效请求；重复取消已取消记录返回原记录。改期只允许预约所有者操作未来 `APPROVED` 预约；后端重新检查时间规则、资格有效期与冲突。成功后 `revision` 增加，并更新原 Outlook 事件。

时段查询默认时长为 30 分钟。前端应依据资源返回的 `slot_minutes` 和 `max_booking_minutes` 限制选择；当前种子规则是 30 分钟粒度、08:00–20:00、最长 480 分钟，同一预约不能跨当地日期。这些是演示配置，客户确认规则后可通过资源数据调整。

Manager 规则页发送 `PATCH admin/resources/{id}/booking-policy/`，请求 `{"pending_hold_minutes":30}`；GET／PATCH 均返回 `{"resource_id":"<uuid>","pending_hold_minutes":30}`。范围为整数 1–20160，默认 30；设为最大值 20160（两周，超过可预约范围）相当于“第一位一直保持到有结果”。占位到期时，原申请进入候补，时段交给下一位。修改只影响之后创建的占位；已有截止时间不变。资源详情也包含 `pending_hold_minutes`。占位时长与 24 小时审批等待是两个独立配置。

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
| `QUALIFICATION_REQUIRED` | 403 | 提示先提交有效 induction 资料；查看 `details.qualification_status` |
| `QUALIFICATION_NOT_VERIFIED` | 409 | 管理员先处理资格，不能直接批准预约 |
| `BOOKING_CONFLICT` | 409 | 人工批准失败，提示时段已有获批预约 |
| `BOOKING_HOLD_CONFLICT` | 409 | 人工批准失败，提示时段仍临时占用；`details.hold_until` 为当前占位截止时间 |
| `REQUEST_WAITLISTED` | 409 | 候补不能直接批准，会按顺序自动递补；管理员可以拒绝 |
| `PENDING_REQUEST_LIMIT` | 409 | 资料审核中只能有 1 张未决申请；引导学生查看或取消 `details.pending_booking_ids` |
| `BOOKING_TOO_FAR_AHEAD` | 400 | 超出可预约范围；`details.latest_date` 为最远日期 |
| `QUALIFICATION_ALREADY_PENDING`／`QUALIFICATION_ALREADY_VERIFIED` | 409 | 保留当前资料，刷新资格状态 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同一 key 不能用于另一份请求；新操作生成新 key |
| `REQUEST_NOT_REVIEWABLE`／`ALREADY_REVIEWED` | 409 | 队列状态已改变，刷新列表 |
| `REQUEST_NOT_CANCELLABLE` | 409 | 预约已开始或请求已结束，刷新预约 |
| `REQUEST_NOT_RESCHEDULABLE` | 409 | 只有未来且已批准的预约可以改期，刷新预约 |
| `INVALID_TIME`／`INVALID_TIME_INCREMENT`／`OUTSIDE_OPENING_HOURS`／`DURATION_LIMIT` | 400 | 根据资源规则修正时间 |
| `VALIDATION_ERROR` | 400 | 在对应字段展示 `details` 错误，包括附件格式／大小问题 |
| `TOKEN_EXPIRED`／`INVALID_TOKEN` | 401 | 重新登录 |

学生提交冲突请求会得到 201 和 `WAITLISTED`；`BOOKING_CONFLICT` 是管理员试图批准仍冲突的请求时的错误。不要把“收到 201”或“等待管理员”显示成已获批准。

API 输出时间为 ISO 8601 UTC `Z`。前端用 `Australia/Sydney` 显示，支持夏令时；不能硬编码全年 `+10:00`。availability 的 `date` 是资源时区日期，`slots` 的时间仍是 UTC。前端应标明本地时区。

预约相关读取／操作会由服务器推进到期状态，无需浏览器维护 24 小时计时器。需要轮询或用户刷新才能更新屏幕；人工审批后的前端实时通知不在本 Sprint 范围内。

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
