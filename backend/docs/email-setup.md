# Email Notifications (Sprint 3)

The system uses a Gmail system mailbox (SMTP + app password) to email the person a booking is for. The notification and final email content are written to PostgreSQL in the same business transaction. After the request finishes, `booking/email_channel.py` sends the message; the scheduler retries failures later. SMTP network calls are outside the database transaction, so they do not hold booking locks or change booking outcomes.

## Emails sent

The recipient is the university email address of the person the booking is for. When staff book on behalf of somebody else, the beneficiary receives the email.

| Event | Notification kind | Example subject |
| --- | --- | --- |
| A user submits their own request | `BOOKING_SUBMITTED` | SmartLab: Request received – Lab Room 1, Mon 2 Nov 2026, 14:00–15:30 |
| Staff book on behalf of a user | `BOOKING_CREATED_FOR_YOU` | SmartLab: Booking made for you – … |
| Staff create a recurring booking for themselves or somebody else | `SERIES_CREATED` / `SERIES_CREATED_FOR_YOU` | SmartLab: Weekly booking confirmed |
| A request is approved or rejected, including an automatic decision | `BOOKING_APPROVED` / `BOOKING_REJECTED` | SmartLab: Booking approved – … |
| A waitlisted or pending request expires | `BOOKING_EXPIRED` | SmartLab: Request expired – … |
| A waitlisted request moves to pending review | `BOOKING_PROMOTED` | SmartLab: Your waitlisted request moved up – … |
| A Manager reschedules a booking | `BOOKING_RESCHEDULED` | SmartLab: Booking moved by a Manager – … |
| Staff cancel a booking | `BOOKING_CANCELLED` | SmartLab: Booking cancelled by staff – … |
| 24 hours before a booking starts | `BOOKING_REMINDER` | SmartLab: Booking coming up – … |
| An induction is about to expire | `INDUCTION_EXPIRING` | SmartLab: Induction expires soon |
| A student's change request is received, approved or rejected (1.16.0) | `CHANGE_REQUESTED` / `CHANGE_APPROVED` / `CHANGE_REJECTED` | SmartLab: Booking moved – … |
| A resource enters maintenance, closes or reopens (1.16.0) | `RESOURCE_OUT_OF_SERVICE` / `RESOURCE_REOPENED` | SmartLab: Lab Room 1 is under maintenance – … |

The body is plain text: a greeting, notification content, a website link such as `SITE_URL` + `/#/bookings`, and an automatic-email/do-not-reply notice. Set the comma-separated `EMAIL_NOTIFICATION_KINDS` to change which notification kinds send email.

## Who actually receives email: `EMAIL_MODE`

Demo zIDs might belong to real students, so by default no email is sent to an address outside the allowlist.

| Value | Effect |
| --- | --- |
| `none` | Send nothing |
| `allowlist` (default) | Send only to addresses in `EMAIL_ALLOWED_RECIPIENTS`; skip all others |
| `redirect` | Redirect every message to `EMAIL_REDIRECT_TO` and identify the original recipient in the body. **Use this for demonstrations** so every user's email reaches your own mailbox |
| `all` | Send to every user's university email address; use only in production |

## First-time setup (Loy's computer, PowerShell)

1. Create a Gmail account for the system mailbox and enable two-step verification.
2. Open <https://myaccount.google.com/apppasswords>, create an app password named SmartLab and copy the 16 letters. **Never send this password through chat or put it in documentation or code.**
3. Set it in the terminal that runs the backend from the `backend` directory. Run the password line **separately**; the input is hidden:

```powershell
$env:EMAIL_HOST_USER = "your-system-mailbox@gmail.com"
$sec = Read-Host "Gmail app password" -AsSecureString
$env:EMAIL_HOST_PASSWORD = [System.Net.NetworkCredential]::new("", $sec).Password
$env:EMAIL_HOST_PASSWORD.Length   # Should display 16, or 19 with spaces; the program removes spaces
```

4. Send a test email to yourself:

```powershell
.\.venv\Scripts\python.exe manage.py send_test_email --to your-email-address
```

Success displays `Sent to …`. A failure displays Gmail's original response, commonly `535 … Username and Password not accepted` when the password is wrong or two-step verification is disabled. The command prints only `password set` or `NOT set`, never the password.

5. Enable email notifications in demonstration mode, redirecting all email to yourself, and then start the backend:

