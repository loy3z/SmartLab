# 邮件通知（Sprint 3）

系统用一个 Gmail 系统邮箱（SMTP + 应用专用密码）给预约人发邮件。邮件和铃铛里的通知是同一条记录：先存为站内通知，请求结束后再由邮件渠道 `booking/email_channel.py` 发出去。业务代码不知道邮件的存在。

## 发哪些邮件

收件人是预约人（受益人）的大学邮箱；员工替别人预约时，发给被预约的人。

| 什么时候 | 通知类型 | 主题示例 |
| --- | --- | --- |
| 自己提交了申请 | `BOOKING_SUBMITTED` | SmartLab: Request received – Lab Room 1, Mon 2 Nov 2026, 14:00–15:30 |
| 员工替你预约 | `BOOKING_CREATED_FOR_YOU` | SmartLab: Booking made for you – … |
| 员工建了重复预约（给自己／给别人） | `SERIES_CREATED`／`SERIES_CREATED_FOR_YOU` | SmartLab: Weekly booking confirmed |
| 批准、拒绝（含系统自动决定） | `BOOKING_APPROVED`／`BOOKING_REJECTED` | SmartLab: Booking approved – … |
| 候补或待审批的申请过期 | `BOOKING_EXPIRED` | SmartLab: Request expired – … |
| 候补转为待审批 | `BOOKING_PROMOTED` | SmartLab: Your waitlisted request moved up – … |
| 被 Manager 改期 | `BOOKING_RESCHEDULED` | SmartLab: Booking moved by a Manager – … |
| 被员工取消 | `BOOKING_CANCELLED` | SmartLab: Booking cancelled by staff – … |
| 预约开始前 24 小时 | `BOOKING_REMINDER` | SmartLab: Booking coming up – … |
| induction 快到期 | `INDUCTION_EXPIRING` | SmartLab: Induction expires soon |
| 学生申请改期：收到、批准、拒绝（1.16.0） | `CHANGE_REQUESTED`／`CHANGE_APPROVED`／`CHANGE_REJECTED` | SmartLab: Booking moved – … |
| 资源进入维护或关闭、重新开放（1.16.0） | `RESOURCE_OUT_OF_SERVICE`／`RESOURCE_REOPENED` | SmartLab: Lab Room 1 is under maintenance – … |

正文是纯文本：称呼、通知内容、网站链接（`SITE_URL` + `/#/bookings` 等）和“自动邮件，请勿回复”。要改发哪些，设置 `EMAIL_NOTIFICATION_KINDS`（逗号分隔）。

## 谁真的会收到：`EMAIL_MODE`

演示数据里的 zID 可能是真实学生的，所以默认不会给任何不在名单上的人发信。

| 值 | 效果 |
| --- | --- |
| `none` | 不发 |
| `allowlist`（默认） | 只发给 `EMAIL_ALLOWED_RECIPIENTS` 里的地址，其他人跳过 |
| `redirect` | 所有邮件都改发到 `EMAIL_REDIRECT_TO`，正文注明原本发给谁。**演示时用这个**：所有人的邮件都进你自己的邮箱 |
| `all` | 发给每个人的大学邮箱（正式上线才用） |

## 第一次配置（Loy 本机，PowerShell）

1. 新建一个 Gmail 账号作为系统邮箱，开启两步验证。
2. 打开 <https://myaccount.google.com/apppasswords>，新建一个应用专用密码（名字写 SmartLab），得到 16 个字母。**这个密码不要发到聊天、文档或代码里。**
3. 在运行后端的终端（`backend` 目录）里设置。密码那一行**单独执行**，输入时不显示：

```powershell
$env:EMAIL_HOST_USER = "你的系统邮箱@gmail.com"
$sec = Read-Host "Gmail app password" -AsSecureString
$env:EMAIL_HOST_PASSWORD = [System.Net.NetworkCredential]::new("", $sec).Password
$env:EMAIL_HOST_PASSWORD.Length   # 应该显示 16（带空格是 19，也可以，程序会去掉空格）
```

4. 先发一封测试邮件给自己：

```powershell
.\.venv\Scripts\python.exe manage.py send_test_email --to 你自己的邮箱
```

