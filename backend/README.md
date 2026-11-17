# SmartLab Booking Backend

Django 5.2 + Django REST Framework 3.16. Provides REST APIs for student availability searches, room and individual-equipment bookings, induction evidence submission, qualification review and booking review. See [frontend-api.md](docs/frontend-api.md) for the frontend handover and [openapi.json](docs/openapi.json) for the complete interface definition. While running, `GET /api/schema/` also returns the OpenAPI JSON.

## Features and rules

- **Long-booking requests** (1.22.0): submit a purpose and reason through the separate `POST bookings/long-bookings/`. This exempts only the normal per-booking duration limit, which defaults to three hours. It still counts toward the weekly 12-hour limit and eight future bookings, and still follows the normal 7–28-day window, resource maximum duration, opening hours and qualification requirements. It cannot be combined with an urgent, additional-hours or recurring request. All numbers continue to come from existing configuration.
- **Long-booking review:** when the time is free, it is held until the resource's review deadline; when it conflicts, it enters the existing first-come, first-served waitlist. Only a Manager may approve or reject it and cannot review their own or a request they created. An unresolved request expires at the review deadline and releases its time; it is never approved automatically. Approval applies only to the original resource and interval; rescheduling requires cancellation and a new request. Existing databases must apply migration 012 before 013.
- **One set of booking rules for everyone:** Students, Admins and Managers can book, but **a request can be submitted only when the required induction is verified and remains valid through the entire booking**. Evidence that is pending, rejected or expired does not qualify; staff have no exception. Only an Admin or Manager can review induction evidence, and nobody may review their own.
- **Booking on behalf:** an Admin or Manager can use `on_behalf_of_zid` to book for somebody else. The booking belongs to the beneficiary (`student_id`, whose induction is checked); `created_by` records the creator, and the audit records both. Staff cannot approve their own or a request they created.
- **Urgent requests:** a request earlier than the minimum notice, seven days by default, can be marked urgent and requires a reason. Only the notice rule is bypassed; induction, opening hours and conflicts still apply. The time must be free and cannot join a waitlist. Only a Manager decides it, it is never approved automatically, and it expires if unresolved before the start.
- **Additional-hours requests** (1.21.0): use the separate `POST bookings/additional-hours/` to request time beyond the normal weekly allowance. Purpose and reason are required. It can be submitted before the normal allowance is used. While pending, it neither holds the resource nor consumes the normal weekly 12 hours, but pending and approved additional-hours requests count toward the eight-future-booking limit. A Manager may approve only within the configured period before the start, 48 hours by default, after rechecking availability, qualification and priority. The three-hour per-booking limit, opening hours and 28-day maximum notice still apply. This workflow permits short-notice requests and is exempt from the seven-day minimum. It is never approved automatically and expires unresolved at its start.
- **Fair ordering for additional hours:** among currently approvable additional-hours requests that overlap on the same resource and time, users with no started and checked-in use across resources during the target booking's local Monday–Sunday week and users in active data collection share the first priority group. Within that group, order by submission time and ID. A data-collection claim requires an explanation and explicit Manager confirmation at approval; invalid claims should be rejected. Requests with neither priority condition form a later group, also first-come, first-served. Normal approved bookings and active holds take precedence. Additional-hours requests do not hold time against one another. Approval rechecks everything in a transaction, while the audit records the priority basis, order, window, collection confirmation and authorised interval.
- **Scope of additional-hours approval:** approval applies only to the exact resource and interval. The ordinary reschedule endpoint cannot move it; cancel and request again. Admins cannot approve or reject additional-hours requests, and Managers cannot review their own or one they created. Requests, outcomes and expiry use existing notification channels, with a dedicated Manager task notification.
- **Only a Manager reschedules directly:** a Manager may change any approved normal future booking without the minimum-notice restriction (`RESCHEDULED_BY_MANAGER`). Long-booking and additional-hours approval is fixed to its original interval and requires cancellation and a new request.
- **Beneficiary change requests** (1.16.0, `POST bookings/{id}/change/`): the beneficiary can request a different time for their approved future booking. The system creates a request whose `replaces_id` points to the original. A free time enters review; an occupied time joins the waitlist. The original remains until the change is approved, when it is cancelled as `REPLACED_BY_CHANGE` and its time is offered to the waitlist. Cancelling the original also cancels any unresolved change request as of 12 November 2026. Ordinary request rules apply, except the original is not a conflict or duplicate. Only one unresolved change request can exist per booking, and a change request cannot be urgent.
- **Weekly allowance during a change:** before the original starts, an original and unresolved same-week change reserve the longer of their two durations, avoiding double charging or early release when shortening. A cross-week change reserves allowance in both weeks until decision; approval releases the original week, while withdrawal or rejection releases the new week. Once the original has started, both count separately. Manual approval, automatic approval and waitlist promotion all recheck the weekly allowance.
- **Induction prerequisites:** one induction may require another through `QualificationRequirement.prerequisite_ids`, stored as `prerequisite_ids uuid[]`. In demo data, Advanced laboratory training requires General laboratory induction. Without General, a user cannot submit Advanced evidence and an Admin cannot verify Advanced. General and Advanced must both remain valid through the end of an Advanced-resource booking; missing General returns `qualification_status=PREREQUISITE_REQUIRED`. A Manager configures `{"prerequisite_ids":[...]}` through `PATCH /api/v1/admin/qualification-requirements/{id}/`; cycles are rejected.
- **Shared rule checks:** creation, Admin approval, automatic deadline processing, waitlist promotion and rescheduling all call the same `BookingService.rule_violation`. It checks active account, available resource, valid time, booking window for creation/rescheduling, and qualifications and prerequisites, in that order. No path bypasses a check.
- **Account state:** deactivating a student immediately rejects every unresolved request with `ACCOUNT_DEACTIVATED` and promotes the next person. Since 10 November 2026, it also cancels not-yet-started approved bookings as `CANCELLED_BY_STAFF`, notifies the beneficiary and releases the time; started bookings remain. Approval and automatic processing recheck activity and can return `AUTO_REJECTED_ACCOUNT_INACTIVE`.
- **Rooms and equipment:** equipment records its containing room in `room_id` and is grouped by room on the page. Closing or maintaining a room pauses only bookings for the room itself and **does not affect** equipment in it, which has independent status. The two are **booked separately**; booking a room does not include equipment, stated on the page since 1.16.0 while the client decides how combinations should work. Since 1.16.0, a room can have `capacity`, and every resource can have up to 12 label/value `details` entered by a Manager on Resources.
- **Normal requests first enter `PENDING_APPROVAL`** with `reason_code=AWAITING_REVIEW`. They are not confirmed but hold the time for the applicant until `hold_until = review_due_at`. An Admin or Manager may decide at any time. At the resource's `pending_hold_minutes` deadline, default 1440 minutes or 24 hours and no later than the booking start, the system decides automatically: approve with `AUTO_APPROVED_AFTER_REVIEW_WINDOW` if qualifications still cover the booking, the resource is available and no approved conflict exists; otherwise reject with an `AUTO_REJECTED_*` code and explanatory `decision_reason`. `reviewed_by` becomes `SYSTEM`. Outlook is written only after approval.
- Bookings require at least seven and at most 28 days' notice by default. The maximum applies to every role, booking on behalf and each date of a staff recurring series. These values are configurable rather than hard-coded; see Configurable rules below. Approval rechecks qualification and conflict and cannot approve a duplicate interval.
- Strict first-come, first-served ordering applies to a time. Approved bookings and pending requests with an active hold occupy it. Later overlaps enter `WAITLISTED` with `TIME_CONFLICT` or `TEMPORARY_HOLD_CONFLICT`. Staff cannot approve a waitlisted request directly but may reject it. When the time opens through cancellation, rejection, expiry, rescheduling or reopening, the system promotes in submission order. An eligible beneficiary moves to a new `PENDING_APPROVAL` with `PROMOTED_FROM_WAITLIST` and a recalculated deadline; an ineligible request is rejected. Once the first request is approved, later entries remain backups until they expire at the start. Rejected induction evidence also rejects all dependent unresolved requests with `QUALIFICATION_REJECTED`.
- A student cannot submit overlapping active requests for the same resource. Existing `PENDING_APPROVAL`, `WAITLISTED` or `APPROVED` records return `DUPLICATE_BOOKING`. A final cancelled, rejected or expired record permits another request. Simultaneous bookings for different resources are not duplicates.
- Students view their dashboard, qualifications and bookings and cancel active bookings that have not started. Staff My Bookings also includes requests they created for others. Admins and Managers review queues and decisions and may cancel anybody's booking as `CANCELLED_BY_STAFF`; Managers may reschedule and change duration.
- A Manager can place a room or equipment under maintenance or close it through `PATCH /api/v1/admin/resources/{id}/status/` with a required reason. This pauses new requests, approval and promotion. Existing bookings remain listed for the Manager to decide whether to cancel. Returning to available promotes the waitlist. Since 1.16.0, a status change automatically sends in-app and email notifications (`RESOURCE_OUT_OF_SERVICE` / `RESOURCE_REOPENED`) to people with future bookings or requests for that resource.
- **Booking records** (Admin/Manager, Booking records): `GET /api/v1/admin/bookings/?status=ALL` searches everyone's bookings by resource, student, date, name or zID (`q`), including student zID and name. `GET /api/v1/admin/bookings/export/` exports the same filters to CSV with creator, recurring-series and attendance details.
- **A Manager has every Admin permission**, plus exclusive access to review-window configuration, resource status, user management and Lab setup from 1.16.0. **An Admin cannot access a Manager page or endpoint**, including reading review windows. User management includes `GET /api/v1/admin/users/` with `is_staff` and student induction status; Add staff through `POST /api/v1/admin/users/staff/` with role `ADMIN` or `MANAGER`; and account deactivation/reactivation through `PATCH /api/v1/admin/users/{id}/`. **Student, Admin and Manager are separate account types fixed at creation.** Students cannot be promoted, and Admins and Managers cannot switch roles; attempts return 409 `ROLE_CHANGE_NOT_ALLOWED`. Create a replacement account and deactivate the old one. Users cannot modify themselves, at least one active Manager must remain, and every change is audited. `POST /api/v1/admin/users/managers/` is a compatibility alias for Add staff with Manager selected.
- Admins and Managers query audit history through `GET /api/v1/admin/audit/` by resource, student, action and time. It covers requests, decisions, rescheduling, cancellation and qualification review.
- **Calendar subscription link:** every person has one private URL from `GET /api/v1/calendar/link/`, containing a system-generated random token unrelated to a Microsoft token. Paste it into Outlook's Subscribe from web. Outlook periodically reads `GET /api/v1/calendar/{token}.ics`, containing approved bookings where that person is the beneficiary. Rescheduling updates the entry and cancellation removes it. `POST calendar/link/reset/` generates a new token and invalidates the old link immediately. Outlook controls refresh timing, which may take hours.
- **In-app notifications** (top-bar bell, `GET /api/v1/notifications/`): request received, booking approved or rejected including automatic decisions, waitlist promotion, Manager reschedule, staff cancellation, booking created for you, induction result and absence. Managers also receive urgent requests. Ordinary new requests do not notify staff. A notification and its state change commit in one transaction. Additional channels are configured through `NOTIFICATION_CHANNELS` in `booking/notification_channels.py`.
- **Email notifications:** `booking/email_channel.py` uses a Gmail system mailbox with SMTP and an app password to send request received, approval/rejection, expiry, promotion, reschedule, staff cancellation, reminder, booking on behalf, change-request outcome and resource maintenance/reopening notifications to the beneficiary's university address. It is disabled by default with `EMAIL_ENABLED`. When enabled, `EMAIL_MODE` defaults to `allowlist`; demonstrations use `redirect` to send everything to the tester. Email is written to PostgreSQL with the notification, and the scheduler retries temporary SMTP failures with backoff, retaining tasks through restarts. Test with `manage.py send_test_email --to your-email`. See [email-setup.md](docs/email-setup.md).
- **Check-in:** the beneficiary of an approved booking selects I'm here in My Bookings from 15 minutes before until 30 minutes after the start (`POST bookings/{id}/check-in/`). An unconfirmed booking becomes `attendance=NO_SHOW` after the window. A resource under maintenance or closed at the time becomes `EXCUSED`. The beneficiary is notified to cancel in future if unable to attend. Absence is for usage reporting only and has no penalty; version 1.25.0 removed freezing and unfreeze requests following the Week 8 client meeting.
- **Maximum 24 half-hour slots (12 hours) per person per week:** normal pending, waitlisted, approved and recurring booking duration for one beneficiary counts within the resource-local Monday–Sunday week. Separate additional-hours requests and approved additional-hours bookings do not consume this normal allowance. Neither does extending a booking in progress: an extension always needs a Manager's approval, and the Manager decides whether the extra time is reasonable. A new normal request is added to current use; more than 24 slots returns 409 `WEEKLY_LIMIT_REACHED`, including a Manager reschedule. Cancellation, rejection and expiry release slots automatically. A booking on behalf counts against the beneficiary.
- **Maximum eight active future bookings per person:** pending, waitlisted, approved and recurring bookings count. Exceeding the limit returns 409 `FUTURE_BOOKING_LIMIT_REACHED`. Cancellation, rejection, expiry or the start of a booking releases a place. A booking on behalf counts for the beneficiary. One approved booking and its unresolved change request count as one.
- **Recurring bookings for staff only:** select Repeat weekly on a resource card, then weekdays, time, duration and date range. The pattern spans at most 14 weeks, while every occurrence must still lie in the current booking window. Preview each date through `POST bookings/series/preview/`; dates with problems are skipped rather than waitlisted, then create through `POST bookings/series/`. Every date uses the current 7–28-day window for both self and on-behalf bookings. Dates too far ahead return `BOOKING_TOO_FAR_AHEAD` and must be skipped at creation. Opening hours, beneficiary induction and conflicts still apply. As staff create the series, valid occurrences are **approved immediately**. Each is an ordinary booking with `series_id`, cancellable individually or for the remaining series through `POST bookings/series/{id}/cancel/`; check-in still applies.
- **Manager resource management through the website** (Resources, `GET/POST /api/v1/admin/resources/`, `PATCH admin/resources/{id}/`):
  - Creation requires name, location and induction. Equipment may select a containing room and category. Opening hours, 15/30/60-minute step, maximum duration and review window have defaults.
  - Active resource names are case-insensitively unique. Rooms cannot have a containing room or category. Opening and closing times align to the step; maximum duration is a multiple of the step and fits within opening hours.
  - Kind, room or equipment, is fixed after creation (`KIND_IS_FIXED`). Editing does not change existing bookings. New rules apply to later requests, approval and automatic processing. `bookings_outside_rules` lists future bookings that no longer fit, for the Manager to cancel or reschedule.
  - Resources are archived, not deleted, through `POST …/archive/`; they disappear from booking pages while history and audits remain, and can be restored through `POST …/restore/`. A resource with future bookings returns `RESOURCE_HAS_BOOKINGS`; a room containing equipment returns `ROOM_HAS_EQUIPMENT`.
  - Creation, update, archive and restore write `RESOURCE_CREATED`, `RESOURCE_UPDATED` with changed fields, `RESOURCE_ARCHIVED` and `RESOURCE_RESTORED` audits.
