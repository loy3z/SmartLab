# 变更记录

这里记录每次改了什么、为什么改。其他文档只写现在的规则。版本号是 `backend/docs/openapi.json` 的接口版本，迁移指 `backend/database/migrations/` 里的脚本。最新的在最上面。

## 1.17.0（2026-10-25）

按 Loy 在本机截图后的功能决定实现；这一轮以功能为先，不做整体视觉重做。没有数据库结构改动。

- **FC-01：Urgent 重复填写说明。** Urgent 表单只留一个必填的 **Purpose and urgency**，同一份文字发送为 `purpose` 与 `urgent_reason`；普通预约仍显示 Purpose。普通账号的紧急请求仍需 Manager 审批。
- **FC-02：每次测试要换账号、等审批、受预约窗口限制。** 增加显式开启的本地 Test console，登录 ID `1`，不需密码；同一账号可切 Student、Admin、Manager，并开关 booking-rule bypass。开关打开时，本人预约／改期立即批准，跳过提前天数、资格、开放时间、维修状态、最长时长、每周次数及冻结限制；周重复预约也支持本人测试。保留未来有效时间、24 h 单次上限、重复和冲突保护，重复系列最多 52 周。切到其他人时仍按那个人的正常规则。权限只存在服务端签名的会话中，不修改持久角色；默认关闭且正式认证模式不可用。测试预约保留站内通知与审计，不发邮件或同步 Outlook。
  - **只在内存模式可用**（Loy 2026-10-25 审阅后定）：`test_console_enabled` 多一个条件 `REPOSITORY_FACTORY` 是内存存储。原因：连 PostgreSQL 时测试预约会写进正式库，出现在 Booking Records、Usage statistics 和 Today 里，还会占住真实时段。不为测试账号单独建表；重启后端就清空。本机 `start-backend.ps1 -TestConsole` 自动用内存模式。
  - 审阅时顺手改的小问题：`TestPrincipal` 的 bypass 默认值改为关（各处本来都显式传值，行为不变）；bypass 时间格的结束时间改为第二天的本地 0 点（夏令时那天不再差一小时）；重复预约的逐日检查和外层检查写法统一为 `booking_rules_bypassed(actor, person.id)`（接口不接受把 `1` 当 zID，以前的写法实际走不到不同结果，只是读起来不一致）；补上 `Sprint 3` 文件标注，改正 `create_test_booking` 的说明。登录后默认打开 bypass，保持不变（Loy 确认）。
- **FC-03：上传 evidence 缺少必填说明。** 培训要求、标题、附件都标 Required；未选文件时直接提示需要上传证书，按钮保持不可提交；空文件、超限和不支持的格式显示英文提示。文件选择改为英文 Choose file／No file selected。

接口版本为 1.17.0；接口约定见 `backend/docs/frontend-api.md`，功能代码和测试索引见 `SPRINT3.md` 第 17 节。

## 1.16.0（2026-10-25）

Sprint 3 的第五批：处理 2026-10-24 的第三方用户体验报告（14 项，基于 1.15.0）。下面按报告编号写，每项先写报告指出的问题（即修改原因），再写改法。Loy 定的方向：房间和设备分开预约，组合逻辑留给客户；学生可以申请改期，新时间被占时只能进候补；维修时自动通知。拿不准的 4 项（第 2、3、4、12 项）由 Loy 选定。**有数据库改动：迁移 007**。新增代码都标了 `Sprint 3 (1.16.0)`，清单见 [SPRINT3.md](SPRINT3.md) 第 16 节。

1. **审批页看不到用途**：Booking Review 加 Purpose 列和明显的 Details 按钮（整行也能点开）。详情抽屉以前就有用途、资格和截止时间，只是入口不明显。改期申请在时间下面显示 Change from。
2. **没有联系入口，学生不能自己申请改期**：
   - 申请改期（`services/changes.py`，`POST bookings/{id}/change/`）：本人已批准的未来预约可以申请换时间。新时间空闲就待审批，被占用就进候补，选到被占用的时间时页面会先提示。原预约在新申请批准前一直保留，批准时自动取消（`REPLACED_BY_CHANGE`）并交给候补；被拒、撤回或过期时原预约不变。规则和普通申请相同，原预约不算冲突、重复或每周名额；一个预约同时只能有一个改期申请（数据库部分唯一索引保证）；不能紧急改期。以前只有 Manager 能改期，学生只能先取消再重订，中间可能被别人抢走。
   - 联系方式（新表 `site_contact`，`GET/PATCH site/contact/`）：Loy 定由 Manager 在新的 Lab setup 页面填写邮箱、电话、答复时间和备注。显示在 Help 页面、已批准预约卡片（Contact the lab，邮件已带资源、时间和预约编号）和每项 induction 下面，只显示填了的字段。