成功会显示 `Sent to …`。失败会显示 Gmail 的原话，常见的是 `535 … Username and Password not accepted`（密码错，或没开两步验证）。命令只打印“password set／NOT set”，不打印密码。

5. 打开邮件通知（演示模式：全部改发给自己），再启动后端：

```powershell
$env:EMAIL_ENABLED = "true"
$env:EMAIL_MODE = "redirect"
$env:EMAIL_REDIRECT_TO = "你自己的邮箱"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

6. 用 z1000001 提交一个申请，邮箱里应该收到 “Request received”；用 Admin 批准后收到 “Booking approved”。

这些环境变量只在当前终端有效，关掉终端就没了，下次要重新设置（密码也要重新输入）。

## 其他设置

| 环境变量 | 默认 | 说明 |
| --- | --- | --- |
| `EMAIL_ENABLED` | `false` | `true` 时把邮件渠道加进 `NOTIFICATION_CHANNELS` |
| `EMAIL_HOST`／`EMAIL_PORT`／`EMAIL_USE_TLS` | `smtp.gmail.com`／`587`／`true` | 换成学校的邮件服务器时改这三个 |
| `EMAIL_HOST_USER`／`EMAIL_HOST_PASSWORD` | 空 | 系统邮箱和应用专用密码 |
| `DEFAULT_FROM_EMAIL` | `SmartLab <EMAIL_HOST_USER>` | 发件人显示名 |
| `EMAIL_TIMEOUT` | `10` | 和邮件服务器的每一步（连接、登录、发送）最多等几秒；发信在后台，不影响网页。服务器正常关闭时，最多再等这么久把队列里的邮件发完 |
| `LOG_LEVEL` | `INFO` | 后端 `booking` 日志的级别；`INFO` 时每封邮件发出、跳过都记一行（见下面「日志」） |
| `EMAIL_MODE`、`EMAIL_ALLOWED_RECIPIENTS`、`EMAIL_REDIRECT_TO` | `allowlist`、空、空 | 见上一节 |
| `EMAIL_NOTIFICATION_KINDS` | 上表所有类型 | 哪些通知发邮件 |
| `SITE_URL` | `http://localhost:5173` | 邮件里的网站链接 |

## 什么时候发出、怎么查（2026-10-27 起）

- 请求结束时，网站只把写好的邮件放进队列，马上返回；每个后端进程有一个后台线程负责发送。所以开着邮件时，提交或审批不再多等连接 Gmail 的约 2 秒。
- 后台线程把同时在排队的邮件用**同一条连接**发出（约 0.2 秒内进队列的算一批），不用每封都重新连接、登录。
- 日志（`docker compose --env-file .env.docker logs api`；本机看运行后端的终端），每批和每封各一行：

  ```
  INFO booking.email_channel: Mail server connection opened in 1907 ms for 2 email(s)
  INFO booking.email_channel: Email sent for notification <通知编号> to @ad.unsw.edu.au: waited 2125 ms, sent in 360 ms
  ```

  `waited` 是从放进队列到开始发这一封（包括连接和登录），`sent in` 是发这一封本身。日志只写收件人的域名。失败时是 `ERROR` 行，带原因。
- 邮件到得慢时，先看这一行：应用这边通常两三秒内就交给了 Gmail。2026-10-27 查过一封晚到约 4 分钟的邮件，时间几乎都花在 UNSW 那边（Proofpoint 扫描约 2 分 30 秒，Microsoft 365 投递约 1 分 20 秒），应用这边改不了。
- `manage.py process_due` 会等后台的邮件发完（最多 60 秒）才退出。

## 局限

- 后台队列在内存里：后端进程被强行杀掉（崩溃、`docker kill`、正常关闭超过等待时间）时，还没发出的邮件会丢，不会补发。铃铛里的通知不受影响。
- 发不出去（网络、密码、Gmail 每天约 500 封的上限）只记日志，不影响预约本身，也不重试。铃铛里的通知照常有。
- 为什么不用 Outlook 邮箱：Outlook.com 从 2024 年 9 月起不再接受密码登录 SMTP，要用微软授权（Graph `Mail.Send`），Token 会过期。正式交付时，学校可以把 `EMAIL_HOST` 等换成自己的邮件服务器，代码不用改。
