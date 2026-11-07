# Sprint 3 新增的功能和代码

这份清单列出 Sprint 3 加入的全部功能，以及每项功能对应的文件、函数、接口、页面和测试，方便检查和演示。Sprint 3 以前的代码都没有列进来。

> **2026-10-25 补充（deepseek修改，Loy已审核）**：本文件记录**已经实现**的 Sprint 3 功能；下面新增一节写 Sprint 3 的目标与范围（未实现，供规划）。Sprint 2 的计划见 [SPRINT2.md](SPRINT2.md)。

## Sprint 3 目标与范围（2026-10-25 规划，未实现）

一句话目标：部署到云上、有真实数据量、接客户真实登录。

| 编号 | 项 | 要做到 | 依赖/风险 |
| --- | --- | --- | --- |
| S3-1 | 可视化 | Usage statistics 图表、Today 页面图形、Room Management 时间轴、My Bookings 进度条；倾向手写 SVG，不引入图表库 | 无外部依赖，纯前端 |
| S3-2 | 云部署 | 选平台、PostgreSQL 托管、HTTPS、环境变量、上传文件持久化、备份 | 需要 Loy 选型；注意 induction 文件和 Outlook token 的存放 |
| S3-3 | 压力测试 | k6 或 Locust：并发查可用时间、并发抢同一时段、审批吞吐；给出 P95 和错误率 | 需要先有云环境 |
| S3-4 | 真实 SSO | UNSW 的 OAuth/SAML 接入 | **强依赖客户**，申请审批可能 2–4 周 |
| S3-5 | 真实 Outlook | 学校账号或学生个人账号的 Graph/Google 接入 | **强依赖客户**；先确认账号类型（见 `claude/reports/2026-10-25-outlook-personal-calendar.md`） |

建议顺序：云部署 → 压力测试 → 可视化 → 真实 SSO/Outlook（客户到位再做）。S3-4、S3-5 是外部依赖，应在 Sprint 2 期间就开始向客户申请。

**代码里怎么认出 Sprint 3 的部分**
- 新文件：第一行注明 `Sprint 3`。
- 改动过的旧文件：新增的代码段前有 `Sprint 3` 注释，或行尾有 `# Sprint 3`。

**版本**：接口 OpenAPI 1.12.0 到 1.16.0；数据库迁移 006（1.12.0）和 007（1.16.0），1.13.0 到 1.15.0 不改数据库。每项改动的原因见 [CHANGELOG.md](CHANGELOG.md)；每条规则写在哪个函数里，见 [ARCHITECTURE.md](ARCHITECTURE.md) 第 10 节。

## 功能一览

| # | 功能 | 谁用 | 页面 | 版本 |
| --- | --- | --- | --- | --- |
| 1 | 日历订阅链接 | 所有人 | My Bookings | 1.12.0 |
| 2 | 站内通知（铃铛） | 所有人 | 顶部栏 | 1.12.0 |
| 3 | 到场确认、缺席、冻结与解冻 | 所有人；员工处理解冻 | My Bookings、Booking Freezes | 1.12.0 |
| 4 | 每人每周最多 3 个预约 | 所有人 | Book a Resource | 1.12.0 |
| 5 | 员工的重复预约 | Admin、Manager | 资源卡片上的 Repeat weekly | 1.12.0 |
| 6 | Manager 在网页上管理房间和设备 | Manager | Resources | 1.13.0 |
| 7 | 提醒：预约快开始、induction 快到期、申请过期 | 所有人 | 铃铛 | 1.13.0 |
| 8 | 使用情况报表 | Admin、Manager（1.14.0 起） | Booking Records → Usage statistics | 1.13.0 |
| 9 | 员工修改自己的密码 | Admin、Manager | Account | 1.13.0 |
| 10 | `create_manager` 命令：建第一个 Manager | 部署的人 | 命令行 | 1.13.0 |
| 11 | 邮件通知（Gmail 系统邮箱）和“申请已收到”确认 | 所有人收；部署的人配置 | 邮箱、铃铛 | 1.14.0 |
| 12 | Booking Records：查、筛选、导出所有人的预约 | Admin、Manager | Booking Records | 1.14.0 |
| 13 | 重复预约在 My Bookings 里合成一张卡片 | 所有人 | My Bookings | 1.14.0 |
| 14 | 时长用小时显示；页面顶部更紧凑 | 所有人 | Book a Resource、My Bookings 等 | 1.14.0 |
| 15 | 可视化第一部分：铃铛动效和面板、资源封面、时间格配色和“现在”线、基础动效 | 所有人 | 顶部栏、Book a Resource、所有页面 | 1.15.0 |
| 16 | 用户体验报告的修改：申请改期、维修通知、联系方式、induction 说明、资源信息、Find a free time 说明原因、预约表单、员工首页 Today | 所有人；Manager 填 Lab setup | My Bookings、Book a Resource、Induction & Training、Help、Today、Lab setup 等 | 1.16.0 |

## 1. 日历订阅链接

每人一条私密地址，在 Outlook（或 Google、苹果日历）里选“从 Internet 订阅”即可。不需要微软授权。

- **后端**：
  - `booking/services/calendar_feed.py`：`calendar_feed`（生成或重置随机码）、`calendar_feed_events`（订阅里有哪些预约）。
  - `booking/ics.py`：`render_calendar`（iCalendar 文本）。
  - `views/calendar.py`：`CalendarLinkView`、`CalendarLinkResetView`、`CalendarFeedView`。
- **接口**：`GET calendar/link/`、`POST calendar/link/reset/`、`GET calendar/{token}.ics`（不需要登录，随机码就是钥匙）。
- **前端**：`features/booking/CalendarSubscribe.tsx`，地址拼接在 `features/booking/attendance.ts` 的 `calendarUrl`。
- **数据**：表 `calendar_feed`。
- **测试**：`test_sprint3.py` `CalendarFeedTests` 和 `test_calendar_link_and_public_feed`。

## 2. 站内通知

- **后端**：
  - `booking/services/notifications.py`：
    - `_booking_changed`：每次保存预约都会调用，统一判断要不要通知。
    - `_notify`、`_notify_managers`。
    - `list_notifications`、`mark_notification_read`、`mark_all_notifications_read`。
  - 发送渠道的接口（预留给 Outlook 或邮件）：`booking/notification_channels.py`，在 `middleware.py` 的 `NotificationDeliveryMiddleware` 里调用，配置项是 `NOTIFICATION_CHANNELS`。
- **接口**：`GET notifications/`、`POST notifications/{id}/read/`、`POST notifications/read-all/`。
- **前端**：`features/notifications/`，包括 `NotificationBell.tsx`、`notifications.ts` 和 `notifications.css`。
- **数据**：表 `notification`。
- **测试**：`test_sprint3.py` `NotificationTests` 和 `test_notifications_api`；`test_extra_channels_receive_new_notifications_after_the_request`；前端 `tests/sprint3.test.mjs`。

## 3. 到场确认、缺席、冻结与解冻