3. **新学生不知道怎么取得 induction**：每项 induction 多四段说明（怎么完成、接受什么证明、谁审核、找谁问），Induction & Training 页面显示 How to get this induction。Loy 定 Manager 可以在 Lab setup 新建 induction、改名称和全部说明、设前置（`POST admin/qualification-requirements/`、`PATCH …/{id}/`）；改文字不影响已经通过的人。
4. **资源信息不足以选对**：Loy 定用可自定义的“标签：内容”列表加房间容量，因为每个实验室要写的内容不同。房间可以填容量（`capacity`），所有资源可以加最多 12 行 `details`。卡片显示容量和前 3 行，预约表单显示全部；房间列表可以按“至少 N 人”筛选；卡片封面缩小。
5. **手机上选时间要双向滚动**：时间条下面可以直接选开始时间和时长；手机上所选时间和提交按钮固定在弹窗底部。
6. **想约近期的人先撞上日期限制**：在最早可约的那天提示“更早要走紧急申请”，可以一键切换。提前天数不变。
7. **维修后的预约要人工跨步骤处理**：按 Loy 的决定自动通知（`services/resources.py` `_notify_status_change`）。资源改成维修或关闭时，所有在它上面有未来预约或申请的人收到站内通知和邮件（带 Manager 写的原因），重新开放时也通知，只改原因不重复通知。已批准的预约仍保留，由 Manager 决定。确认框列出受影响的预约，列表标出它们，Today 页面显示维修中的资源和受影响数。
8. **房间和设备的关系没讲清**：按 Loy 的决定分开预约、不做自动组合。页面写明“订房间不包含里面的设备”“订设备不占用房间”。
9. **两种预约方式的时长不一致**：Find a free time 的时长到 8 小时。某个资源不能按所选时长预约时只跳过这个资源（计入 `too_long`），以前是整个请求 400、页面报错。
10. **空结果把资格问题说成筛选问题**：按原因说明隐藏了什么（例如“19 hidden: 18 induction not submitted, 1 under maintenance”），有 induction 原因时给出 Induction & Training 链接（`day_overview` 的 `not_bookable`）。
11. **日历订阅只讲 Outlook**：分别给 Outlook、Google 和 Apple 的步骤，说明更新有延迟、以网站为准，换新链接时说明要删掉旧订阅。
12. **Manager 没有工作总览**：Loy 定改为员工首页 Today（`/admin/today`，`GET admin/overview/`）。Admin 和 Manager 登录后先看到待审 induction、待审预约、紧急申请、候补、改期申请、快到审批期限的申请、解冻申请、维修中的资源、今天的预约和缺席，每张卡片链接到处理它的页面。以前 Admin 落在 Qualification Review、Manager 落在 Room Management。
13. **必填没标记、按钮为什么灰着不清楚**：Purpose 标为必填；按钮灰着时直接写还差什么（`submitBlocker`）。
14. **管理表单用分钟**：资源设置的“最长预约”和“审批期”改用小时填写，并写明生效方式（例如“24 h (1 day) 后系统自动决定”）；接口仍是分钟。

- 演示数据不变：联系方式、induction 说明、容量和资源信息都是空的，由 Manager 在网页上填。
- 没有做：第 6 项的“先选日期再说明流程”、第 10 项的相邻日期推荐、第 11 项的单次事件下载、第 12 项的侧栏分组；真实照片；可视化的第二、三部分。
- 迁移 007（`007_change_requests_guidance_details_contact.sql`，可重复执行）；OpenAPI 1.16.0。

## 1.15.0（2026-10-24）

Sprint 3 的第四批：界面可视化的第一部分，依据 Loy 2026-10-24 以用户和领导角度的检查。只改前端，不改数据库，接口没有变化（版本号照规则同步）。新增代码都标了 `Sprint 3`，清单见 [SPRINT3.md](SPRINT3.md) 第 15 节。

- **通知铃铛**：
  - 角标以前和铃铛一样大，把铃铛盖住了。原因是 `shell.css` 的 `.app-icon-button > span { font-size: 27px }` 压过了角标自己的 11px。现在角标用更具体的选择器，缩小并移到铃铛右上角，加一圈白边。
  - 有新通知（未读数增加）时铃铛摆动一下，角标数字变化时弹一下；打开页面第一次加载时不摆，免得每次进站都晃。
  - 手机上面板以前从铃铛往左展开，会超出屏幕左边；现在窄屏时面板固定在顶部栏下方，左右各留 16px。
  - 面板：按“今天 / 更早”分组（按悉尼日期），每条按类型配图标（批准 ✓、拒绝或取消 ✗、提醒 时钟、其他 i），正文最多两行，未读用粗体标题和蓝点表示，不再整块铺蓝底。原因：以前每条三四行长句，一屏只能看两三条，也分不清哪种消息。
