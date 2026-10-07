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
| 我的预约 | 显示详情、取消确认、取消后刷新 | 判断归属及状态，执行取消 |
| 管理员资格审核 | 审核列表、查看资料、通过／拒绝和原因，填写有效期 | 修改资格，重新判断等待资格的预约 |
| 管理员预约审核 | 审核队列、详情、通过／拒绝和原因、显示冲突错误 | 批准前再次检查资格与冲突 |

隐藏按钮只能改善体验；身份、资格和冲突均由后端执行。前端不能直接设置预约状态、资格状态或用户角色。

## 建议调用顺序

1. 读取 `GET auth/config/` 判断认证模式；演示模式调用 `auth/demo-login/` 或 `auth/demo-register/`，然后使用响应 token 调用 `GET auth/me/`。
2. 调用 `GET resources/` 和 `GET qualification-requirements/`，展示资源及其要求。
3. 学生通过 `GET qualifications/` 或 `GET dashboard/` 查看自己的资格。未提交对应资料时，显示上传入口。
4. 使用 `multipart/form-data` 调用 `POST qualifications/`，字段为 `requirement_id`、`title`、`notes`、`file`。不要手写 multipart 的 Content-Type boundary，由浏览器处理。
5. 调用 `GET resources/{id}/availability/?date=YYYY-MM-DD&duration_minutes=60` 展示时段，并读取 `can_request`／`qualification_status`。日期是资源当地的日历日期。
6. 调用 `POST bookings/`，发送 `resource_id`、`start`、`end`、`purpose`。时间必须携带时区，例如 `2026-10-07T09:00:00+11:00`；不要发送无时区字符串。
7. 按响应 `status` 显示结果，再刷新 dashboard 和可用性。HTTP 201 表示请求创建成功，重复幂等请求返回 200；只有 `APPROVED` 表示预约已经获批。
8. Admin 使用 `admin/qualifications/` 审核 induction；审核响应包含 `submission` 和 `updated_bookings`，刷新相关列表。随后用 `admin/bookings/` 审核预约。

`dashboard` 返回 `{ bookings, qualifications, counts }`。两个列表是数组，`counts` 的键为六种大写预约状态，例如 `counts.APPROVED`；它不是资格数量或预约总数。其他列表接口使用 `{ count, results }`。

`qualification_status=NOT_CONFIGURED` 表示资源尚未设置 induction 要求，不能申请；需要维护资源数据后再开放。

可用性查询是当时的快照，提交前后仍可能有人占用时段。显示 `available=false` 的时段不能提示“可立即预约”；如果希望前端允许发送冲突人工审核请求，应明确展示“已有预约，将进入人工审核”，而不是“预订成功”。

## 状态与界面文字

| 资格状态 | 显示含义 | 可以提交该资源预约？ |
| --- | --- | --- |
| 无提交记录 | 请先提交 induction 资料 | 否 |
| `PENDING` | 资料等待管理员审核 | 是，进入等待资格／人工审核流程 |
| 有效 `VERIFIED` | 已具备该资源资格 | 是 |
| `REJECTED` 或已过期 | 资料被拒绝／资格已过期，请重新提交 | 否 |

最新提交决定当前资格。`status` 是资料审核状态，额外的 `effective_status` 表示当前有效性，界面应结合该字段显示过期情况。有效期需要覆盖预约结束时间；在当前时刻有效，不一定覆盖用户选择的预约。已有 PENDING 提交或仍有效的 VERIFIED 提交时，不能重复上传相同要求的资料；拒绝或过期后可重新提交。

| 预约状态 | 建议显示 | 是否占时段 |
| --- | --- | --- |
| `WAITING_QUALIFICATION` | 申请已提交，等待资格确认 | 否 |
| `PENDING_APPROVAL` | 等待管理员审批 | 否 |
| `APPROVED` | 预约已批准 | 是 |
| `REJECTED` | 预约被拒绝 | 否 |
| `CANCELLED` | 预约已取消 | 否 |
| `EXPIRED` | 申请已过期 | 否 |

无冲突且资格已验证的申请立即批准。未验证申请从预约创建起等待 24 小时，之后进入人工预约审核；不会自动获得资格。已有冲突的请求立即进入人工审核。资格通过后，后端会重新判断仍在等待资格的预约；前端使用后端返回的结果，不自行推算“自动成功”。