- **规则**：
  - 开始前 15 分钟到开始后 30 分钟内，本人要点 I'm here，否则记一次缺席。资源当时在维修或关闭的不算。
  - 第 4 次缺席冻结 30 天：期间不能被预约，之后的预约和申请全部取消。**1.24.0 起默认关闭**（`FREEZE_AFTER_NO_SHOWS=0`），缺席照常记录。
  - 冻结只看 zID，员工被冻结仍然能审批别人的申请。
  - 被冻结的人可以申请解冻，由 Admin／Manager 同意或拒绝，也可以直接解冻。
- **后端**：`booking/services/attendance.py`：
  - 到场：`check_in_window`、`check_in_state`、`check_in`；
  - 缺席与冻结：`_process_attendance`、`_freeze`、`frozen_violation`；
  - 解冻：`request_unfreeze`、`review_unfreeze`、`unfreeze`。
- **接口**：
  - `POST bookings/{id}/check-in/`
  - `GET/POST account/unfreeze-requests/`
  - `GET admin/unfreeze-requests/`、`POST admin/unfreeze-requests/{id}/review/`
  - `GET admin/frozen-users/`、`POST admin/users/{id}/unfreeze/`
- **前端**：
  - My Bookings 里的 I'm here 按钮：`MyBookings.tsx`、`attendance.ts`；
  - 冻结提示和解冻申请：`FreezeNotice.tsx`；
  - 员工页面：`features/admin/FreezesPage.tsx`（Booking Freezes）。
- **数据**：
  - `app_users.no_show_count`、`frozen_until`；
  - `booking.attendance`、`checked_in_at`；
  - 表 `unfreeze_request`。
- **测试**：`test_sprint3.py` `AttendanceTests`、`test_unfreeze_api`、`test_check_in_and_booking_fields`；`test_postgres.py` `test_weekly_series_check_in_and_freeze_are_persisted`。

## 4. 每人每周最多 3 个预约

- **后端**：`booking/services/checks.py` `_weekly_limit_violation`，在 `bookings.py` 的 `create_booking` 和 `reschedule_booking` 里调用。
- **错误**：`WEEKLY_LIMIT_REACHED`。
- **测试**：`test_sprint3.py` `WeeklyLimitTests`、`test_weekly_limit_api_error`。

## 5. 员工的重复预约

- **后端**：`booking/services/series.py`：`_series_plan`、`_series_check`、`preview_series`、`create_series`（直接批准）、`series_detail`、`cancel_series`。
- **接口**：`POST bookings/series/preview/`、`POST bookings/series/`、`GET bookings/series/{id}/`、`POST bookings/series/{id}/cancel/`。
- **前端**：`features/booking/RecurringBookingForm.tsx`、`series.ts`；入口是资源卡片 `ResourceCard.tsx` 上的 Repeat weekly（`BookingApp.tsx`）。
- **数据**：表 `booking_series`、`booking.series_id`。
- **测试**：`test_sprint3.py` `SeriesTests`、`test_series_api`；Playwright `staff book a weekly series…`。

## 6. Manager 在网页上管理房间和设备

- **规则**：都在 `booking/services/resources.py` 开头的说明里：
  - 必填名称、地点和所需 induction；名称不重复。
  - 房间不能有所在房间和类别。
  - 时间要落在 15／30／60 分钟的步长上；最长时长要放得进开放时间。
  - 类型创建后不能改。
  - 修改不动已有预约，而是列出不再符合新规则的预约。
  - 只下架不删除；还有未来预约，或房间里还有设备时不能下架。
- **后端**：`booking/services/resources.py`：
  - 主要函数：`list_all_resources`、`create_resource`、`update_resource`、`archive_resource`、`restore_resource`；
  - 字段规则：`_check_resource_fields`；
  - 编辑后受影响的预约：`_bookings_outside_rules`。
- **接口**：`GET/POST admin/resources/`、`PATCH admin/resources/{id}/`、`POST admin/resources/{id}/archive/`、`POST admin/resources/{id}/restore/`。
- **前端**：`features/manager/ManagerResourcesPage.tsx`（Resources），表单规则在 `features/manager/resource-form.ts`。
- **数据**：不改表结构，沿用 `bookable_resource`。
- **测试**：`test_resource_setup.py`；`test_postgres.py` `test_resource_setup_is_persisted`；前端 `tests/resource-form.test.mjs`；Playwright `a Manager adds equipment…`、`Admins do not see the Resources page`。

## 7. 提醒

- **规则**：
  - 已批准的预约开始前 24 小时提醒点 I'm here；
  - 已通过的 induction 14 天内到期时提醒；
  - 候补或待审批的申请到开始时间还没轮到或没人决定，通知“已过期”。
  - 每条只发一次。
- **后端**：
  - `booking/services/reminders.py`：`_send_reminders`、`_booking_reminders`、`_induction_reminders`，在 `waitlist.py` 的 `process_due_requests` 最后调用。
  - 2026-11-01：提醒调用 `notifications.py` 的 `_notify(..., once=True)`，在写锁内按收件人和预约／induction 链接复查，避免网页请求和 scheduler 同时生成重复通知及邮件。
  - “已过期”通知在 `notifications.py` `_booking_changed` 里。
  - 规则数字：`rules.py` 的 `reminder_hours_before`、`induction_reminder_days`。
- **测试**：`test_reminders.py`；`test_postgres.py` 的两个 `test_concurrent_*_reminders_create_one_notification_and_email` 在真实数据库上验证并发去重。

## 8. 使用情况报表

- **后端**：`booking/services/reports.py` `usage_report`（只读）。
- **接口**：`GET admin/reports/usage/?first_date=&last_date=`。
- **前端**：`features/records/UsageTab.tsx`（1.14.0 起是 Booking Records 的 Usage statistics 标签，以前是单独的 Usage Report 页面 `ManagerUsagePage.tsx`）、`features/manager/usage.ts`。
- **测试**：`test_usage_report.py`；前端 `tests/usage.test.mjs`；Playwright `an Admin reads the usage statistics on Booking Records`、`the old Usage Report address opens the usage statistics tab`。

## 9. 员工修改自己的密码

- **后端**：`booking/services/accounts.py` `change_password`。
- **接口**：`POST auth/change-password/`。
- **前端**：`features/auth/ChangePassword.tsx`，显示在 Account 页面（`app/UtilityPages.tsx`）。
- **测试**：`test_change_password.py`；Playwright `staff change their password…`、`students have no password form`。

## 10. `create_manager` 命令

- **用法**：`python manage.py create_manager --zid z9000003 --name "Lab Manager" --email z9000003@ad.unsw.edu.au`，输出一次性邀请码。
- **后端**：
  - 命令：`booking/management/commands/create_manager.py`。
  - 业务：`booking/services/accounts.py` 的 `bootstrap_manager`。它和 Add staff 共用 `_create_staff_account`，两条路径规则完全一样。
- **测试**：`test_create_manager.py`。

## 11. 邮件通知和“申请已收到”

