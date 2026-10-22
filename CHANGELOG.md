# 变更记录

这里记录每次改了什么、为什么改。其他文档只写现在的规则。版本号是 `backend/docs/openapi.json` 的接口版本，迁移指 `backend/database/migrations/` 里的脚本。最新的在最上面。

## 1.11.1（2026-10-20）

接口没有变化。

- **后端重构**：`booking/services.py` 拆成 `booking/services/` 目录，按主题分成 9 个文件（见 [ARCHITECTURE.md](ARCHITECTURE.md)）。只挪了代码位置，行为不变；`from booking.services import BookingService` 照常可用。
- **文档整理**：
  - 各文档只写现行规则，版本号、日期和“新增／原来”的说法挪到本文件。
  - 新增 `ARCHITECTURE.md` 和 `CHANGELOG.md`，根目录 `README.md` 从 GitLab 模板换成项目说明。
  - `backend/database/README.md` 的升级步骤改成按顺序执行全部迁移脚本（在已经是最新结构的库上执行也没有变化，已验证）。
  - 修正了文档里过时的说法：dashboard 的 `counts` 是七种状态；员工也可以预约。
- **OpenAPI**：只改说明文字（去掉 Sprint、日期和版本备注），版本号改为 1.11.1。

## 1.11.0（2026-10-18）迁移 005

依据客户 2026-10-17 的邮件：第一阶段单向同步可以接受，但必须真正接入 Outlook 并实测；网站是唯一依据，Outlook 里的改动不能绕过规则，也不能变成已批准的预约。

- **Outlook 真实接入（单向）**：
  - 用 Microsoft Graph 写日历：批准后创建事件，Manager 改期时更新，取消时删除。
  - 系统从不读取 Outlook。用户在自己日历里删改事件，系统不管；只有 Manager 改期时，如果事件已被删除，才按新时间重建（审计 `OUTLOOK_EVENT_RECREATED`）。
  - 邀请开关 `OUTLOOK_INVITE_MODE`（`none`／`allowlist`／`all`，默认 `allowlist`）和 `OUTLOOK_ALLOWED_ATTENDEES`，避免给真实的人发邀请。
  - 两种授权方式：`manage.py outlook_token`（粘贴 Graph Explorer Token），`manage.py outlook_login`（设备码登录，自动续期）。
  - 实测命令 `manage.py outlook_live_check`：连接、创建、读回、改期、删除，共 5 步。
  - 新接口 `POST admin/outlook/check/`；`GET admin/outlook/` 增加 `summary`、`items`、`last_check`、`invite_mode`。
  - 前端加 Calendar Sync 开发页面（`/admin/calendar-sync`），正式交付前删除。
- **讨论后决定不做**：检查 Outlook 事件是否被改动（drift check）和自动改回（restore）。理由：每个人管自己的日历，删改也没有惩罚，检查没有意义。
- **预约页 Find a free time**：
  - 新接口 `GET resources/day-overview/`：一张表列出所有符合筛选的资源当天的空闲和占用时间，用的是和单个资源时段相同的规则检查。
  - 资源加 `category`（设备类别，演示类别是编的），`GET resources/` 支持 `category=` 筛选。
- **演示 staff 密码**改为 `123`（z9000001、z9000002）。
- 迁移 005：`bookable_resource.category` 和演示密码。
- OpenAPI 里的可空字段统一改成 3.0 的写法。

## 1.10.0（2026-10-17）迁移 004

依据客户 2026-10-17 的邮件。

- **所有人用同一套规则预约**：Admin 和 Manager 也可以预约，induction 不能绕过。
- **代他人预约**：员工用 `on_behalf_of_zid` 替别人预约；预约属于被预约人（检查他的 induction），`created_by` 记录创建者。新接口 `GET people/lookup/`，availability 支持 `for_zid`。
- **紧急申请**：`urgent` + `urgent_reason`，只跳过最短提前期；时段必须空闲；只有 Manager 能决定，不自动批准。
- **改期改为只有 Manager 能做**，不受最短提前期限制。
- 不能审批给自己的或自己创建的申请（`SELF_REVIEW_FORBIDDEN`）。
- 迁移 004：`booking.created_by`、`urgent`、`urgent_reason`。

## staff 登录（迁移 003）

当时没有单独记版本号，在 1.8.0 和 1.10.0 之间。

- 两个登录入口：学生用大学登录（演示版只填 zID），Admin／Manager 用 staff 登录页（zID + 密码）。两边互相拒绝对方的账号。
- Manager 用 Add staff 建员工账号，系统发邀请码，员工首次激活时自己设密码；忘记密码由 Manager 点 Reset access 重发邀请码。
- 迁移 003：新表 `staff_credential`，只存密码哈希和邀请码。

## 1.8.0（第 5 周，2026-10-14）迁移 002

- **人员管理（只有 Manager）**：人员列表、Add staff、停用和恢复账号。停用学生时，他的未决申请立即拒绝并递补下一位。
- **前置 induction**：`prerequisite_ids`，例如 Advanced 要先通过 General；缺前置时返回 `PREREQUISITE_REQUIRED`。
- **房间和设备**：设备记录所在房间 `room_id`，页面按房间分组；房间维修不影响里面的设备。
- 迁移 002：`prerequisite_ids`、`room_id`。

## 1.7.0（2026-10-12）迁移 001

依据客户 2026-10-07 的要求重做审批流程。

- **只有 induction 已通过且有效的人才能申请。**
- **每个申请都先进入待审批**，在审批期限内占住时段（默认 24 小时，Manager 可按资源调整）。Admin／Manager 在期限内批准或拒绝；期限到了没人处理，系统按规则自动批准或拒绝。
- **先到先得的等待名单**：时段被占时进入候补，时段空出来按提交顺序递补成新的待审批申请。
- **资源状态**：Manager 可以把资源设为维修中或关闭，暂停新申请，已有预约保留。
- **所有人的预约**：`GET admin/bookings/` 支持按状态、资源、学生、时间筛选；Manager 可以导出 CSV。
- **移除**：120 分钟以内立即批准、`auto_approve_max_minutes`、`needs_review`、`DURATION_REVIEW`、`RESCHEDULE_NEEDS_REVIEW`；资料审核中先预约（`WAITING_QUALIFICATION`、30 分钟占位、`HOLD_EXPIRED`、`PENDING_REQUEST_LIMIT`）。`WAITING_QUALIFICATION` 只留在早期数据里。
- 迁移 001：资源状态两列；`pending_hold_minutes` 的含义改为审批期限，默认从 30 改为 1440。

## 1.5.0

- **预约窗口**：开始日期必须在“今天 + 7 天”到“今天 + 30 天”之间。数字放进 `RulesProvider`（`booking/rules.py`），改环境变量就能调。

## 1.3.0

- **审计记录查询** `GET admin/audit/`（Admin／Manager）。
- **资格有效期由后端设定**：审核通过时间加 120 天，审核时不能再填有效期。

## 更早（Sprint 1 起步）

- 资源和时段查询、induction 上传和审核、预约申请和审核、取消、dashboard、`Idempotency-Key` 防重复提交、内存演示存储。
