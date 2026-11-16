# Outlook Calendar Synchronisation: Setup and Live Testing

Synchronisation is one way, from the website to Outlook, and is a real, testable Outlook integration. The website is the sole authority for booking rules and qualifications. Changes made in Outlook cannot bypass system rules or become approved website bookings.

## 1. What synchronisation does

**One-way writes (website → Outlook)**
- Create an Outlook Calendar event after a booking is approved.
- Update the same event when a Manager reschedules the booking.
- Delete the event when the booking is cancelled.
- Do not write pending, waitlisted, rejected or expired requests to the calendar.
- Manual approval, automatic approval after the review deadline, waitlist promotion followed by approval, and Manager approval of an urgent request all use the same workflow.

**The website is authoritative**
- The running system never reads changes from Outlook, so actions in Outlook cannot affect a booking or create one on the website.
- Each user controls their own calendar. If they delete or move an event, the system does not immediately restore it.
- Only another website action writes to the calendar again. For example, if a Manager reschedules a booking after its event was deleted, the system recreates it at the new time and records `OUTLOOK_EVENT_RECREATED` in the audit.

**Event location and attendees**
- Events are written to the authorised account's calendar. In a personal demonstration, this is your own Outlook account, temporarily representing the beneficiary's calendar.
- When staff book on behalf of another person, the attendee is the **booking beneficiary** (`student_id`). The event body names the staff creator as "Booked by … (on behalf)"; that staff member is not invited.
- The body excludes the booking purpose and induction evidence. It includes only a booking reference for finding the record on the website.
- Writing directly to each person's calendar in production requires university Microsoft 365 authorisation; see Section 8.

### Alternative: calendar subscription link, with no authorisation

Every user can copy a private calendar subscription link from My Bookings and paste it into Outlook under Add calendar → Subscribe from web. Outlook periodically reads the link, which contains all approved bookings for that person. This requires no Microsoft authorisation or university IT support and therefore reaches each student's own calendar. The limitation is that Outlook controls refresh frequency, which may take several hours. This subscription and the Graph integration described here are independent and can run together; if both are enabled, one person may see two copies of an event. See "Calendar subscription link" in [frontend-api.md](frontend-api.md).

### Future notifications through Outlook

In-app notifications are stored in the database before being passed to a delivery channel. Email currently uses SMTP with PostgreSQL outbox retries driven by the scheduler. If the university later requires Graph `sendMail`, a new channel can be added without changing booking rules.

## 2. Use only your own email for testing

An Outlook event with an attendee sends a **real meeting invitation**. Demo account addresses such as `z1000001@ad.unsw.edu.au` look real and may belong to actual people. The defaults therefore are:

- `OUTLOOK_INVITE_MODE=allowlist`: invite only addresses listed in the comma-separated `OUTLOOK_ALLOWED_ATTENDEES`. An event is still created for a beneficiary outside the list, but without an attendee. An empty list invites nobody. This is an environment switch and needs no table.
- To receive an invitation, first register a demo student using another email address of your own. Do not use the address of the Outlook organiser, because Outlook does not invite an organiser to their own meeting. Then add that address to the allowlist.
- `none` never invites anyone. `all` invites every beneficiary and is only for a client-approved production environment.

The system can independently use a configured SMTP system mailbox for approval, rejection and other notifications. It is disabled by default; see `email-setup.md` for configuration and durable retries. Email notification and Outlook Calendar synchronisation are separate integrations.

## 3. Allow the backend to write to your calendar

Authorisation needs only `Calendars.ReadWrite` for **your own calendar**. Credentials are stored only under the backend `.local/` directory, which Git ignores. Never paste them into chat, documentation or source code.

### Option A: Graph Explorer token, used by this project

1. Open an **incognito window**, go to [Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer) and sign in with a **personal** Microsoft account. The Tenant in the top-right should display Personal. UNSW accounts are blocked by university policy.
2. Select **Modify permissions** and confirm that `Calendars.ReadWrite` is **Consented**.
3. Copy the token from the **Access token** tab, run `manage.py outlook_token`, paste it into the hidden prompt and press Enter.