- **规则**：
  - 发给预约人（受益人）的大学邮箱；哪些通知发邮件见 `settings.py` 的 `EMAIL_NOTIFICATION_KINDS`。
  - `EMAIL_MODE` 决定谁真的收到：`none`、`allowlist`（默认）、`redirect`（演示：全部改发给一个地址）、`all`。
  - 发送失败只记日志，不影响预约。
- **后端**：
  - `booking/email_channel.py`：`EmailChannel.deliver`（选不选发，写好后放进队列）、`choose_recipient`（按模式选收件人）、`compose`（主题和正文）、`booking_label`、`site_link`；`EmailOutbox`（2026-10-27：后台线程发送，同一批共用一条连接，每封记日志）；`notification_channels.wait_for_deliveries`（命令和测试等后台发完）。日志设置在 `config/settings.py` 的 `LOGGING`。
  - 配置：`config/settings.py` 的 `EMAIL_*`、`SITE_URL`；`EMAIL_ENABLED=true` 时把邮件渠道加进 `NOTIFICATION_CHANNELS`。
  - 命令：`booking/management/commands/send_test_email.py`。
  - “申请已收到”：`services/bookings.py` `_created_notices`（`BOOKING_SUBMITTED`）；员工自己的重复预约：`services/series.py` `create_series`（`SERIES_CREATED`）；时间文字 `services/notifications.py` `describe_moment`。
- **文档**：`backend/docs/email-setup.md`。
- **测试**：`test_email_channel.py`（2026-10-27 新增：`test_the_response_does_not_wait_for_the_mail_server`、`test_emails_waiting_together_share_one_connection`、`test_each_sent_email_is_logged_with_its_notification_and_recipient_domain`、`test_a_mail_server_that_cannot_be_reached_is_logged_and_later_emails_still_go`）；`test_sprint3.py` 里关于 `BOOKING_SUBMITTED`、`SERIES_CREATED` 的断言。

## 12. Booking Records

- **后端**：
  - `services/resources.py` `booking_report` 新增 `query`（zID 或姓名的一部分，预约人或创建人）。
  - `serializers.py` `AdminBookingQuerySerializer` 新增 `q`；`views/admin.py` `staff_booking_rows` 把它传下去。
  - `views/admin.py` `AdminBookingExportView` 改为 Admin 也能用，CSV 加 Weekly series、Attendance 两列；`services/reports.py` `usage_report` 改为 Admin 也能用。
- **接口**：`GET admin/bookings/?q=`、`GET admin/bookings/export/?q=`。
- **前端**：
  - 页面 `features/records/BookingRecordsPage.tsx`（Records 和 Usage statistics 两个标签），筛选换成接口参数在 `features/records/records.ts`（`recordQuery`、`sydneyMidnight`、`creatorText`、`attendanceText`）。
  - 接口 `features/booking/api.ts` 的 `listBookingRecords`、`downloadBookingRecords`。
  - 路由 `/admin/records`（`routes.ts`、`AppRouter.tsx`、`AppLayout.tsx`）；旧地址 `/manager/usage` 跳转过来。
  - `features/manager/ManagerBookingsPage.tsx` 去掉导出按钮。
- **测试**：`test_manager_tools.py`（`q` 搜索、Admin 导出、新列）、`test_usage_report.py`；前端 `tests/sprint3-records.test.mjs`；Playwright `staff search booking records and export the same list as CSV`、`students do not see Booking Records`。

## 13. 重复预约合成一张卡片

- **前端**：`features/booking/my-bookings.ts`（`groupBookings`、`seriesSummary`）；`MyBookings.tsx` 的 `SeriesCard`。
- **测试**：`tests/sprint3-records.test.mjs`；Playwright `my bookings shows a weekly series as one card`。

## 14. 时长用小时、页面顶部更紧凑

- **前端**：
  - `features/booking/format.ts` `fmtDuration`（`1.5 h`）；“几分钟前”另用 `fmtSpan`。`FindTime.tsx` 的时长下拉也用它。
  - `BookingApp.tsx`：induction 一行（`bk-induction-strip`）。
  - `CalendarSubscribe.tsx`：先只显示 Subscribe in calendar 按钮。
  - 样式在 `booking.css` 末尾的 Sprint 3 段。
- **测试**：`tests/sprint3-records.test.mjs`；Playwright `book a resource shows all inductions on one line with an upload link`、`my bookings: check in, and get the calendar subscription link`。

## 15. 可视化第一部分

- **铃铛**：
  - `features/notifications/notifications.ts`：`notificationIcon`（类型 → 图标）、`groupNotifications`（按悉尼日期分“今天 / 更早”）、`shouldRing`（未读数增加才摆，第一次加载不摆）。
  - `NotificationBell.tsx`：`ringKey` 重新挂载图标来重播摆动，角标用 `key={badge}` 重播弹出；面板分组、图标（`KindIcon`）、两行正文、未读蓝点。
  - 样式 `notifications.css`：角标选择器 `.nt-bell-button > .nt-badge`（压过 `shell.css` 的 27px）、`nt-ring`、`nt-pop`、`nt-panel-in`；窄屏（≤600px）面板改为固定在屏幕上。
- **资源封面**：`features/booking/covers.ts` `coverKey`（房间／类别／名称里的关键词 → 封面类型）；`ResourceCard.tsx` 的 `ResourceCover`、`COVER_ICONS`；样式在 `booking.css` 的 `.bk-cover` 段。
- **时间格**：配色和边框在 `ui/ui.css` 的 `.ui-tl-*`、`.ui-legend` 段；“现在”线：`features/booking/slot-cells.ts` `nowLineFraction`，组件 `features/booking/NowLine.tsx`（`NowLine`、`NowLegend`），用在 `SlotPicker.tsx` 和 `FindTime.tsx`。
- **基础动效**：变量 `--motion-fast`、`--motion-base`、`--ease-out`、`--ease-spring` 和“减少动态效果”总开关在 `index.css`；页面淡入 `app/AppLayout.tsx`（`app-page`，`key={pathname}`）和 `app/shell.css`；弹窗 `booking.css`（`bk-modal-in`）、确认框和按钮 `ui/ui.css`；首页数字卡片 `features/dashboard/dashboard.css`。
- **测试**：`tests/sprint3-visual.test.mjs`；Playwright `the bell badge stays small, and the panel groups notifications with an icon each`。

## 16. 用户体验报告的修改（1.16.0）