- **Reminders** in the notification bell: 24 hours before an approved booking, remind the beneficiary to select I'm here; within 14 days of a verified induction's expiry, remind them to upload again; at its start, notify that an unpromoted waitlisted or unresolved pending request expired. Each reminder is sent once.
- **Usage report** (Manager only since 1.26.0, Usage statistics under Booking records, `GET /api/v1/admin/reports/usage/?first_date=&last_date=`): for each resource and date range, approved count, booked hours, proportion of opening time, attendance rate as checked in / (checked in + absent), absences, cancellations and rejections. Read-only.
- **Staff password change** (Account, `POST /api/v1/auth/change-password/`): requires the current password; the new password has at least eight characters and differs from the current one. Students use university sign-in and have no password here.
- **Lab setup** (1.16.0, Manager, `/manager/setup`): create inductions; edit their name and four guidance sections—how to complete, accepted evidence, reviewer and contact—shown under Induction & Training; and maintain laboratory contact details through `GET/PATCH site/contact/`, displayed in Help, approved bookings and induction guidance.
- **Staff home** (`GET admin/overview/`): an Admin lands on Today with pending inductions, bookings, waitlist, changes, requests near deadline, out-of-service resources and today's bookings. A Manager lands on Lab overview from 1.26.0 with Manager-only decisions for urgent, additional-hours and long requests, room status, weekly use and zID history lookup; Today remains available.
- **Role-scoped data** (1.26.0): Booking Records and CSV give Admins only bookings ending within the last seven days or later; complete history is Manager-only. Equipment owner, UNSW asset number, source and specifications live in a separate table accessible only to Managers through `GET/PATCH admin/resources/{id}/internal/`.
- **Create the first Manager:** `python manage.py create_manager --zid z9000003 --name "Lab Manager" --email z9000003@ad.unsw.edu.au` outputs a one-time invite code for activation on staff sign-in. PostgreSQL mode only.

