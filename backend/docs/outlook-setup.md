# Outlook 日历同步：配置与实测

同步是单向的（网站 → Outlook），而且真实接入了 Outlook、可以实测。网站是预约规则和资格的唯一依据，Outlook 里的改动不能绕过系统规则，也不能变成网站上已批准的预约。

## 1. 同步做什么

**单向写入（网站 → Outlook）**
- 预约批准后，在 Outlook 日历里创建事件。
- Manager 改期时，更新同一个事件。
- 预约取消时，删除这个事件。
- 待审批、候补、被拒、过期的申请都不写日历。
- 人工批准、超时自动批准、候补递补后批准、紧急申请由 Manager 批准，这几种情况走的是同一套流程。

**以网站为准**
- 系统运行时从不读取 Outlook 里的修改，所以在 Outlook 里做什么都影响不到预约，也不可能变成网站上的预约。
- 每个人管自己的日历：把事件删掉或改掉，系统不会自动改回来。
- 只有网站上的操作会再次写日历。例如 Manager 改期时，如果发现事件已经被删除，就按新时间重新建一个（审计记录为 `OUTLOOK_EVENT_RECREATED`）。

**事件写在哪里、邀请谁**
- 事件写在授权账号的日历里。个人演示用的就是你自己的 Outlook 账号，暂时代表"预约人的日历"。
- 代别人预约时，受邀人是**预约的受益人**（`student_id`）。代订的员工名字写在事件正文里（"Booked by … (on behalf)"），员工本人不会收到邀请。
- 事件正文不包含内部 ID、预约用途或 induction 资料。
- 正式环境要写进每个人自己的日历，需要学校 Microsoft 365 授权（见第 8 节）。

## 2. 测试只用自己的邮箱（必须先看）

事件带受邀人时，Outlook 会**真的发出会议邀请**。演示账号的邮箱是 `z1000001@ad.unsw.edu.au` 这种真实格式，邀请可能会发给真实的人。所以默认设置是：

- `OUTLOOK_INVITE_MODE=allowlist`：只邀请 `OUTLOOK_ALLOWED_ATTENDEES`（多个地址用逗号分隔）里列出的地址。不在名单里的人照样会创建事件，只是不加受邀人；名单为空就谁都不邀请。这是一个环境变量开关，不需要另建数据表。
- 想在收件箱里看到邀请：先注册一个演示学生，邮箱填你的另一个地址（不要填登录 Outlook 的那个，Outlook 不会给组织者本人发邀请），再把这个地址填进名单。
- `none`：永远不邀请。`all`：邀请所有受益人，只在客户确认的正式环境里使用。

系统本身不发邮件。批准、拒绝这类通知还没有实现，要等客户答复通知方式。

## 3. 让后端能写你的日历

授权只需要 `Calendars.ReadWrite`，而且只针对**你自己的日历**。凭证只保存在后端的 `.local/` 目录里（已被 Git 忽略），不要贴到聊天、文档或源码里。

### 方式 A：Graph Explorer Token（本项目实际使用的方式）

1. 打开**无痕窗口**，进入 [Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer)，用你的**个人**微软账号登录（右上角 Tenant 应显示 Personal）。UNSW 账号会被学校拦截。
2. 点 **Modify permissions**，确认 `Calendars.ReadWrite` 已经 **Consent**。
3. 在 **Access token** 标签复制 Token，然后运行 `manage.py outlook_token`，在不显示内容的提示处粘贴，按回车。

Token 大约 1 小时过期。过期后同步会显示 `GRAPH_HTTP_401`（Calendar Sync 页面显示 "Microsoft sign-in expired"）。重新复制、粘贴一次，再点 Retry 或等它自动重试，不用重启服务器。

### 方式 B：一次登录，自动续期（需要 Azure 应用注册）

只有在你能注册 Azure 应用时才用（UNSW 账号不行，个人账号可能被要求开 Azure 订阅）：

1. 在 Microsoft Entra 的 App registrations 新建一个应用，账户类型选"任何组织目录和个人 Microsoft 帐户"。
2. 在 Authentication 里把 **Allow public client flows** 设为 Yes。
3. 在 API permissions 里添加 Microsoft Graph 的委托权限 `Calendars.ReadWrite` 和 `offline_access`。
4. 把 Application (client) ID 设为 `OUTLOOK_PUBLIC_CLIENT_ID`，然后运行 `manage.py outlook_login`。按提示打开网址、输入短码，用自己的账号登录。