- **申请改期**：
  - 后端：`services/changes.py`（`ChangesMixin`）`request_time_change`（谁能申请、什么时候能申请）、`open_change_for`、`_apply_time_change`（新申请批准时取消原预约，在 `base.py` `_save_booking` 里调用）。`bookings.py` `create_booking` 的 `replaces` 参数：重复、每周上限和冲突检查都排除原预约；`checks.py` `_overlaps` 的 `also_exclude`；`waitlist.py` 递补时同样排除。通知在 `notifications.py`（`CHANGE_REQUESTED`／`CHANGE_APPROVED`／`CHANGE_REJECTED`，`_old_time_note`）。
  - 数据：`Booking.replaces_id`；数据库 `booking.replaces_id` 和部分唯一索引 `booking_one_open_change_idx`（一个预约只能有一个待处理的改期）。
  - 接口：`POST bookings/{id}/change/`（`views/bookings.py` `BookingChangeView`）；预约 JSON 新增 `replaces_booking`、`open_change`。
  - 前端：`features/booking/ChangeTimeBox.tsx`、`change-requests.ts`（`canAskForChange`、`openChangeText`、`replacesText`、`changeSentMessage`）；`MyBookings.tsx` 的 Change time；`SlotPicker.tsx` 的 `takenNote`（选到被占用的时间时提示只能候补）。
- **维修和关闭通知**：`services/resources.py` `set_resource_status` → `_notify_status_change`（`RESOURCE_OUT_OF_SERVICE`／`RESOURCE_REOPENED`，每个受影响的预约一条，状态真的变了才发）；邮件类型在 `settings.py` `EMAIL_NOTIFICATION_KINDS`。前端 `ManagerBookingsPage.tsx` 的确认框和 `is-attention` 行。
- **联系方式**：`domain.py` `SiteContact`；`services/site_contact.py`（`site_contact`、`update_site_contact`）；新表 `site_contact`（只有一行）；接口 `GET/PATCH site/contact/`（`SiteContactView`）。前端 `features/contact/contact.ts`（`hasContact`、`mailtoLink`）、`site-contact-store.ts`（`useSiteContact`）、`LabContact.tsx`（`LabContactCard`、`ContactLink`），用在 Help、My Bookings 和 induction 说明里。
- **induction 说明和新建**：`QualificationRequirement` 的 `how_to_complete`、`accepted_evidence`、`reviewer`、`contact`；`services/qualifications.py` `create_requirement`、`update_requirement`、`_check_requirement_fields`；接口 `POST admin/qualification-requirements/`、`PATCH …/{id}/`。前端 `features/induction/guide.ts`（`guideItems`）、`InductionGuide.tsx`；`InductionRow.tsx` 显示说明。
- **Lab setup 页面**（Manager，`/manager/setup`）：`features/manager/LabSetupPage.tsx`（Inductions 和 Contact details 两个标签）、`lab-setup.ts`（`requirementChanges` 只发改了的字段）。
- **资源信息**：`domain.py` `ResourceDetail`、`Resource.capacity`／`details`；`services/resources.py` `_check_resource_fields`（容量 1–1000 且只有房间，最多 `MAX_DETAILS = 12` 行）；数据库 `bookable_resource.capacity`、`details jsonb`（`postgres.py` 的 `_JSON_LISTS`）。前端 `ResourceCard.tsx` `ResourceFacts`；`BookingApp.tsx` 的 Fits at least 筛选；`ManagerResourcesPage.tsx` 的 `DetailsEditor`；`resource-form.ts` 的检查和小时换算（`hoursFromMinutes`、`minutesFromHours`、`describeHours`）。
- **房间和设备分开预约的说明**：`features/booking/format.ts` `SEPARATE_BOOKING_TEXT`，显示在 `BookingForm.tsx` 和 `BookingApp.tsx`。
- **Find a free time**：后端 `services/availability.py` `day_overview` 的 `too_long`、`not_bookable`；前端 `features/booking/find-time.ts`（`FIND_DURATIONS`、`hiddenSummary`）、`FindTime.tsx`。
- **预约表单**：`format.ts` `submitBlocker`（还差什么）；`BookingForm.tsx`（必填标记、`bk-submit-row`）；`SlotPicker.tsx`（`onAskEarlier`、开始时间和时长下拉 `chooseByInputs`）。
- **员工首页 Today**：`services/overview.py` `staff_overview`（`DUE_SOON_HOURS = 6`、`LIST_LIMIT = 10`）；接口 `GET admin/overview/`（`StaffOverviewView`）。前端 `features/admin/TodayPage.tsx`、`today.ts`（`todoCards`、`attendanceLabel`）；`app/routes.ts` `homePath` 让员工进 `/admin/today`。
- **其他**：`BookingReviewPage.tsx`（Purpose 列、Details 按钮、Change from）；`CalendarSubscribe.tsx`（`CALENDAR_APPS`）；样式在 `booking.css` 和 `ui/ui.css` 的 `Sprint 3 (1.16.0)` 段。
- **数据库**：`database/migrations/007_change_requests_guidance_details_contact.sql`（可重复执行），`schema.sql` 同步。
- **测试**：后端 `tests/test_change_requests.py`、`tests/test_lab_setup.py`，`test_postgres.py` 新增两项，`test_day_overview.py` 改了一项；前端 `tests/sprint3-review.test.mjs`；Playwright `a student asks to move a booking; a taken time can only join the waitlist`、`staff start on Today, whose cards open the pages that handle them`、`the induction page says how to get an induction and offers the lab's email`、`Find a free time says why nothing can be booked`、`a Manager saves the lab's contact details on Lab setup`。

## 所有新增文件

- **后端**：
  - 业务（`booking/services/`）：`attendance.py`、`calendar_feed.py`、`notifications.py`、`series.py`、`reminders.py`、`reports.py`、`changes.py`、`site_contact.py`、`overview.py`（后三个 1.16.0）
  - 其他代码：`booking/ics.py`、`booking/notification_channels.py`、`booking/email_channel.py`、`booking/management/commands/create_manager.py`、`send_test_email.py`
  - 迁移：`database/migrations/006_calendar_notifications_attendance_series.sql`、`007_change_requests_guidance_details_contact.sql`（1.16.0）
  - 测试（`booking/tests/`）：`test_sprint3.py`、`test_resource_setup.py`、`test_reminders.py`、`test_usage_report.py`、`test_change_password.py`、`test_create_manager.py`、`test_email_channel.py`、`test_change_requests.py`、`test_lab_setup.py`（后两个 1.16.0）
- **前端**：
  - 页面和组件：
    - `features/admin/FreezesPage.tsx`
    - `features/auth/ChangePassword.tsx`
    - `features/booking/CalendarSubscribe.tsx`、`FreezeNotice.tsx`、`RecurringBookingForm.tsx`
    - `features/manager/ManagerResourcesPage.tsx`（`ManagerUsagePage.tsx` 在 1.14.0 改成 `features/records/UsageTab.tsx`）
    - `features/records/BookingRecordsPage.tsx`、`UsageTab.tsx`
    - `features/notifications/NotificationBell.tsx`
    - `features/booking/NowLine.tsx`（1.15.0）
    - 1.16.0：`features/booking/ChangeTimeBox.tsx`、`features/admin/TodayPage.tsx`、`features/manager/LabSetupPage.tsx`、`features/contact/LabContact.tsx`、`features/induction/InductionGuide.tsx`
  - 辅助文件：
    - `features/booking/attendance.ts`、`series.ts`、`my-bookings.ts`
    - `features/records/records.ts`
    - `features/manager/resource-form.ts`、`usage.ts`
    - `features/notifications/notifications.ts`、`notifications.css`
    - `features/booking/covers.ts`（1.15.0）
    - 1.16.0：`features/booking/change-requests.ts`、`find-time.ts`、`features/admin/today.ts`、`features/manager/lab-setup.ts`、`features/contact/contact.ts`、`site-contact-store.ts`、`features/induction/guide.ts`
  - 测试：`tests/sprint3.test.mjs`、`tests/resource-form.test.mjs`、`tests/usage.test.mjs`、`tests/sprint3-records.test.mjs`、`tests/sprint3-visual.test.mjs`（1.15.0）、`tests/sprint3-review.test.mjs`（1.16.0）、`tests/ui-internal-tool.test.mjs`（第 20 节）