The token expires in approximately one hour. After expiry, synchronisation shows `GRAPH_HTTP_401`, while Calendar Sync displays "Microsoft sign-in expired". Copy and paste a new token, then select Retry or wait for the automatic retry. A server restart is not required.

### Option B: sign in once and refresh automatically, requiring an Azure app registration

Use this option only if you can register an Azure application. UNSW accounts cannot; a personal account may require an Azure subscription.

1. Create an app under Microsoft Entra App registrations with account type "Accounts in any organizational directory and personal Microsoft accounts".
2. Set **Allow public client flows** to Yes under Authentication.
3. Add delegated Microsoft Graph permissions `Calendars.ReadWrite` and `offline_access` under API permissions.
4. Set the Application (client) ID as `OUTLOOK_PUBLIC_CLIENT_ID`, then run `manage.py outlook_login`. Open the displayed URL, enter the short code and sign in with your account.

The backend then refreshes access automatically. The refresh token is stored in `.local/outlook-refresh-token`. If `OUTLOOK_LOGIN_EXPIRED` appears, rerun `outlook_login`. When both options are configured, Option B takes precedence.

## 4. Configure and start (PowerShell, from `backend`)

Create the environment on first use:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-postgres.txt
```

Set the variables again in every new terminal; the project does not load `.env` automatically:

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

For PostgreSQL, also set the database variables described in Section 3 of [database/README.md](../database/README.md) before `runserver`, entering the password with `Read-Host`. If PostgreSQL is not in use, clear those variables; otherwise the backend reports `no password supplied`.

| Variable | Default | Description |
| --- | --- | --- |
| `OUTLOOK_ENABLED` | `false` | Master switch |
| `OUTLOOK_INVITE_MODE` | `allowlist` | `none`, `allowlist` or `all`; see Section 2 |
| `OUTLOOK_ALLOWED_ATTENDEES` | Empty | Comma-separated addresses allowed as attendees in `allowlist` mode |
| `OUTLOOK_TOKEN_FILE` | `.local/outlook-token` in DEBUG | Token saved by Option A |
| `OUTLOOK_PUBLIC_CLIENT_ID` | Empty | Application (client) ID for Option B |
| `OUTLOOK_AUTHORITY` | `common` | Option B sign-in endpoint; `consumers` also works for personal accounts only |
| `OUTLOOK_REFRESH_TOKEN_FILE` | `.local/outlook-refresh-token` in DEBUG | Option B refresh-token file |

## 5. Live testing

### 5.1 Automated live check

```powershell
.\.venv\Scripts\python.exe manage.py outlook_live_check
```

This command follows the real system workflow on a temporary event **without an attendee** in your calendar and prints PASS or FAIL for each step:
1. Connect to and read the calendar.
2. Create an event.
3. Read it back and confirm its contents match the booking.
4. Move the same event as a reschedule would.
5. Delete it as a cancellation would, and confirm deletion.

Success displays `All live Outlook checks passed.`. A failure partway through still removes the temporary event. The command never prints the token.

### 5.2 Manual end-to-end checklist for demonstrations and screenshots

1. **Check the connection:** sign in to the frontend as z9000001 through Staff sign-in with demo password `123`. Open Calendar Sync and select Check connection. It should display Connected and your email address.
2. **Write after approval:** as z1000001, request Lab Room 1 for a time 7–28 days away, then approve it as an Admin. Outlook should show `SmartLab booking: Lab Room 1`, and the Calendar Sync row should display Synced.
3. **Change or delete in Outlook:** drag or delete the event in Outlook. The website booking remains unchanged and the system does not restore the event immediately.
4. **Reschedule:** as Manager z9000002, reschedule the booking. The Outlook event moves to the new time. If it was deleted in Step 3, the system recreates it at the new time.
5. **Cancel:** cancel the booking. The event is deleted from Outlook and the row displays Removed (cancelled).
6. **Book on behalf:** as the Manager, book for z1000001 and have an Admin approve it. The body says "Booked by Demo manager (on behalf)". An invitation is sent only if z1000001's email address is in the allowlist.

## 6. Scheduled processing

The Docker Compose `scheduler` service periodically processes due reviews and pending Outlook updates. Other PostgreSQL deployments can run `manage.py run_scheduler` continuously, or use Windows Task Scheduler or cron to run `manage.py process_due` every few minutes; `--outlook-limit` defaults to 10. These commands refuse to run in memory mode. Use Sync now on the page or `POST admin/outlook/process/` instead.

## 7. Status and retrying failures

- Booking `status` and calendar `outlook_sync.status` are independent. A booking remains valid if calendar synchronisation fails.
- Failures retry with exponential backoff starting at 30 seconds and capped at one hour, while respecting Microsoft's Retry-After response.
- The **Calendar Sync page** (`/admin/calendar-sync`, Admin/Manager) is a development visualisation that may be removed before final delivery. It shows connection state, synchronisation totals for synced, pending and failed tasks, and failed bookings first, with Retry, Check connection and Sync now actions.

| Method | Path, under `/api/v1/` | Purpose |
| --- | --- | --- |
| GET | `admin/outlook/` | Configuration, statistics and per-booking status without calling Microsoft |
| POST | `admin/outlook/check/` | Read the calendar once to test sign-in and permission; body `{}` |
| POST | `admin/outlook/process/` | Process pending updates; body `{"limit":1}`, maximum 5 |
| POST | `admin/bookings/{id}/outlook-retry/` | Retry immediately; body `{}` |

| Error code | Meaning and action |
| --- | --- |
| `TOKEN_EXPIRED` / `GRAPH_HTTP_401` | Token expired: paste a new token for Option A or run `outlook_login` for Option B, then select Retry |
| `OUTLOOK_LOGIN_EXPIRED` | Option B sign-in expired: rerun `outlook_login` |
| `OUTLOOK_NOT_CONFIGURED` | No token has been saved and sign-in is incomplete |
| `GRAPH_HTTP_403` / `OUTLOOK_CALENDAR_READ_ONLY` | Calendar read/write permission is missing, or the target calendar is read-only |
| `GRAPH_HTTP_404` | Target event does not exist. During rescheduling this indicates a deleted event and causes recreation rather than an error |
| `GRAPH_HTTP_429` | Microsoft rate limiting; retry automatically according to Retry-After |
| `GRAPH_NETWORK_ERROR` | Network unavailable or timed out; retry automatically after recovery |
| `STUDENT_EMAIL_NOT_CONFIGURED` | Booking beneficiary has no university email address |

To **remove the Calendar Sync page**, delete only the following frontend items; the backend endpoints may remain:
- `src/features/admin/CalendarSyncPage.tsx`, `src/features/admin/calendar-sync.ts`
- One corresponding line from each of `app/routes.ts`, `app/AppRouter.tsx` and `app/AppLayout.tsx`
- The corresponding tests

## 8. Production handover (Microsoft 365)

A production service can configure `OUTLOOK_TENANT_ID`, `OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET` and `OUTLOOK_MAILBOX` to write calendars with application identity. This requires application `Calendars.ReadWrite` permission, administrator consent and a mailbox access scope. Remove personal token and sign-in files at the same time.

Writing directly to every person's calendar also requires university IT authorisation, which the client is seeking. A student's SSO sign-in does not replace this authorisation. Production may set `OUTLOOK_INVITE_MODE=all`.

Database table `outlook_sync_record` stores the event ID, iCal UID, target path, version, retry time and lease. The booking, sync record and audit are saved in one transaction. The Microsoft network request runs outside the transaction, after which the version is reread before saving the result.

Microsoft documentation: [Create event](https://learn.microsoft.com/en-us/graph/api/calendar-post-events?view=graph-rest-1.0), [Update event](https://learn.microsoft.com/en-us/graph/api/event-update?view=graph-rest-1.0), [Delete event](https://learn.microsoft.com/en-us/graph/api/event-delete?view=graph-rest-1.0), [Device code sign-in](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-device-code), [Permissions](https://learn.microsoft.com/en-us/graph/permissions-reference#calendarsreadwrite).