Pending is not confirmed but holds the time until its deadline, preventing later users from taking a request under review. Conflicts enter the waitlist without holding time. Every resource has one qualification requirement, which may have prerequisites, and its validity must cover the booking end.

A Manager reads a resource's review window through `GET /api/v1/admin/resources/{id}/booking-policy/` and updates it with `PATCH {"pending_hold_minutes":1440}`. Values are integers from 1 to 20160 minutes, default 1440 or 24 hours. A change affects only later requests. An Admin cannot read or update it. The seed default comes from `default_review_window_minutes`.

## Configurable rules for client changes

Global numbers the client may adjust are centralised in `BookingRules` in `booking/rules.py`. Business code reads only through `RulesProvider.current()` and rereads for each check:

| Rule | Field | Default | Environment variable |
| --- | --- | --- | --- |
| Minimum advance days | `min_advance_days` | 7 | `MIN_ADVANCE_DAYS` |
| Maximum advance days | `max_advance_days` | 28 (4 weeks) | `MAX_ADVANCE_DAYS` |
| Induction validity days | `qualification_validity_days` | 120 | `QUALIFICATION_VALIDITY_DAYS` |
| Default review window for new resources, minutes | `default_review_window_minutes` | 1440 | `DEFAULT_PENDING_HOLD_MINUTES` |
| Longest normal booking, hours | `max_slots_per_booking` | 3 | `MAX_HOURS_PER_BOOKING` |
| Hours one person may hold per week | `max_slots_per_week` | 12 | `MAX_HOURS_PER_WEEK` |
| Step in which hours are counted, minutes (both hour limits must be whole steps) | `booking_slot_minutes` | 30 | `BOOKING_SLOT_MINUTES` |
| Maximum active future bookings per person | `max_active_future_bookings` | 8 | `MAX_ACTIVE_FUTURE_BOOKINGS` |
| Hours before start when additional hours may be approved | `additional_hours_approval_window_hours` | 48 | `ADDITIONAL_HOURS_APPROVAL_WINDOW_HOURS` |
| Check-in opens this many minutes before start | `check_in_opens_minutes` | 15 | `CHECK_IN_OPENS_MINUTES` |
| Check-in closes this many minutes after start | `check_in_closes_minutes` | 30 | `CHECK_IN_CLOSES_MINUTES` |
| Maximum recurring-pattern weeks, without widening each date's booking window | `max_series_weeks` | 14 | `MAX_SERIES_WEEKS` |
| Reminder hours before booking start | `reminder_hours_before` | 24 | `REMINDER_HOURS_BEFORE` |
| Reminder days before induction expiry | `induction_reminder_days` | 14 | `INDUCTION_REMINDER_DAYS` |