- **文档**：`SPRINT3.md`（本文件）、`backend/docs/email-setup.md`

## 改动过的旧文件（新增部分都标了 Sprint 3）

- **后端**：
  - 实体和存储：`domain.py`、`repository.py`、`postgres.py`
  - 规则和配置：`rules.py`、`config/settings.py`、`.env.example`
  - 接口：`serializers.py`、`views/`、`urls.py`、`middleware.py`
  - 业务（`booking/services/`）：`__init__.py`、`accounts.py`、`availability.py`、`base.py`、`bookings.py`、`checks.py`、`qualifications.py`、`resources.py`、`waitlist.py`
  - 命令：`management/commands/process_due.py`
  - 数据库：`database/schema.sql`
  - 测试：`tests/test_postgres.py`、`tests/test_user_management.py`、`tests/test_manager_tools.py`、`tests/test_day_overview.py`（1.16.0）
- **前端**：
  - 框架：`app/AppLayout.tsx`、`app/AppRouter.tsx`、`app/routes.ts`、`app/UtilityPages.tsx`
  - 预约页面：`features/booking/BookingApp.tsx`、`MyBookings.tsx`、`ResourceCard.tsx`、`FindTime.tsx`、`SlotPicker.tsx`、`slot-cells.ts`、`BookingForm.tsx`、`icons.tsx`（后两个 1.16.0）
  - 其他页面（1.16.0）：`features/admin/BookingReviewPage.tsx`、`features/induction/InductionRow.tsx`
  - 全局样式（1.15.0）：`index.css`、`app/shell.css`、`ui/ui.css`、`features/dashboard/dashboard.css`
  - Manager 页面：`features/manager/ManagerBookingsPage.tsx`
  - 接口、类型和格式：`features/booking/api.ts`、`types.ts`、`format.ts`、`booking.css`
  - 测试：`tests/routing.spec.ts`、`tests/session-routing.test.mjs`（1.16.0）
- **文档**：
  - 根目录：`ARCHITECTURE.md`、`CHANGELOG.md`、`README.md`
  - 后端：`backend/README.md`、`backend/database/README.md`、`backend/docs/frontend-api.md`、`backend/docs/database-interface.md`、`backend/docs/outlook-setup.md`、`backend/docs/email-setup.md`、`backend/docs/openapi.json`
  - 前端：`frontend/README.md`

## 17. Functional controls (1.17.0)

| ID | Main code and entry points | Verification |
| --- | --- | --- |
| FC-01 | `frontend/src/features/booking/BookingForm.tsx`: one required urgent explanation, shared request values | `TestConsoleAPITests.test_urgent_shared_description_is_saved_and_directly_approved`; interactive browser verification remains pending |
| FC-02 | `backend/booking/test_console.py`: gates, ephemeral signed identity, self-only booking policy, time views; `authentication.py`, `views/`, `serializers.py`, `urls.py`: `auth/test-login/`, `auth/test-session/`; `services/bookings.py`, `availability.py`, `series.py`: create/move/recurrence; `services/base.py`, `notification_channels.py`: suppress external delivery | `backend/booking/tests/test_test_console.py` (15 API cases including ordinary-account protection, disabled gates, conflicts, recurrence and moves) |
| FC-02 UI | `features/auth/TestLoginPage.tsx`, `TestConsoleBar.tsx`; `AppRouter.tsx`, `AppLayout.tsx`, `LoginPage.tsx`; booking `SlotPicker.tsx`, `FindTime.tsx`, `ResourceCard.tsx`, `RecurringBookingForm.tsx`, `ChangeTimeBox.tsx`, `change-requests.ts`; `UtilityPages.tsx` hides password form on the test account | Frontend unit, lint and build; real browser checks remain pending |
| FC-03 | `features/induction/InductionPage.tsx`, `evidence.ts`, booking `booking.css`: required evidence and English picker | `frontend/tests/evidence.test.mjs`; backend existing multipart file validation |

Paths in the UI row are relative to `frontend/src/`. API types/client additions are in `features/booking/types.ts` and `api.ts`. No migration is needed: the stored principal is an ordinary STUDENT record; override fields exist only in the signed session.

## 18. Workspace UI iteration (API remains 1.17.0)

| ID | Code locations under frontend | Verification |
| --- | --- | --- |
| UI-01 | `src/ui/workspace.css`, `src/App.tsx`, `src/app/AppLayout.tsx`, `src/ui/components.tsx`; `public/fonts/` and included OFL licenses | Lint, build; desktop and phone visual review |
| UI-02 | `src/features/dashboard/DashboardPage.tsx`, `dashboard.css`; booking `ResourceCard.tsx`, `BookingApp.tsx`; admin `TodayPage.tsx` | Live memory-backend walkthrough: student request, Manager approval, populated dashboard; existing Today routing check |
| UI-03 | `src/features/booking/FindTime.tsx`, `SlotPicker.tsx`, `BookingForm.tsx` | Routing check: no query before submit, stale results disabled, selected interval retained, timeline collapsed, Escape and focus return; empty-result reasons retained |
| UI-04 | `src/features/booking/MyBookings.tsx` | Routing check: tabs filter locally without another booking read; selected URL view survives reload |
| UI-05 | `src/features/booking/Modal.tsx`, `src/ui/workspace.css` | Native dialog and keyboard test; 390 px visual walkthrough, desktop approval and records pages |

No API/schema/authentication policy changes. The time-search response still includes server-calculated slots; request timing and presentation changed on the client. Visual review is a design judgement, not a certification against award winners.

Review fixes (Claude). R1–R7 use the IDs of the code review in project docs `claude/reports/2026-10-25-workspace-ui-review.md`; “UI review #1” is item 1 of `claude/reports/2026-10-25-ui-review.md`:

