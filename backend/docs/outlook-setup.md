# Sprint 1：个人 Outlook 日历演示

本版把已批准预约写入授权 Outlook 账号的日历，并邀请学生邮箱；改期时更新原事件，取消时删除事件。授权账号是组织者，学生邮箱作为 `required` attendee。房间和设备的可用性、资格要求与冲突由本系统管理。这是“系统 → Outlook”的单向日历同步，不是独立邮件通知，也不是学校 SSO。学生仍用本地演示登录。等待名单和重复预约留到 Sprint 2。

微软凭证只在本机配置，不要发到聊天或提交 GitLab。默认不启用同步。

## 1. 在微软授权自己的账号

打开 [Microsoft Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer)，使用自己的 Outlook 账号 Sign in。未登录的微软样例数据不代表真实账号。

1. 选择 GET，地址为 `https://graph.microsoft.com/v1.0/me/calendar`，确认能读取自己的日历。
2. 在 **Modify permissions** 找到 `Calendars.ReadWrite`，点击 **Consent**。组织账号可能需要管理员处理；个人账号通常能自行授权。
3. 打开 **Access token** 标签页，复制当前 Microsoft Graph access token。

这不是 GitLab Token，也不是后端演示 Token。操作说明见 [微软文档](https://learn.microsoft.com/en-us/graph/graph-explorer/graph-explorer-overview)。

## 2. 配置并启动

在 Windows **命令提示符（CMD）**执行。已建立 `.venv` 的同学可以跳过建立环境和安装依赖两步：

```bat
cd /d "C:\Users\loy\Desktop\9900\team-repo\backend"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
set DEBUG=true
set ENABLE_DEMO_AUTH=true
set DJANGO_SECRET_KEY=local-demo-only-change-this-key
set OUTLOOK_ENABLED=true
.\.venv\Scripts\python.exe manage.py outlook_token
```

在 `Paste the Graph access token (hidden)` 提示处粘贴一次 Token，按 Enter。不会显示文字或星号。`Local token saved` 表示本地保存完成；有效期和权限由微软在同步时检查。

该命令只在 DEBUG 本地演示可用，凭证写入当前后端的 `.local/outlook-token`，此目录已被 Git 忽略。API 和审计不会返回凭证。

然后启动后端：

```bat
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

PowerShell 用 `$env:DEBUG="true"`、`$env:ENABLE_DEMO_AUTH="true"`、`$env:DJANGO_SECRET_KEY="local-demo-only-change-this-key"`、`$env:OUTLOOK_ENABLED="true"` 设置变量，其余 Python 命令相同。项目不会自动读取 `.env`。

## 3. 验证

通过前端或 `demo.http`：

1. 用已具备 induction 资格的 `z1000001` 登录。
2. 创建未来可用时段的房间或设备预约。
3. `status=APPROVED` 表示预约批准；`outlook_sync.status=SYNCED` 表示 Graph 确认事件创建。
4. 打开 Outlook Calendar 的预约日期，查看 `SmartLab booking: <资源名称>`，或打开 `outlook_sync.web_link`。
5. 在本系统把预约改到另一个可用时间；确认 `action=UPDATE`、`status=SYNCED`，原事件 ID 保持不变且时间已更新。
6. 在本系统取消该预约；确认 `action=DELETE`、`status=SYNCED`，日历中该事件应被删除。

人工批准、induction 审核后自动批准也走同一流程。未批准申请不会创建事件。事件包含学生大学邮箱、预约资源名称、地点和预约引用，不包含内部 student ID、学生证件、induction 附件或预约用途。演示种子里的 `example.edu` 学生邮箱只是占位值；真实联调前必须换成实际邮箱。

取消演示预约后再停止服务器。当前数据在内存，重启会丢失预约和事件 ID，但 Outlook 事件仍存在；提前重启后需要在自己的 Outlook 删除遗留演示事件。共享运行前由数据库同学接入持久化。

## 4. 失败与重试

同步失败时，预约仍批准并占用系统时段。前端单独显示“日历同步失败”。Admin／Manager 可调用：

| 方法 | 路径（前缀 `/api/v1/`） | 用途 |
| --- | --- | --- |
| GET | `admin/outlook/` | 启用状态、本地配置是否存在、同步记录 |
| POST | `admin/outlook/process/` | 处理到期任务；body 为 `{"limit":1}`，最多 5 条 |
| POST | `admin/bookings/{id}/outlook-retry/` | 修复配置后立即重试；body 为 `{}` |

`configured=true` 只表示本地配置存在，`SYNCED` 才表示微软操作完成。默认预约操作后自动尝试一次；失败任务保留并退避，GET dashboard 不触发网络请求。

| last_error | 检查事项 |
| --- | --- |
| `OUTLOOK_NOT_CONFIGURED` | 尚未保存 Token 或未提供应用配置 |
| `STUDENT_EMAIL_NOT_CONFIGURED` | 用户资料没有大学邮箱；补全可信 SSO／用户映射 |
| `OUTLOOK_EVENT_ID_MISSING` | 更新任务缺少已创建事件的 ID；检查持久化／迁移数据 |
| `GRAPH_HTTP_401` | Token 过期／无效；重新获取并运行 `outlook_token`，再重试 |
| `GRAPH_HTTP_403` | 未授予日历读写权限，或没有目标日历权限 |
| `GRAPH_HTTP_404` | 目标邮箱／日历不存在；删除已消失事件视为成功 |
| `GRAPH_HTTP_429` | 微软限流；按 Retry-After 和退避规则重试 |
| `GRAPH_NETWORK_ERROR` | 网络不可达／超时；恢复后重试 |

更新 Token 不用重启服务器：第二个终端进入相同目录，设置 `DEBUG=true`，运行 `outlook_token`，再调用管理员重试。临时 Token 不会自动续期。

## Microsoft 365 与数据库交接

正式服务可配置 `OUTLOOK_TENANT_ID`、`OUTLOOK_CLIENT_ID`、`OUTLOOK_CLIENT_SECRET`、`OUTLOOK_MAILBOX`，使用应用身份自动获取新 access token；清除个人 Token，并将 `OUTLOOK_TOKEN_FILE` 设置为空。需要应用 `Calendars.ReadWrite` 权限、管理员同意及目标邮箱访问范围配置。客户／学校须确认授权，学生 SSO 登录不能替代。

数据库新增 `get_outlook_sync`、`list_outlook_sync`、`save_outlook_sync`，保存 `OutlookSyncRecord` 全部字段，包括事件 ID、iCal UID、目标路径、预约版本、同步版本、最后成功时间、重试时间和租约。`Principal.university_email` 也必须持久化。预约、同步记录、审计在同一事务保存，处理完成时重读版本。接入持久化后可定时执行 `python manage.py process_outlook --limit 10`；内存演示只能通过运行中服务器的管理员接口处理失败。

默认在一个授权组织者日历建立事件，再邀请当前学生。房间和设备只由系统数据库管理，Outlook 事件中的资源名称和地点用于向学生说明预约内容。

微软文档：[创建事件](https://learn.microsoft.com/en-us/graph/api/calendar-post-events?view=graph-rest-1.0)、[更新事件](https://learn.microsoft.com/en-us/graph/api/event-update?view=graph-rest-1.0)、[删除事件](https://learn.microsoft.com/en-us/graph/api/event-delete?view=graph-rest-1.0)、[权限](https://learn.microsoft.com/en-us/graph/permissions-reference#calendarsreadwrite)、[应用身份认证](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)。