- Current: the default `SettingsRulesProvider` reads these environment variables; restart after changing a value.
- Future: if the client wants Manager-page editing, create a database-backed provider whose `current()` returns `BookingRules`, then point `RULES_PROVIDER` to it, for example `my_app.rules.DatabaseRulesProvider`. Booking, review and qualification code needs no change.
- Per-resource rules—opening hours, step, maximum duration, review window, required induction and status—remain on the resource. A review deadline never extends beyond the start and is not lengthened by refreshing or replaying the same idempotent request.

A real Microsoft Graph Outlook adapter is provided. Approval creates an event, Manager rescheduling updates it, and cancellation deletes it. Sync state is independent of booking state and failures can retry. The system never reads Outlook changes: **the website is always authoritative**. Deleting an event from a personal calendar causes recreation only when a Manager later reschedules it. By default only addresses in `OUTLOOK_ALLOWED_ATTENDEES` are invited. Admins and Managers can inspect connection and status on the development Calendar sync page. The integration is disabled by default. See [outlook-setup.md](docs/outlook-setup.md) for setup, refreshable personal sign-in and `manage.py outlook_live_check`. Automated tests mock responses; a live connection requires local Microsoft authorisation.

The booking page supports browsing resource cards or **Find a free time**, which filters by date, duration, kind, room and equipment category, displays all resources' daily availability in one table and opens a booking from a free time. Endpoint: `GET resources/day-overview/`; see [frontend-api.md](docs/frontend-api.md). Equipment `category` values in demo data are fictional.