| ID | Code locations under frontend | Verification |
| --- | --- | --- |
| R1 | `src/features/booking/MyBookings.tsx` `RescheduleBox` (inline error); `Modal.tsx` docstring | Routing test “Room Management shows a failed reschedule inside the dialog” |
| R2 | `src/features/booking/BookingApp.tsx` (training summary `open`, `verifiedCount`); `src/ui/workspace.css` `.bk-access-summary` | Routing test “book a resource keeps missing inductions open with an upload link” |
| R4 | `src/features/booking/Modal.tsx` (`pressedOnBackdrop`, `onBackdrop`) | Routing test “find a free time searches only on submit…”: drag from Purpose to the backdrop keeps the dialog; a backdrop click closes it |
| R5 | `Modal.tsx` `label` prop; callers `BookingApp.tsx`, `manager/ManagerBookingsPage.tsx` | Same routing tests find the dialog by its name |
| R7 | `Sprint 3` notes in `FindTime.tsx`, `SlotPicker.tsx`, `BookingForm.tsx`, `DashboardPage.tsx`, `BookingApp.tsx`; `.bk-overlay` removed from `booking.css`, `workspace.css` | Lint, build |
| UI review #1 | `src/ui/ui.css` `.ui-table-wrap` (`position: relative`); `src/ui/workspace.css` phone breakpoint: `.ui-tabs`, `.bk-pills`, `.bk-mode-tabs` scroll sideways | Routing test “phone width: tables and tab rows never make a page wider than the screen” (fails without either change: `/bookings` +176 px, `/manager/bookings` +81 px) |

## 19. Account 1 induction access (1.17.1)

FC-04: `backend/booking/test_console.py::_grant_test_inductions` grants all requirements as permanent VERIFIED records without files. `get_test_account` and `authentication.py::DemoIdentityProvider.resolve_bearer` cover login and existing sessions; new requirements are picked up automatically. `views/_common.py::submission_json` returns an empty file URL for fileless grants. `frontend/src/features/induction/InductionPage.tsx` hides the evidence form for the test account. No schema change.

Verification: `TestConsoleAPITests.test_all_inductions_are_permanent_fileless_and_survive_role_switches`, `test_existing_session_receives_new_requirements_without_duplicate_grants`, `test_bypass_off_keeps_inductions_but_restores_windows_and_approval`; routing test `test account 1 has verified inductions without an evidence upload form`. Existing tests retain ordinary-account restrictions, disabled-console rejection, conflict checks and self-only bypass.

## 20. Internal-tool UI, first pass (API remains 1.17.1)

Direction (Loy): a school's internal tool, not award-site styling. Task list: project docs `claude/tasks-ui-internal-tool.md` (AI-2, AI-3, AI-5, AI-6). Paths are under `frontend/`.

| ID | Code locations | Verification |
| --- | --- | --- |
| AI-2 copy | `src/features/dashboard/DashboardPage.tsx` (H1 “Dashboard”), `booking/FindTime.tsx`, `admin/TodayPage.tsx`, `booking/ResourceCard.tsx`, `booking/BookingApp.tsx`, `booking/MyBookings.tsx`, `induction/InductionPage.tsx`, `app/UtilityPages.tsx`, `app/AppRouter.tsx` (not-found page), `app/AppLayout.tsx` (no “Portal” title), `auth/AuthShell.tsx`, `auth/LoginPage.tsx`, `StaffLoginPage.tsx`, `TestLoginPage.tsx`; the 10 staff `PageHeader`s | `tests/ui-internal-tool.test.mjs`: removed phrases, no heading ending in a full stop; routing tests use the new copy |
| AI-3 type scale | `src/ui/workspace.css` (one shared H1 rule, scale comment), `ui/ui.css`, `app/shell.css`, `features/booking/booking.css`, `dashboard/dashboard.css`, `notifications/notifications.css`, `auth/auth.css`, `auth/mock-sso.css` | Unit tests: every `font-size` on 12/14/16/20/24/28 px; H1 size set once (+ phone). Screenshot metrics: no text below 12px |
| AI-5 one font, two radii | `src/ui/workspace.css` (Instrument Serif removed), `public/fonts/instrument-serif*` deleted, `auth/auth.css` uses Manrope; radii in the same stylesheets | Unit tests: font families, `border-radius` values. Exception: `auth/mock-sso.css` stands in for the university's Microsoft sign-in |
| AI-6 naming | `src/app/AppLayout.tsx` (menu), `app/AppRouter.tsx` (`titles`), page H1s; `features/booking/format.ts` `fmtClock`, `fmtHours` used by `ResourceCard.tsx`, `BookingForm.tsx`, `manager/ManagerResourcesPage.tsx`, `FindTime.tsx` | Unit tests: menu label = tab title, sentence case; `fmtClock`/`fmtHours`; routing tests find pages by the new names |

Also: `tests/routing.spec.ts` “book a resource keeps missing inductions open…” now waits for the Induction page before going back (it could collapse both navigations into one).

## 21. Code structure cleanup (2026-10-25)

No API, schema or booking-rule change. Report: project docs `claude/reports/2026-10-25-code-structure-review.md`.

| ID | Code locations | Verification |
| --- | --- | --- |
| SC-1 | `backend/booking/views/` (split from `views.py`): `_common.py`, `auth.py`, `resources.py`, `bookings.py`, `admin.py`, `outlook.py`, `notifications.py`, `calendar.py`, `series.py`, `unfreeze.py`, `misc.py`; `__init__.py` re-exports the same names | Backend test suite (355, 18 PostgreSQL skipped), Django system check |
| SC-2 | Frontend: `features/booking/RescheduleBox.tsx`, `SeriesCard.tsx`, `slot-picker.ts`; `MyBookings.tsx` and `SlotPicker.tsx` import them; `ManagerBookingsPage.tsx` imports `RescheduleBox` from its new file | Frontend unit (68), lint, build, Playwright routing tests |
| SC-3 | Dead motion code removed: duplicate `.app-page` in `app/shell.css`, duplicate dialog fade in `ui/workspace.css`, second reduced-motion rule in `index.css`, pressed-scale for `.ui-btn` in `ui/ui.css`, and the `animation: none` override for `.nt-ring`; the single reduced-motion rule now includes `::backdrop` | grep; frontend checks |
| SC-4 | `src/App.css` deleted (no import). | lint/build |
| SC-5 | Style layering documented in `frontend/README.md` (“Style layers”). | review |

## 22. Notification preferences and induction notice (1.18.0)

No booking-rule change. Migration 008 adds `notification_preference`.

| ID | Code locations | Verification |
| --- | --- | --- |
| NP-1 | `backend/booking/domain.py` `NotificationPreference`; `repository.py`, `postgres.py` (save/list); `services/notifications.py` `NOTIFICATION_CATEGORIES`, `notification_category`, `_notify` filter, `notification_preferences`, `save_notification_preferences`; `views/notifications.py` `NotificationPreferencesView`; `urls.py` `notifications/preferences/`; `serializers.py` `NotificationPreferencesSerializer` | `booking/tests/test_notification_preferences.py` (7 cases: defaults, switch off/on, per person, unknown category, refused save changes nothing) |
| NP-2 | `services/qualifications.py` `submit_qualification` sends `INDUCTION_SUBMITTED` (respects the induction switch) | same test file |
| NP-3 | Frontend: `features/notifications/NotificationPreferences.tsx`, `app/UtilityPages.tsx` Account card; `features/booking/api.ts` `getNotificationPreferences`/`saveNotificationPreferences`; `types.ts` `NotificationPreference`; `ui/workspace.css` `.app-pref-list` | unit, lint, build, routing tests (mock `notifications/preferences/`) |
| NP-4 | `ui/workspace.css`: `.bk-earlier .bk-linkbtn` is a yellow button (urgent route) | visual |
| NP-5 | `features/auth/LoginPage.tsx`: "Other demo sign-in options" removed; its routing test deleted | routing tests |
| DB | `database/migrations/008_notification_preferences.sql`, `schema.sql` `notification_preference` | `check-local.sh schema` |
| Docs | `backend/docs/openapi.json` 1.18.0 (69 routes), `backend/docs/frontend-api.md`, CHANGELOG 1.18.0 | openapi check |