之后后端会自动续期（refresh token 存在 `.local/outlook-refresh-token`）。如果出现 `OUTLOOK_LOGIN_EXPIRED`，重新运行 `outlook_login` 即可。两种方式都配置时，方式 B 优先。

## 4. 配置并启动（PowerShell，在 `backend` 目录）

第一次使用时先建环境：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-postgres.txt
```

每次新开窗口都要重新设置变量，项目不会自动读取 `.env`：

```powershell
$env:DEBUG = 'true'
$env:ENABLE_DEMO_AUTH = 'true'
$env:DJANGO_SECRET_KEY = 'local-demo-only-change-this-key'
$env:OUTLOOK_ENABLED = 'true'
$env:OUTLOOK_INVITE_MODE = 'allowlist'
$env:OUTLOOK_ALLOWED_ATTENDEES = ''
.\.venv\Scripts\python.exe manage.py outlook_token
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

如果用 PostgreSQL，`runserver` 前还要按 [database/README.md](../database/README.md) 第 3 节设置数据库变量（密码用 `Read-Host` 输入）。如果没用，就清掉这些变量，否则会报 `no password supplied`。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `OUTLOOK_ENABLED` | `false` | 总开关 |
| `OUTLOOK_INVITE_MODE` | `allowlist` | `none`／`allowlist`／`all`，见第 2 节 |
| `OUTLOOK_ALLOWED_ATTENDEES` | 空 | `allowlist` 模式下允许邀请的地址，用逗号分隔 |
| `OUTLOOK_TOKEN_FILE` | `.local/outlook-token`（DEBUG 时） | 方式 A 保存的 Token |
| `OUTLOOK_PUBLIC_CLIENT_ID` | 空 | 方式 B 的 Application (client) ID |
| `OUTLOOK_AUTHORITY` | `common` | 方式 B 的登录端点；只用个人账号时也可以填 `consumers` |
| `OUTLOOK_REFRESH_TOKEN_FILE` | `.local/outlook-refresh-token`（DEBUG 时） | 方式 B 的 refresh token 文件 |

## 5. 真实实测

### 5.1 自动实测命令

```powershell
.\.venv\Scripts\python.exe manage.py outlook_live_check
```

这个命令照着系统的真实做法，在你的日历里操作一个**不带受邀人**的临时事件，每一步打印 PASS 或 FAIL：
1. 连接并读取日历
2. 创建事件
3. 读回确认，内容和预约一致
4. 像改期一样移动同一个事件
5. 像取消一样删除事件，并确认已删除

全部通过时显示 `All live Outlook checks passed.`。中途失败也会删掉临时事件，命令不会打印 Token。

### 5.2 端到端手工清单（演示、截图用）

1. **检查连接**：前端用 Staff sign-in 登录 z9000001（演示密码 `123`），打开 Calendar Sync，点 Check connection，应该显示 Connected 和你的邮箱。
2. **批准后写入**：用 z1000001 申请一个 7～30 天后的 Lab Room 1 时段，Admin 批准。Outlook 里出现 `SmartLab booking: Lab Room 1`，Calendar Sync 中这一行显示 Synced。
3. **在 Outlook 里改或删**：在 Outlook 里拖动或删除这个事件。网站上的预约不受影响，系统也不会把事件改回去。
4. **改期**：Manager（z9000002）给这个预约改期。Outlook 事件移到新时间；如果第 3 步已经删了，就按新时间重新建一个。
5. **取消**：取消预约后，Outlook 里的事件被删除，这一行显示 Removed (cancelled)。
6. **代预约**：Manager 代 z1000001 预约，由 Admin 批准。事件正文写着 "Booked by Demo manager (on behalf)"。只有 z1000001 的邮箱在名单里时，才会真的发邀请。

## 6. 定时处理