```powershell
$env:EMAIL_ENABLED = "true"
$env:EMAIL_MODE = "redirect"
$env:EMAIL_REDIRECT_TO = "your-email-address"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

6. Submit a request as z1000001. The mailbox should receive "Request received". Approve it as an Admin and confirm that "Booking approved" arrives.

These environment variables apply only to the current terminal. Closing it clears them, so they, including the password, must be set again next time.

## Other settings

| Environment variable | Default | Description |
| --- | --- | --- |
| `EMAIL_ENABLED` | `false` | When `true`, add the email channel to `NOTIFICATION_CHANNELS` |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_USE_TLS` | `smtp.gmail.com` / `587` / `true` | Change these three values when using the university mail server |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Empty | System mailbox and app password |
| `DEFAULT_FROM_EMAIL` | `SmartLab <EMAIL_HOST_USER>` | Displayed sender name |
| `EMAIL_TIMEOUT` | `10` | Timeout in seconds for connecting, signing in and sending |
| `EMAIL_MAX_ATTEMPTS` | `6` | Maximum attempts per message; after this it remains `FAILED` and is no longer sent automatically |
| `EMAIL_LEASE_SECONDS` | `300` | Lease after a worker claims a task; after a crashed process's lease expires, another worker can take over |
| `EMAIL_BATCH_SIZE` | `50` | Maximum due messages claimed in one pass by the API background thread |
| `LOG_LEVEL` | `INFO` | Log level for backend `booking` messages; at `INFO`, each sent or skipped email writes one line, as described under Logs below |
| `EMAIL_MODE`, `EMAIL_ALLOWED_RECIPIENTS`, `EMAIL_REDIRECT_TO` | `allowlist`, empty, empty | See the previous section |
| `EMAIL_NOTIFICATION_KINDS` | All kinds in the table above | Notification kinds that send email |
| `SITE_URL` | `http://localhost:5173` | Website link included in email |

## Delivery and inspection (since 27 October 2026)

- When a notification is generated, the final recipient address, subject and body are committed with it as an `email_delivery` record. The SMTP password exists only in an environment variable.
- At the end of a request, an API background thread immediately claims and sends due records in batches; the web page does not wait for Gmail. The independent scheduler continues to process remaining records and due retries every minute.
- A batch reuses one SMTP connection. Database leases allow multiple workers to claim tasks without duplicate delivery during normal concurrency. If a worker crashes, another can take over after the lease expires.
- Temporary failures retry after approximately 1, 5, 15 and 60 minutes, followed by 60-minute intervals. After `EMAIL_MAX_ATTEMPTS`, the message becomes `FAILED`. The booking and in-app notification are unaffected.
- Logs are available through `docker compose --env-file .env.docker logs api`, or in the terminal running the local backend. Each batch and message produces one line:

  ```
  INFO booking.email_channel: Mail server connection opened in 1907 ms for 2 durable email(s)
  INFO booking.email_channel: Email sent for notification <notification-id> to @ad.unsw.edu.au: waited 2125 ms, sent in 360 ms
  ```

  `waited` measures the time from entering the queue until sending begins, including connection and authentication. `sent in` measures the message transmission itself. Logs record only the recipient's domain. Failures produce an `ERROR` line with the cause.
- If an email arrives slowly, check this line first. The application normally hands the message to Gmail within two or three seconds. An email investigated on 27 October 2026 arrived about four minutes late; almost all of that time was spent on the UNSW side, with about 2 minutes 30 seconds in Proofpoint scanning and about 1 minute 20 seconds in Microsoft 365 delivery. The application cannot reduce that delay.
- `manage.py process_due --email-limit 50` processes due email; the Docker `scheduler` calls it continuously.

## Reliability boundaries

- In PostgreSQL mode, pending tasks and failure reasons persist, and processing continues after an API or scheduler restart. The in-memory repository is only for local tests and does not persist across processes.
- SMTP has no idempotency key. In an extreme case, the server may accept a message before the worker crashes while writing `SENT`; the task may be sent again after its lease is recovered. The system prevents silent loss and minimises duplicates, but does not claim strict exactly-once delivery.
- Configuration errors or permanent rejection remain `FAILED` after the maximum attempts. They require manual action after the configuration is fixed and are not retried forever.
- Outlook mail is not used because Outlook.com stopped accepting password-based SMTP sign-in in September 2024 and requires Microsoft authorisation through Graph `Mail.Send`; its token expires. For production handover, the university can replace `EMAIL_HOST` and related settings with its own mail server without changing the code.