## 23. Review fixes, demo sign-up and Docker deployment (API remains 1.18.0)

No API, schema or booking-rule change. Review: project docs `claude/reports/2026-10-25-review-1.18.0.md`.

| ID | Code locations | Verification |
| --- | --- | --- |
| RV-D1 | `features/booking/SlotPicker.tsx` wheel effect (depends on `data`; hands the wheel back to the page at either end) | routing test `a mouse wheel scrolls the day timeline sideways once the day has loaded` (fails on the old effect) |
| RV-D2 | `services/notifications.py` `save_notification_preferences` (check all names, then save in `repo.atomic()`) | `test_notification_preferences.py` `test_a_refused_save_changes_nothing` |
| SU-1 | `features/auth/MockSsoPage.tsx` `create` (Create one → Create account form, `demoRegister`); `features/auth/mock-sso.css` `.mock-sso-create`, `.mock-sso-back` | routing tests `a new demo student creates an account on the mock sign-in page`, `the mock sign-in page offers no sign-up when demo registration is off` |
| DK-1 | `docker-compose.yml`, `.env.docker.example`, `backend/Dockerfile`, `backend/entrypoint.sh` (new database: schema + optional `seed_*.sql` in one transaction; `migrate` subcommand), `backend/.dockerignore`, `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/.dockerignore`; steps in `DEPLOY.md` | `entrypoint.sh` run against a temporary local PostgreSQL (new database, restart keeps a changed password, `migrate`); containers not yet run (no Docker on the dev machine) |
## 24. 通知独立渠道与公告栏（1.19.0，Sprint 3）

范围：任务清单 N1、N2、A1–A4、D1；不做 D2，不改 Docker / 部署文件，不重新部署 EC2。

| 项 | 文件和主要函数 | 自动验证 |
| --- | --- | --- |
| N1 设置页和侧栏 | `frontend/src/features/notifications/NotificationPreferences.tsx`；`app/routes.ts`、`AppRouter.tsx`、`AppLayout.tsx`、`UtilityPages.tsx`；`features/booking/api.ts`、`types.ts`；`ui/workspace.css` | `routing.spec.ts` 三种角色的 `1.19 notifications`：五类十开关、失败不丢选择、刷新保留、邮件禁用且整列不勾选、开邮件后恢复保存的选择（审查 Q1）、Account 链接、390px 等宽、新文字 ≥12px |
| N2 通知渠道 | `backend/booking/domain.py` `Notification/NotificationPreference`；`services/notifications.py` `_category_channels/_notify`、偏好和读通知函数；`notification_channels.py`；`serializers.py`；`views/notifications.py` | `test_119.py` `Acceptance119` 的 channels / partial_preferences；`test_notification_preferences.py` 同步新契约；HTTP `API119Tests` |
| A1 / A3 / A4 公告及权限 | 新 `services/announcements.py`；新 `views/announcements.py`；`services/__init__.py`、`views/__init__.py`、`urls.py`；`domain.py` `Announcement`；`repository.py`、`postgres.py` | `Acceptance119` 的 expiry_order_history、ownership_matrix、removal_time_must_be_in_the_future（审查 R1）；HTTP 学生写 403、禁止伪造 kind、跨作者 Admin / Manager 权限 |
| A2 状态公告 | `services/resources.py` `set_resource_status`；`AnnouncementsMixin._status_announcement`；`serializers.py` `ResourceStatusSerializer`；`views/admin.py` | Memory / PG 共用 status_upsert（同状态改原因、维修→关闭、重开、房间及设备、恢复估计不过期）；status_and_announcement_roll_back_together |
| 数据库 | `backend/database/schema.sql`；新 `migrations/009_announcements_notification_channels.sql`；`repository.py` Memory 事务快照；`postgres.py` 公告读写 | `test_postgres.py` 新 `Postgres119Tests` 共用六项服务验收，加旧偏好升级／009 连跑两遍；`check-local.sh schema` 比较新旧库 |
| 前端公告 | 新 `features/announcements/AnnouncementBoard.tsx`、`AnnouncementsPage.tsx`、`dates.ts`；`dashboard/DashboardPage.tsx`、`admin/TodayPage.tsx`；新 `manager/ResourceStatusDialog.tsx`；`manager/ManagerBookingsPage.tsx`；API / types / routes / workspace 样式同上 | `routing.spec.ts` 公告发布、修改、下架失败弹窗、首页署名、学生权限、空公告无区域、390px；状态弹窗错误和输入保留；新 `announcement-dates.test.mjs` 夏令时及无效日期 |
| D1 文档 | `openapi.json` 1.19.0（72 路由）；`frontend-api.md`；`database/README.md`；CHANGELOG；本节；ARCHITECTURE 第 10 节；`frontend/README.md`、`PROJECT_GUIDE.md` 使用说明 | OpenAPI 校验及路由覆盖；任务卡记录完整检查的实际结果行 |

实现前的失败日志和完整检查结果放在项目外 `9900/output/1.19.0-checks/`；最终验收和截图索引见 `claude/tasks-1.19.0.md` 及本轮交付报告。通知邮件的实际外部送达、线上 EC2 页面未在本轮验证。

## 25. 结构整理 S1 + S3（2026-10-27，接口仍为 1.19.0）

只搬移和删除，不改行为。报告：项目文档 `reports/2026-10-27-code-structure-review.md` 4.3、4.4 节。

| 项 | 内容 | 证据 |
| --- | --- | --- |
| S1 | 删 31 个没用过的 CSS 类名：booking.css 21、workspace.css 8、shell.css 3、auth.css 2（审查清单里的 `ttf` 是字体扩展名，不是类名） | 每个类名在 src/tests 里搜不到（任务卡）；删除前后的 CSS 用 PostCSS 逐条比对：被删的选择器都含清单里的类，留下的规则声明一条没变（审查报告）；`check-local.sh` 全通过；截图比对见下 |
| S3 | `features/booking/api.ts`、`types.ts` → `src/api/`：函数 7 个领域文件 + `client.ts`，类型 8 个文件，`index.ts` 统一导出；旧文件删除，不留转发 | 对照表（任务卡）；用 TypeScript 语法树逐条比对 128 条顶层语句：126 条一字不差，`post` 只多了 `export`，`ApiError` 的转发只改了相对路径；说明注释全部在原来的声明上方（审查修复 R1）；`grep "features/booking/(api\|types)"` 无结果；`check-local.sh` 全通过；截图比对：44 张改动后的截图都能和 `8ae931f` 的某一次截图逐像素相同（审查修复 R2） |
| 文档 | `ARCHITECTURE.md` 第 7 节、`frontend/README.md` 的路径说明 | review |