**Not implemented:** real university SSO, Outlook email notification (Gmail SMTP email exists), equipment collection/return, student recurring bookings, and complete Manager configuration of global rules, which currently use environment variables.

**Two storage modes:** the default in-memory demonstration adapter loses demo data, attachments and event mappings on process restart and supports only one process. The PostgreSQL adapter persists them; see [database/README.md](database/README.md). See [DEPLOY.md](../DEPLOY.md) for the Docker Compose server deployment with PostgreSQL, gunicorn and nginx.

## Local startup (PowerShell)

Run from this directory:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
$env:DEBUG = "true"
$env:ENABLE_DEMO_AUTH = "true"
$env:DJANGO_SECRET_KEY = "local-demo-only-change-this-key"
$env:ALLOWED_HOSTS = "localhost,127.0.0.1"
$env:CORS_ALLOWED_ORIGINS = "http://localhost:3000,http://localhost:5173"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

Example variables are in [.env.example](.env.example). Copying it to `.env` does not load it automatically; set process environment variables or use an environment-loading tool.

`ENABLE_DEMO_AUTH` defaults off. Sign-in endpoints work only when both it and `DEBUG=true` are set explicitly. Tokens last 3600 seconds and use `Authorization: Bearer <access_token>`.

**Two sign-in entry points**; the account, never the entry point, determines the role:

- **Student:** University sign-in, currently simulated SSO through `POST /api/v1/auth/demo-login/`, accepts a zID without a password. A staff zID returns 403 `USE_STAFF_SIGN_IN`.
- **Admin/Manager:** staff sign-in with zID and password through `POST /api/v1/auth/staff-sign-in/`. A student zID returns 403 `STUDENT_USES_SSO`.
- **Creating staff:** a Manager selects Add staff in user management. The system generates an invite such as `K7Q4-9MZD`, displayed until activation. The user selects First activation on staff sign-in, enters zID and invite and chooses a password of at least eight characters through `POST /api/v1/auth/staff-activate/`; the invite then expires.
- **Forgotten password:** a Manager selects Reset access through `POST /api/v1/admin/users/{id}/reset-access/`. The old password becomes invalid, a new invite is generated, and the user activates again without changing role.
- Only a Django password hash is stored, separately in `StaffCredential` / `staff_credential`, and never returned by an API. This is the prototype until university SSO is available. When staff also use SSO, replace sign-in while keeping role decisions unchanged.

Demo identities:

| zID | Role | Sign-in method |
| --- | --- | --- |
| `z1000001` | STUDENT | Simulated university sign-in; valid General induction |
| `z1000002` | STUDENT | Simulated university sign-in; must upload induction first |
| `z9000001` | ADMIN | Staff sign-in, demo password `123` |
| `z9000002` | MANAGER | Staff sign-in, demo password `123` |

Obtain a student token with `POST /api/v1/auth/demo-login/` and `{"zid":"z1000001"}`. Staff use `POST /api/v1/auth/staff-sign-in/` with `{"zid":"z9000002","password":"123"}`. The demo password applies only to those two fictional accounts. `demo-register` creates only STUDENT and never accepts a requested staff role. [docs/openapi.json](docs/openapi.json) lists every endpoint.

Demo registration requires `zid`, `display_name` and `university_email`. It validates only email format, not university membership or ownership. Production authentication receives trusted SSO claims. Seed identities use matching `zID@ad.unsw.edu.au` demo addresses.

As required by the client prototype, seed data contains two laboratories, `101` and `102`, and 20 independent example equipment resources, `201`–`220`, each with separate availability. `101` and ordinary equipment in Lab Room 1 require General induction `00000000-0000-0000-0000-000000000001`. `102` and specialist Lab Room 2 equipment such as `202` Camera 001, the 3D printer and laser cutter require Advanced training `00000000-0000-0000-0000-000000000002`. Complete resource IDs share prefix `00000000-0000-0000-0000-000000000`; see `DEMO_RESOURCES` in `booking/runtime.py`. Student `z1000001` has only General and cannot request Advanced resources. Actual names and rules come from `GET resources/`.