- **资源卡片封面**：以前是名字首字母加渐变色，两个房间完全一样，看起来像占位图。现在按类型显示图标和配色：房间、显微、成像、电子测试、焊接、加工、分析，其他设备用通用图标；设备卡片左下角显示类别。按类别和名称里的关键词判断，所以 Manager 以后新建的类别（例如 “3D printing”）也能配上。等有真实照片再替换。
- **时间格配色**（Book a resource 弹窗和 Find a free time）：以前“空闲”是最深的蓝色、铺满整屏，真正要注意的“已占用”反而是浅灰斜纹。现在空闲是浅蓝、鼠标移上去加深并出现蓝框；已占用是深灰实色；待审批和自己的申请仍是斜纹；不可预约是浅灰细斜纹；整条加了边框。当天营业时间内加一条红色“现在”竖线（图例里同时出现 Now）。
- **基础动效**：统一的时长和缓动变量（`index.css`）；切换页面时内容淡入；资源卡片和首页数字卡片鼠标移上去轻微上浮；弹窗和确认框淡入上浮；按钮按下时轻微缩小。系统设置了“减少动态效果”时全部关闭。页面淡入只用透明度，不用位移，因为位移会让页面里固定定位的弹窗跑位。
- 没有做：真实照片和 Manager 上传照片（等照片准备好）；Manager 在网页上管理 induction 类型（待定）。
- OpenAPI 1.15.0（接口无变化）。

## 1.14.0（2026-10-24）

Sprint 3 的第三批，依据 Loy 2026-10-24 试用后的反馈。不改数据库。新增代码都标了 `Sprint 3`，清单见 [SPRINT3.md](SPRINT3.md) 第 11–14 节。

- **邮件通知**（`booking/email_channel.py`）：
  - 用一个 Gmail 系统邮箱（SMTP + 应用专用密码）发信，接在 1.12.0 留好的通知发送渠道上，业务代码不改。
  - 发给预约人的大学邮箱：申请已收到、批准或拒绝（含系统自动决定）、过期、候补转正、改期、被员工取消、提醒、员工替你预约或建了重复预约。主题带资源和时间，正文带网站链接。
  - 开关 `EMAIL_ENABLED`（默认关）；收件范围 `EMAIL_MODE`：`none`／`allowlist`（默认，只发名单里的地址）／`redirect`（全部改发到一个地址，演示用）／`all`。演示数据的 zID 可能是真实学生的，所以默认不会发给名单外的人。
  - 发送失败只记日志，不影响预约。新命令 `manage.py send_test_email --to` 检查配置。
  - 为什么用 Gmail：Outlook.com 2024 年 9 月起不再接受密码登录 SMTP，要走微软授权且 Token 会过期。配置见 [email-setup.md](backend/docs/email-setup.md)。
- **新通知“申请已收到”**（`BOOKING_SUBMITTED`）：自己提交申请后，铃铛里（和邮件里）确认收到，并说明是在等审批还是在候补、什么时候会有结果。员工自己的重复预约也有确认（`SERIES_CREATED`）。原因：以前提交后没有任何书面确认。
- **Booking Records 页面**（Admin 和 Manager，`/admin/records`）：
  - Records 标签：按日期、资源、状态、姓名或 zID 查所有人的预约，显示预约人、创建人、状态和到场；Export CSV 导出同样的列表。
  - Usage statistics 标签：原来的 Usage Report 页面挪到这里，菜单里去掉 Usage Report（旧地址自动跳转）。
  - 接口：`GET admin/bookings/` 和 `export/` 新增 `q`（zID 或姓名的一部分，预约人或创建人）；导出 CSV 和使用情况报表对 Admin 开放；CSV 新增 Weekly series 和 Attendance 两列。
  - Room Management 只保留 Manager 的操作（开关房间、改期、取消），导出挪到 Booking Records。
  - 原因：客户要能查“谁在什么时候订了什么”，Admin 也需要。
- **界面**：
  - 时长统一用小时（`0.5 h`、`1 h`、`1.5 h`）。只有资源设置表单的时间步长仍用分钟。
  - My Bookings 里的重复预约合成一张卡片：规律（每周几、几点）、起止日期、还剩几次、下一次；当天的 I'm here 按钮直接显示在卡片上；Show dates 展开每个日期，可以单独取消；员工可以 Cancel the rest。以前一组 10 次会显示成 10 张卡片。
  - Book a Resource 顶部的大块 induction 横幅改成一行（`General ✓ · Advanced ✗ Upload`），有缺的才用提醒色。My Bookings 的日历订阅改成一个小按钮，点了才显示链接。
- OpenAPI 1.14.0。