## 26. 页面流畅度 B 卡（2026-10-27，接口仍为 1.19.0）

只改前端，任务卡：项目文档 `claude/tasks-fluency-2026-10-27.md`；不做卡 A 维修链路。

| 项 | 文件和行为 | 验证 |
| --- | --- | --- |
| V2 | `frontend/src/features/booking/BookingApp.tsx`、`ui/workspace.css`：人数和设备房间筛选独立于标签区 | `tests/fluency.spec.ts` V2（320/390/1440px，完整标签、仅 tab、设备筛选、无水平溢出） |
| V4 | `features/records/BookingRecordsPage.tsx`、`ui/workspace.css`：保留结果及对应筛选；更新中变淡/aria-busy/禁用输出；失败恢复，CSV 使用可见结果的筛选 | 同文件 V4（延迟、成功、失败、旧结果导出查询） |
| V5 | 新 `features/announcements/use-announcements.ts`；`AnnouncementBoard.tsx` 改为接收状态；`dashboard/DashboardPage.tsx`、`admin/TodayPage.tsx` 协调首页首次显示 | 同文件 V5（三角色、公告延迟1.6秒、首帧位移0、失败/重试/空公告、首页数据晚到、刷新时公告不收起） |
| V6 | `features/manager/ManagerBookingsPage.tsx`：仅首次加载错误显示与文字重试 | 同文件 V6（错误后无 Loading，重试恢复）；现有 routing 用例验证其他页面 |
| V8 | `ui/workspace.css`：移除整页入场，不影响状态动效 | 同文件 V8（计算样式无入场、reduced-motion 仍有效） |

红灯日志、前后截图和全套检查结果：项目外 `9900/output/fluency-2026-10-27/`，索引与验收状态见任务卡。

## 27. 维修链路 A 卡（2026-10-28，接口仍为 1.19.0）

只改前端，任务卡：项目文档 `claude/tasks-maintenance-2026-10-27.md`。

| 项 | 文件和行为 | 验证 |
| --- | --- | --- |
| M1① | `frontend/src/api/admin.ts` `listUnfinishedBookings(since)`（替换 `listApprovedBookings`）；`features/manager/ManagerBookingsPage.tsx` 只请求还没结束的预约和申请 | `tests/maintenance.spec.ts` M1（请求的四个状态和 `since`） |
| B1 | `ManagerBookingsPage.tsx` 的预约表和 Upcoming 列只用已批准的（`confirmed`）；`manager/ResourceStatusDialog.tsx` 显示预约加申请的合计 | 同文件 B1（弹窗 3 条含待审批、候补；表格只有已批准的） |
| V3 | `ResourceStatusDialog.tsx` `onSaved(resource)` 交出接口返回的房间；`ManagerBookingsPage.tsx` 立即更新这一行，刷新中状态按钮禁用 | 同文件 V3（刷新延迟时这一行已是 Maintenance，Reopen 禁用；刷新后恢复） |

## 28. Booking 筛选、个人历史与首页（2026-10-28，1.20.0，迁移 010）

| 项 | 文件与入口 | 验证 |
| --- | --- | --- |
| F1 | `features/booking/MyBookings.tsx`、`ui/workspace.css`：资源／状态交集与 URL、数量、Clear filters | `tests/routing.spec.ts` booking history resource（三角色、刷新、空结果与手机） |
| H1 后端 | `services/bookings.py` `remove_booking_history`；`views/bookings.py` `BookingHistoryRemoveView`、`my_bookings`；`urls.py`；`repository.py` / `postgres.py` 的 `hide_booking`、`hidden_booking_ids`；迁移 010 / schema.sql | `test_booking_history.py`：权限、状态、幂等、代约双方、回滚、原记录／缺席／日历保留、API 与 Dashboard；`test_postgres.py` 持久化与迁移连跑两遍 |
| H1 前端 | `api/bookings.ts` `removeBookingHistory`；`MyBookings.tsx`、`SeriesCard.tsx`；`my-bookings.ts` `canRemoveBookingHistory` | routing booking history removal（三角色、取消确认、503 保留、成功与刷新）、逐日期移除 |
| D1 | `DashboardPage.tsx`、`dashboard.css`、`workspace.css`：独立统计卡、紧凑 Next session 与预约列表、员工 Today 横幅 | routing booking dashboard（真实列表形状、桌面与320/390px）；既有 fluency 用例回归公告 |
| 文档 | OpenAPI 1.20.0 / frontend-api.md、数据库 README、ARCHITECTURE 第10节、CHANGELOG | check-local 的 openapi 和 schema；具体输出见任务卡 |

## 29. 压力测试（2026-10-29）

脚本和结果都在 [load-test/README.md](load-test/README.md)。性能修复的代码改动见 CHANGELOG 的压力测试三轮。

## 30. 客户 Week 8 会议（2026-11-06，1.24.0，无迁移）

任务卡：项目文档 `claude/tasks-week8-2026-11-06.md`。

| 项 | 文件和入口 | 测试 |
| --- | --- | --- |
| W1 Manager 越过规则 | `services/bookings.py` `_create_manager_booking`（`create_booking` 调用）、`reschedule_booking`；`services/availability.py` `_availability`、`day_overview` 的 `manager_override`；前端 `BookingForm.tsx`、`SlotPicker.tsx`、`slot-picker.ts` `dateRange`、`ManagerBookingsPage.tsx` 说明文字 | `test_approval_flow.py` `test_a_manager_booking_overrides_the_rules_but_needs_free_time`；`test_staff_booking.py` `test_a_manager_sees_times_inside_the_window_and_the_full_length`；`test_booking_window.py`、`test_sprint3.py` 改期用例 |
| W2 延长进行中的预约 | `services/changes.py` `extend_booking`；`checks.py` `_period_violation`（参数 `started`）；`views/bookings.py` `BookingExtendView`；`urls.py`；`serializers.py` `BookingExtendSerializer`；前端 `api/bookings.ts` `extendBooking`、`features/booking/extend.ts`、`ExtendBox.tsx`、`MyBookings.tsx`、`ManagerBookingsPage.tsx` | `test_change_requests.py` `ExtendBookingTests`、`test_extend_a_booking_in_progress`；`frontend/tests/extend.test.mjs` |
| W3 冻结默认关闭 | `rules.py` `freeze_after_no_shows=0`；`config/settings.py`；`.env.example`；`services/attendance.py` `_process_attendance` | `test_sprint3.py` `test_freeze_is_off_by_default`；原冻结用例改为显式打开 |