如果预约开始时间早于／等于 24 小时门槛，未验证请求立即进入人工审核。仍未获批准的请求达到开始时间后为 `EXPIRED`。资格获批不会自动批准已经处于 `PENDING_APPROVAL` 的请求，需要管理员另行审核预约。

## 接口速查

下面路径均以 `/api/v1/` 开头。除健康、认证配置与演示登录／注册外，需要 Bearer token。列表统一返回 `{ "count": 0, "results": [] }`。

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `health/` | 服务状态 |
| GET | `auth/config/` | 当前认证配置 |
| POST | `auth/demo-register/` | 本地创建学生账号：`zid`、`display_name` |
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
| GET | `dashboard/` | 我的预约、资料与数量 |
| GET | `admin/qualifications/?status=PENDING` | 管理员资格队列 |
| POST | `admin/qualifications/{id}/review/` | `decision: VERIFIED\|REJECTED`，可带 `reason`、`valid_until` |
| GET | `admin/bookings/?status=PENDING_APPROVAL` | 管理员预约队列 |
| POST | `admin/bookings/{id}/review/` | `decision: APPROVED\|REJECTED`，可带 `reason` |
| POST | `admin/process-due/` | 处理已到 24 小时门槛／开始时间的请求 |

`POST bookings/` 可带 `Idempotency-Key`，同一用户重试同一请求时复用同一 key；提交不同预约时生成新 key。key 最多 128 个字符，仅可使用字母、数字、点、下划线、冒号、连字符。禁止只依赖禁用按钮防止重复请求。字段 `start`、`end` 表示区间 `[start,end)`。取消仅允许尚未开始的有效请求；重复取消已取消记录返回原记录。

时段查询默认时长为 30 分钟。前端应依据资源返回的 `slot_minutes` 和 `max_booking_minutes` 限制选择；当前种子规则是 30 分钟粒度、08:00–20:00、最长 480 分钟，同一预约不能跨当地日期。这些是演示配置，客户确认规则后可通过资源数据调整。

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
| `QUALIFICATION_ALREADY_PENDING`／`QUALIFICATION_ALREADY_VERIFIED` | 409 | 保留当前资料，刷新资格状态 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同一 key 不能用于另一份请求；新操作生成新 key |
| `REQUEST_NOT_REVIEWABLE`／`ALREADY_REVIEWED` | 409 | 队列状态已改变，刷新列表 |
| `REQUEST_NOT_CANCELLABLE` | 409 | 预约已开始或请求已结束，刷新预约 |
| `INVALID_TIME`／`INVALID_TIME_INCREMENT`／`OUTSIDE_OPENING_HOURS`／`DURATION_LIMIT` | 400 | 根据资源规则修正时间 |
| `VALIDATION_ERROR` | 400 | 在对应字段展示 `details` 错误，包括附件格式／大小问题 |
| `TOKEN_EXPIRED`／`INVALID_TOKEN` | 401 | 重新登录 |

学生提交冲突请求可以得到 201 和 `PENDING_APPROVAL`；`BOOKING_CONFLICT` 是管理员试图批准仍冲突的请求时的错误。不要把“收到 201”或“等待管理员”显示成已获批准。

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
| `SYNCED` + `CREATE` | 已同步到 Outlook；可显示“打开日历”链接 |
| `SYNCED` + `DELETE` | 取消已同步到 Outlook |
| `FAILED` | 预约结果已保存，日历同步失败；提示联系管理员 |

只依据预约 `status` 判断是否批准／取消，不把日历失败提示为“预约失败”，也不要自动重新创建预约。更新界面可轮询预约详情或 dashboard；读取接口不自动执行日历网络请求。只有创建成功且未取消的事件返回 `web_link`。

Admin／Manager 的接口：`GET admin/outlook/` 查询配置及记录；`POST admin/outlook/process/` 处理到期任务（`{"limit":1}`，最多 5）；`POST admin/bookings/{id}/outlook-retry/` 立即重试（`{}`）。配置存在不代表权限验证成功，以 Graph 操作结果为准。学生不能调用这些管理接口。

个人账号的授权在开发者本机完成，不需要学生 dashboard 出现 Microsoft 授权按钮，也不要把微软 Token 放进前端。步骤见 [outlook-setup.md](outlook-setup.md)。Sprint 1 是系统写入 Outlook 的单向同步；改期、等待名单、重复预约及规则管理在 Sprint 2 完善。