## 1.13.0（2026-10-23）

Sprint 3 的第二批。不改数据库。新增的代码都标了 `Sprint 3`，清单见 [SPRINT3.md](SPRINT3.md)。

- **Manager 在网页上管理房间和设备**（新页面 Resources）：
  - 新增、编辑、下架、恢复：`GET/POST admin/resources/`、`PATCH admin/resources/{id}/`、`POST …/archive/`、`POST …/restore/`。
  - 原因：以前加资源要手写 SQL，交给客户之后他自己没法维护。
  - 修改不动已有预约，只列出不再符合新规则的未来预约，由 Manager 决定怎么处理。这样改开放时间不会悄悄取消别人的预约。
  - 只下架不删除，所以预约和审计记录始终能找到这个资源。
- **提醒**：预约开始前 24 小时提醒点 I'm here；induction 14 天内到期时提醒；候补或待审批的申请过期时通知。目的是减少“忘了来”和“资格过期才发现”。每条只发一次，靠查已有通知判断，不加表。新的可配置规则：`REMINDER_HOURS_BEFORE`、`INDUCTION_REMINDER_DAYS`。
- **使用情况报表**（新页面 Usage Report，`GET admin/reports/usage/`）：每个资源的预约次数、小时数、占开放时间的比例、到场率和缺席数，给客户评估设备使用情况。
- **员工修改自己的密码**（Account 页面，`POST auth/change-password/`）。以前只能让 Manager 重置。
- **`manage.py create_manager`**：建第一个 Manager 不用再手写 SQL。它和 Add staff 共用同一个函数 `_create_staff_account`，规则一样。
- **标注**：Sprint 3 的代码在文件里都标了 `Sprint 3`；ARCHITECTURE.md 新增“每条规则写在哪里”一节。
- OpenAPI 1.13.0。

## 1.12.0（2026-10-23）迁移 006

依据 2026-10-23 团队定稿的需求（日历订阅、通知、到场确认、每周上限、重复预约）。参考了 LibreBooking／Booked Scheduler（签到、自动释放、配额、iCal）、NEMO（未到场处理）和 MRBS（重复预约）的做法。

- **日历订阅链接**：每人一条私密地址（`GET calendar/link/`，可以 `POST calendar/link/reset/` 重新生成），Outlook／Google／苹果日历自己定期读取 `GET calendar/{token}.ics`。不需要微软授权，解决了“进每个人自己的日历”的问题；更新频率由日历软件决定。
- **站内通知**：顶部铃铛（`GET notifications/`、标为已读）。预约被批准或拒绝、候补转正、被 Manager 改期、被员工取消、员工替你预约、induction 审核结果、缺席、冻结和解冻都会通知；Manager 收到紧急申请。普通新申请不通知管理员。给 Outlook／邮件通知留了发送渠道接口（`booking/notification_channels.py`、`NOTIFICATION_CHANNELS`），这次没有实现。
- **到场确认与冻结**：已批准的预约要在开始前 15 分钟到开始后 30 分钟内由本人点 I'm here（`POST bookings/{id}/check-in/`），否则记缺席（资源维修或关闭时不算）。第 4 次缺席冻结 30 天，并取消这个人之后所有的预约和申请；冻结只影响预约，员工照常审批。被冻结的人可以提交解冻申请，Admin／Manager 在新页面 Booking freezes 处理或直接解冻。
  - 讨论过的取舍：网站按钮在哪里都能点，所以只能防“忘了取消”，防不住故意作弊；更可靠的方式（门口二维码）列为待问客户。
- **每周上限**：每人每周（周一到周日）最多 3 个待审批、候补或已批准的预约（`WEEKLY_LIMIT_REACHED`），只在新建申请和 Manager 改期时检查，所以候补递补和超时自动处理不受影响。
- **员工的重复预约**：资源卡片上的 Repeat weekly，先预览每个日期，有问题的日期跳过，其余**直接批准**（员工自己创建，不需要自己批自己）。可以突破“最多提前 30 天”，最长 14 周；不受每周上限限制。
- 新的可配置规则：`MAX_BOOKINGS_PER_WEEK`、`CHECK_IN_OPENS_MINUTES`、`CHECK_IN_CLOSES_MINUTES`、`FREEZE_AFTER_NO_SHOWS`、`FREEZE_DAYS`、`MAX_SERIES_WEEKS`。
- 迁移 006：新表 `notification`、`calendar_feed`、`unfreeze_request`、`booking_series`；用户加缺席次数和冻结截止时间；预约加系列、到场标记。已经开始的已批准预约标为 `NOT_TRACKED`，不会被算成缺席。
- OpenAPI 1.12.0。另外修正了几处可空字段和 `ManagedUser` 的写法，让严格的校验器也能通过（接口本身不变）。

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