使用 PostgreSQL 时，可以用 Windows 任务计划每几分钟运行一次 `manage.py process_due`。它会处理到期的审批申请，并推送等待中的 Outlook 更新（`--outlook-limit`，默认 10）。只处理 Outlook 时用 `manage.py process_outlook --limit 10`。内存模式下这两个命令会拒绝运行，请改用页面上的 Sync now 或 `POST admin/outlook/process/`。

## 7. 状态与失败重试

- 预约的 `status` 和日历的 `outlook_sync.status` 互相独立：日历同步失败时，预约仍然有效。
- 失败后自动退避重试（从 30 秒开始，最长 1 小时，并遵守微软返回的 Retry-After）。
- **Calendar Sync 页面**（`/admin/calendar-sync`，Admin／Manager）是开发阶段的可视化页面，正式交付前可以删掉（见下）。它显示连接状态、同步统计（已同步／等待／失败），失败的预约排在最前，可以点 Retry；还有 Check connection 和 Sync now 按钮。

| 方法 | 路径（前缀 `/api/v1/`） | 用途 |
| --- | --- | --- |
| GET | `admin/outlook/` | 配置、统计和每个预约的同步状态（不调用微软） |
| POST | `admin/outlook/check/` | 读一次日历，测试登录和权限；body `{}` |
| POST | `admin/outlook/process/` | 处理等待中的更新；body `{"limit":1}`，最多 5 |
| POST | `admin/bookings/{id}/outlook-retry/` | 立即重试；body `{}` |

| 错误码 | 含义和处理 |
| --- | --- |
| `TOKEN_EXPIRED`／`GRAPH_HTTP_401` | Token 过期：重新粘贴 Token（方式 A）或运行 `outlook_login`（方式 B），然后点 Retry |
| `OUTLOOK_LOGIN_EXPIRED` | 方式 B 的登录失效：重新运行 `outlook_login` |
| `OUTLOOK_NOT_CONFIGURED` | 还没保存 Token，也没有完成登录 |
| `GRAPH_HTTP_403`／`OUTLOOK_CALENDAR_READ_ONLY` | 没有授予日历读写权限，或者目标日历只读 |
| `GRAPH_HTTP_404` | 目标日历不存在（改期时发现事件已被删除，不算错误，会直接重建） |
| `GRAPH_HTTP_429` | 微软限流，会按 Retry-After 自动重试 |
| `GRAPH_NETWORK_ERROR` | 网络不通或超时，恢复后自动重试 |
| `STUDENT_EMAIL_NOT_CONFIGURED` | 预约人没有大学邮箱 |

**删除 Calendar Sync 页面时**，前端去掉以下内容即可，后端接口可以保留：
- `src/features/admin/CalendarSyncPage.tsx`、`src/features/admin/calendar-sync.ts`
- `app/routes.ts`、`app/AppRouter.tsx`、`app/AppLayout.tsx` 里各一行
- 对应的测试

## 8. 正式环境交接（Microsoft 365）

正式服务可以配置 `OUTLOOK_TENANT_ID`、`OUTLOOK_CLIENT_ID`、`OUTLOOK_CLIENT_SECRET`、`OUTLOOK_MAILBOX`，以应用身份写日历。这需要应用的 `Calendars.ReadWrite` 权限、管理员同意，并配置可以访问的邮箱范围；同时要清掉个人 Token 和登录文件。

要直接写进每个人自己的日历，也需要学校 IT 授权，客户正在联系相关人员；学生的 SSO 登录不能替代这一步。正式环境可以把 `OUTLOOK_INVITE_MODE` 设为 `all`。

数据库表 `outlook_sync_record` 保存事件 ID、iCal UID、目标路径、版本号、重试时间和租约。预约、同步记录、审计在同一个事务里保存；调用微软的网络请求放在事务之外，完成后重新读取版本再写回。

微软文档：[创建事件](https://learn.microsoft.com/en-us/graph/api/calendar-post-events?view=graph-rest-1.0)、[更新事件](https://learn.microsoft.com/en-us/graph/api/event-update?view=graph-rest-1.0)、[删除事件](https://learn.microsoft.com/en-us/graph/api/event-delete?view=graph-rest-1.0)、[设备代码登录](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code)、[权限](https://learn.microsoft.com/en-us/graph/permissions-reference#calendarsreadwrite)。