## Checks

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test
```

Exact verified dependency versions are in `requirements-lock.txt` for reproducing the environment.

Tests use temporary in-memory data and cover qualification gates, pending requests and deadlines, manual and automatic decisions, waitlist promotion, concurrent conflict, Manager rule permissions, identity email and the API contract. A database adapter also needs its own transaction and concurrency tests.

## Business-code locations

See [ARCHITECTURE.md](../ARCHITECTURE.md) for overall structure, [CHANGELOG.md](../CHANGELOG.md) for changes and [SPRINT3.md](../SPRINT3.md) for the Sprint 3 feature/code inventory.

All business rules live under `booking/services/`, with one public `BookingService` entry point (`from booking.services import BookingService`). Topic mixins attach their methods to the same object and call each other through `self.xxx`:

| File | Responsibility |
| --- | --- |
| `base.py` | Clock, rules, role checks, audit writing, resource lookup and status-group constants |
| `accounts.py` | User list/deactivation, staff invite/sign-in and beneficiary lookup |
| `resources.py` | Manager create/edit/archive/restore, review windows, maintenance/closure and booking records |
| `qualifications.py` | Induction upload, review, validity and prerequisites |
| `checks.py` | Shared `rule_violation` and conflict queries |
| `bookings.py` | Creation, including on-behalf and urgent, review, cancellation and Manager reschedule |
| `waitlist.py` | Expiry, automatic deadline decisions and waitlist promotion |
| `availability.py` | One resource's daily slots and the booking-page day overview |
| `audit.py` | Audit queries |
| `notifications.py` | In-app bell notifications; other channels are in `booking/notification_channels.py` |
| `calendar_feed.py` | Calendar subscription; `booking/ics.py` renders iCalendar |
| `attendance.py` | Check-in and absence records |
| `series.py` | Staff recurring bookings |
| `reminders.py` | Upcoming-booking and induction-expiry reminders |
| `reports.py` | Manager usage reports |
| `changes.py` | Beneficiary change requests (1.16.0) |
| `site_contact.py` | Laboratory contact details (1.16.0) |
| `overview.py` | Staff Today overview (1.16.0) |

Put a new feature in its topic file. For a new topic, create a mixin and add it to the `BookingService` inheritance list in `booking/services/__init__.py`.

## Production database integration

Business logic depends on the `Repository` protocol in [booking/repository.py](booking/repository.py), not direct Django ORM queries. An adapter implements user, resource, qualification requirement, submission, booking and audit persistence. See [booking/domain.py](booking/domain.py) for entities and [database-interface.md](docs/database-interface.md) for new fields, blocking queries and transaction contracts. Every bookable resource requires an induction; missing configuration rejects requests rather than bypassing the gate. Attachments use the private `FileStorage` interface in [booking/storage.py](booking/storage.py).

`Repository.atomic(resource_ids, student_ids)` must be a real transaction coordinating:

1. Consistent resource and student lock ordering.
2. Rereading qualification inside the transaction, querying approved and unexpired pending holds through `list_blocking_bookings`, checking interval conflicts, then saving state and audit.
3. Identical locking for creation, manual approval, automatic deadline processing and waitlist promotion.
4. Complete rollback on failure so concurrent requests cannot both be approved. Never query availability and then write independently.

Intervals use `[start, end)`, so one booking may start when another ends. The database stores timezone-aware values, the API emits UTC, and resource rules use `Australia/Sydney`. Each physical device is an independent resource rather than an inventory quantity for a model.

`REPOSITORY_FACTORY` and `FILE_STORAGE_FACTORY` are importable factory paths returning protocol implementations. Memory mode requires no tables or migration. A production adapter may use Django ORM, PostgreSQL or another database while preserving interfaces and transaction guarantees. Replace the memory instance at production startup; the demo repository cannot support multiple processes. `SEED_DEMO_DATA` controls demo seeds and is permitted only in DEBUG.

## Real SSO and background time processing

Real SSO verifies university credentials and maps them to local `Principal` fields: `id`, `zid`, `display_name`, `university_email`, `role`, `active`. Roles come from trusted university claims or local management, never a browser-submitted role. Induction comes from qualification records; successful SSO does not imply qualification.

`AUTH_PROVIDER` configures the real authentication adapter. Its no-argument provider implements `resolve_bearer(token: str) -> Principal`, verifies signature, expiry and audience, and maps trusted identity to a database user. Demo Bearer authentication is not university SSO. After integration, keep `/auth/me/` and business endpoints; adjust only frontend redirection and token acquisition for the university solution.

Each request stores `review_due_at`, calculated on entering pending review from resource `pending_hold_minutes`. Booking queries and actions advance due state, including automatic decisions and expiry after the start. An Admin can call `POST /api/v1/admin/process-due/`. The Docker `scheduler` invokes the same logic every minute so processing continues without site visits.

Only the owner and Admin/Manager can download evidence through the protected endpoint. Production storage must remain private. The service is not a real campus service until deployment configuration, SSO, database, background jobs and file service are complete.

## Qualification source and validity

After verification, a qualification expires review time plus `QUALIFICATION_VALIDITY_DAYS`, default 120 days or approximately one term. Reviewers cannot choose the expiry. A booking must end no later than it. Valid qualifications cannot renew early; rejected or expired ones can be resubmitted. Revocation is not implemented. The 120-day value is a demo default, not confirmed client policy.

`BookingService.qualification_expiry` in `booking/services/qualifications.py` centralises calculation. A future term-end or per-type rule changes only that location. Every booking path—creation, approval, reschedule and availability—uses `BookingService.qualification_state`, which reads the latest submission for the resource's requirement.

If the client later wants Moodle completion to establish qualification, add an adapter that reads authorised completion records containing zID, course/module and completion time, then saves a `VERIFIED` `QualificationSubmission` for the corresponding `requirement_id`, identifies the source in `reviewed_by`, and calculates `valid_until` with `qualification_expiry`. Booking, review, conflict and hold rules remain unchanged. Moodle integration requires a university API and data authorisation and must be implemented and maintained by the client; this project does not connect to Moodle.

## Outlook and database handover

`booking/outlook.py` defines `CalendarProvider` and the real Microsoft Graph adapter. `booking/calendar_sync.py` manages mapping, backoff retry, cancellation compensation and processing leases. A personal demo writes every resource booking to one default calendar; `OUTLOOK_MAILBOX` and `OUTLOOK_CALENDAR_ID` select a Microsoft 365 calendar. Sync is one way: Outlook changes are never read or applied to bookings, which can be changed only in SmartLab.

The adapter implements `get_outlook_sync(booking_id)`, `list_outlook_sync()` and `save_outlook_sync(record)` for `OutlookSyncRecord`. Booking, sync record and audit save in one `atomic` transaction. Claim a processing lease under the same resource/student locks, perform the network call outside the transaction, then reread the version and update it. Retain event mappings for cancelled bookings.

Memory mode tries sync after booking API calls. Staff can process failures through Calendar sync or `admin/outlook/process/` and `admin/bookings/{id}/outlook-retry/`. With a shared database, schedule `python manage.py process_due --outlook-limit 10` (the Docker `scheduler` already does this). An independent process cannot access the demo server's memory, so the command rejects the memory adapter.

## Scheduled due processing

Requests require a trigger at their review deadline, and an unconfirmed attendance requires recording after its window. Web requests advance state incidentally, but nothing happens when the site is idle. Docker Compose includes a persistent `scheduler`; other database deployments can run:

```powershell
.\.venv\Scripts\python.exe manage.py run_scheduler
```

Alternatively run this every minute with Windows Task Scheduler or cron:

```powershell
.\.venv\Scripts\python.exe manage.py process_due
```

It reports processed due requests, email tasks and Outlook tasks. `--email-limit` defaults to 50; with Outlook enabled, `--outlook-limit` defaults to 10. It also rejects the memory adapter.

## Local test console (1.17.0)

To enable account **1** without a password, set these before starting the local backend. The test account works **only with the in-memory store**: test bookings never reach the PostgreSQL database, so they cannot show up in real records, reports or the Today page, and restarting the backend clears them.

```powershell
$env:DEBUG="true"
$env:ENABLE_DEMO_AUTH="true"
$env:ENABLE_TEST_CONSOLE="true"
$env:AUTH_PROVIDER="booking.authentication.DemoIdentityProvider"
$env:REPOSITORY_FACTORY="booking.repository.MemoryRepository"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

The existing machine-local `start-backend.ps1` also accepts `-TestConsole`, which always starts in memory mode (as if `-Memory` were given). Stop the previous backend in its own terminal before starting it again. Without `-TestConsole`, the script disables this feature.

Account 1 automatically owns every induction permanently, including later additions; it never needs evidence uploads. Turning off booking-rule bypass retains these inductions. See the [1.17.1 contract](docs/frontend-api.md#1171-account-1-owns-every-induction).

Open the frontend sign-in page, choose **Test console**, enter **1**, then use **Test role** and **Bypass booking rules** in the top bar. Bypass starts on. It applies to this account's own bookings; choose a staff role to test staff pages or weekly series. Turn it off to test normal restrictions. See the [API contract](docs/frontend-api.md#1170-functional-controls) for the exact scope. This is the only development exception to the ordinary-account rules above. No database migration is required. Do not enable it on deployed services.
