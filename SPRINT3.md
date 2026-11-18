# Sprint 3 Features and Code

This checklist lists every feature added in Sprint 3, together with the files, functions, endpoints, pages, and tests for each feature, to make review and demonstration easier. Code from before Sprint 3 is not included.

> **2026-10-25 addition (edited by deepseek and reviewed by Loy)**: This document records Sprint 3 features that have **already been implemented**. The new section below describes the Sprint 3 goals and scope (not implemented; for planning). See [SPRINT2.md](SPRINT2.md) for the Sprint 2 plan.

## Sprint 3 Goals and Scope (planned on 2026-10-25, not implemented)

Goal in one sentence: deploy to the cloud, use a realistic amount of data, and connect the client's real sign-in system.

| ID | Item | Target | Dependencies / risks |
| --- | --- | --- | --- |
| S3-1 | Visualisation | Usage statistics charts, Today page graphics, Room Management timeline, and My Bookings progress bars; prefer hand-written SVG without adding a chart library | No external dependency; frontend only |
| S3-2 | Cloud deployment | Choose a platform, managed PostgreSQL, HTTPS, environment variables, persistent uploaded files, and backups | Loy must choose the platform; consider storage for induction files and Outlook tokens |
| S3-3 | Load testing | k6 or Locust: concurrent availability searches, concurrent attempts to book the same time, and approval throughput; report P95 and error rate | Requires a cloud environment first |
| S3-4 | Real SSO | Integrate UNSW OAuth/SAML | **Strong client dependency**; approval may take 2–4 weeks |
| S3-5 | Real Outlook | Integrate Graph/Google using a university or personal student account | **Strong client dependency**; confirm the account type first (see `claude/reports/2026-10-25-outlook-personal-calendar.md`) |

Recommended order: cloud deployment → load testing → visualisation → real SSO/Outlook (after the client is ready). S3-4 and S3-5 are external dependencies, so requests to the client should start during Sprint 2.

**How to identify Sprint 3 code**
- New files: the first line says `Sprint 3`.
- Modified existing files: new code blocks have a `Sprint 3` comment before them or `# Sprint 3` at the end of the line.

**Versions**: API OpenAPI 1.12.0 to 1.16.0; database migrations 006 (1.12.0) and 007 (1.16.0). Versions 1.13.0 to 1.15.0 do not change the database. See [CHANGELOG.md](CHANGELOG.md) for the reason behind each change, and Section 10 of [ARCHITECTURE.md](ARCHITECTURE.md) for the function that implements each rule.

## Feature Overview

| # | Feature | Users | Page | Version |
| --- | --- | --- | --- | --- |
| 1 | Calendar subscription link | Everyone | My Bookings | 1.12.0 |
| 2 | In-app notifications (bell) | Everyone | Top bar | 1.12.0 |
| 3 | Check-in and absence records (freezing removed in 1.25.0) | Everyone | My Bookings | 1.12.0 |
| 4 | Maximum of three bookings per person per week | Everyone | Book a Resource | 1.12.0 |
| 5 | Recurring bookings for staff | Admin, Manager | Repeat weekly on a resource card | 1.12.0 |
| 6 | Manager room and equipment management on the website | Manager | Resources | 1.13.0 |
| 7 | Reminders for upcoming bookings, expiring inductions, and expired requests | Everyone | Bell | 1.13.0 |
| 8 | Usage report | Manager (from 1.26.0; Admin was also allowed in 1.14.0–1.25.0) | Booking Records → Usage statistics | 1.13.0 |
| 9 | Staff password change | Admin, Manager | Account | 1.13.0 |
| 10 | `create_manager` command to create the first Manager | Deployers | Command line | 1.13.0 |
| 11 | Email notifications (Gmail system mailbox) and “request received” confirmation | Received by everyone; configured by deployers | Email, bell | 1.14.0 |
| 12 | Booking Records: search, filter, and export everyone's bookings | Manager sees all; Admin only sees the last seven days (1.26.0) | Booking Records | 1.14.0 |
| 13 | Combine a recurring series into one card in My Bookings | Everyone | My Bookings | 1.14.0 |
| 14 | Show duration in hours and use a more compact page header | Everyone | Book a Resource, My Bookings, etc. | 1.14.0 |
| 15 | First visualisation set: bell animation and panel, resource covers, time-cell colours and “now” line, and base animations | Everyone | Top bar, Book a Resource, all pages | 1.15.0 |
| 16 | User-experience report changes: time-change requests, maintenance notices, contact details, induction guidance, resource information, Find a free time explanations, booking form, and staff Today home page | Everyone; Manager completes Lab setup | My Bookings, Book a Resource, Induction & Training, Help, Today, Lab setup, etc. | 1.16.0 |

## 1. Calendar Subscription Link

Each person has a private URL. In Outlook (or Google Calendar or Apple Calendar), select “Subscribe from Internet.” Microsoft authorisation is not required.

- **Backend**:
  - `booking/services/calendar_feed.py`: `calendar_feed` (generate or reset the random token) and `calendar_feed_events` (bookings included in the subscription).
  - `booking/ics.py`: `render_calendar` (iCalendar text).
  - `views/calendar.py`: `CalendarLinkView`, `CalendarLinkResetView`, and `CalendarFeedView`.
- **Endpoints**: `GET calendar/link/`, `POST calendar/link/reset/`, and `GET calendar/{token}.ics` (no sign-in is required; the random token is the key).
- **Frontend**: `features/booking/CalendarSubscribe.tsx`; the URL is assembled by `calendarUrl` in `features/booking/attendance.ts`.
- **Data**: `calendar_feed` table.
- **Tests**: `CalendarFeedTests` and `test_calendar_link_and_public_feed` in `test_sprint3.py`.

## 2. In-App Notifications

- **Backend**:
  - `booking/services/notifications.py`:
    - `_booking_changed`: called whenever a booking is saved to decide consistently whether to send a notification.
    - `_notify` and `_notify_managers`.
    - `list_notifications`, `mark_notification_read`, and `mark_all_notifications_read`.
  - Delivery-channel interface (reserved for Outlook or email): `booking/notification_channels.py`, called by `NotificationDeliveryMiddleware` in `middleware.py`; configured through `NOTIFICATION_CHANNELS`.
- **Endpoints**: `GET notifications/`, `POST notifications/{id}/read/`, and `POST notifications/read-all/`.
- **Frontend**: `features/notifications/`, including `NotificationBell.tsx`, `notifications.ts`, and `notifications.css`.
- **Data**: `notification` table.
- **Tests**: `NotificationTests` and `test_notifications_api` in `test_sprint3.py`; `test_extra_channels_receive_new_notifications_after_the_request`; frontend `tests/sprint3.test.mjs`.

## 3. Check-In and Absence Records

Version 1.25.0 (2026-11-07) removed freezing and unfreeze requests (client Week 8 meeting; migration 014). This section now covers only check-in and absence records.

- **Rule**: The user must select I'm here from 15 minutes before to 30 minutes after the start time. Otherwise, an absence is recorded and the user is notified (with a reminder to cancel in future if they cannot attend). A resource under maintenance or closed at the time does not count. Absences have no penalty and are used only in usage reports.
- **Backend**: `check_in_window`, `check_in_state`, `check_in`, and `_process_attendance` in `booking/services/attendance.py`.
- **Endpoint**: `POST bookings/{id}/check-in/`.
- **Frontend**: I'm here button in My Bookings: `MyBookings.tsx` and `attendance.ts`.
- **Data**: `booking.attendance` and `checked_in_at`.
- **Tests**: `AttendanceTests` and `test_check_in_and_booking_fields` in `test_sprint3.py`; `test_weekly_series_check_in_and_missed_booking_are_persisted` in `test_postgres.py`.

## 4. Maximum of Three Bookings per Person per Week

- **Backend**: `_weekly_limit_violation` in `booking/services/checks.py`, called by `create_booking` and `reschedule_booking` in `bookings.py`.
- **Error**: `WEEKLY_LIMIT_REACHED`.
- **Tests**: `WeeklyLimitTests` and `test_weekly_limit_api_error` in `test_sprint3.py`.

## 5. Recurring Bookings for Staff

- **Backend**: `_series_plan`, `_series_check`, `preview_series`, `create_series` (approved directly), `series_detail`, and `cancel_series` in `booking/services/series.py`.
- **Endpoints**: `POST bookings/series/preview/`, `POST bookings/series/`, `GET bookings/series/{id}/`, and `POST bookings/series/{id}/cancel/`.
- **Frontend**: `features/booking/RecurringBookingForm.tsx` and `series.ts`; opened through Repeat weekly on the resource card in `ResourceCard.tsx` (`BookingApp.tsx`).
- **Data**: `booking_series` table and `booking.series_id`.
- **Tests**: `SeriesTests` and `test_series_api` in `test_sprint3.py`; Playwright `staff book a weekly series…`.

## 6. Manager Room and Equipment Management on the Website

- **Rules**: described at the top of `booking/services/resources.py`:
  - Name, location, and required induction are mandatory; names must be unique.
  - A room cannot have a parent room or category.
  - Times must align with 15-, 30-, or 60-minute steps; the maximum duration must fit within opening hours.
  - The resource type cannot be changed after creation.
  - An edit does not modify existing bookings; it lists bookings that no longer satisfy the new rules.
  - Resources are archived, not deleted; a resource cannot be archived while it has future bookings or, for a room, contains equipment.
- **Backend**: `booking/services/resources.py`:
  - Main functions: `list_all_resources`, `create_resource`, `update_resource`, `archive_resource`, and `restore_resource`;
  - Field rules: `_check_resource_fields`;
  - Bookings affected by an edit: `_bookings_outside_rules`.
- **Endpoints**: `GET/POST admin/resources/`, `PATCH admin/resources/{id}/`, `POST admin/resources/{id}/archive/`, and `POST admin/resources/{id}/restore/`.
- **Frontend**: `features/manager/ManagerResourcesPage.tsx` (Resources); form rules are in `features/manager/resource-form.ts`.
- **Data**: no schema change; continues to use `bookable_resource`.
- **Tests**: `test_resource_setup.py`; `test_resource_setup_is_persisted` in `test_postgres.py`; frontend `tests/resource-form.test.mjs`; Playwright `a Manager adds equipment…` and `Admins do not see the Resources page`.

## 7. Reminders

- **Rules**:
  - Remind users to select I'm here 24 hours before an approved booking starts;
  - Remind users when an approved induction expires within 14 days;
  - Notify users that a waitlisted or pending request has “expired” if it has not been promoted or decided by its start time.
  - Send each reminder only once.
- **Backend**:
  - `_send_reminders`, `_booking_reminders`, and `_induction_reminders` in `booking/services/reminders.py`, called at the end of `process_due_requests` in `waitlist.py`.
  - 2026-11-01: reminders call `_notify(..., once=True)` in `notifications.py` and recheck the recipient and booking/induction link inside the write lock, preventing web requests and the scheduler from generating duplicate notifications and emails concurrently.
  - “Expired” notifications are handled by `_booking_changed` in `notifications.py`.
  - Rule values: `reminder_hours_before` and `induction_reminder_days` in `rules.py`.
- **Tests**: `test_reminders.py`; the two `test_concurrent_*_reminders_create_one_notification_and_email` tests in `test_postgres.py` verify concurrent deduplication against a real database.

## 8. Usage Report

- **Backend**: `usage_report` in `booking/services/reports.py` (read-only).
- **Endpoint**: `GET admin/reports/usage/?first_date=&last_date=`.
- **Frontend**: `features/records/UsageTab.tsx` (from 1.14.0, the Usage statistics tab in Booking Records; previously the separate Usage Report page `ManagerUsagePage.tsx`) and `features/manager/usage.ts`.
- **Tests**: `test_usage_report.py`; frontend `tests/usage.test.mjs`; Playwright `an Admin reads the usage statistics on Booking Records` and `the old Usage Report address opens the usage statistics tab`.

## 9. Staff Password Change

- **Backend**: `change_password` in `booking/services/accounts.py`.
- **Endpoint**: `POST auth/change-password/`.
- **Frontend**: `features/auth/ChangePassword.tsx`, shown on the Account page (`app/UtilityPages.tsx`).
- **Tests**: `test_change_password.py`; Playwright `staff change their password…` and `students have no password form`.

## 10. `create_manager` Command

- **Usage**: `python manage.py create_manager --zid z9000003 --name "Lab Manager" --email z9000003@ad.unsw.edu.au`; outputs a one-time invitation code.
- **Backend**:
  - Command: `booking/management/commands/create_manager.py`.
  - Logic: `bootstrap_manager` in `booking/services/accounts.py`. It shares `_create_staff_account` with Add staff, so both paths follow exactly the same rules.
- **Tests**: `test_create_manager.py`.

## 11. Email Notifications and “Request Received”

- **Rules**:
  - Send to the university email address of the person receiving the booking; `EMAIL_NOTIFICATION_KINDS` in `settings.py` determines which notifications are emailed.
  - `EMAIL_MODE` determines who actually receives messages: `none`, `allowlist` (default), `redirect` (demo: redirect all messages to one address), or `all`.
  - A delivery failure is logged and does not affect the booking.
- **Backend**:
  - `booking/email_channel.py`: `EmailChannel.deliver` (decide whether to send, compose, and enqueue), `choose_recipient` (select recipient by mode), `compose` (subject and body), `booking_label`, and `site_link`; `EmailOutbox` (2026-10-27: send on a background thread, share one connection within a batch, and log every email); `notification_channels.wait_for_deliveries` (wait for background delivery in commands and tests). Logging is configured through `LOGGING` in `config/settings.py`.
  - Configuration: `EMAIL_*` and `SITE_URL` in `config/settings.py`; when `EMAIL_ENABLED=true`, the email channel is added to `NOTIFICATION_CHANNELS`.
  - Command: `booking/management/commands/send_test_email.py`.
  - “Request received”: `_created_notices` in `services/bookings.py` (`BOOKING_SUBMITTED`); staff recurring bookings: `create_series` in `services/series.py` (`SERIES_CREATED`); time wording: `describe_moment` in `services/notifications.py`.
- **Documentation**: `backend/docs/email-setup.md`.
- **Tests**: `test_email_channel.py` (added on 2026-10-27: `test_the_response_does_not_wait_for_the_mail_server`, `test_emails_waiting_together_share_one_connection`, `test_each_sent_email_is_logged_with_its_notification_and_recipient_domain`, and `test_a_mail_server_that_cannot_be_reached_is_logged_and_later_emails_still_go`); assertions for `BOOKING_SUBMITTED` and `SERIES_CREATED` in `test_sprint3.py`.

## 12. Booking Records

- **Backend**:
  - `booking_report` in `services/resources.py` adds `query` (part of a zID or name, for either the booking holder or creator).
  - `AdminBookingQuerySerializer` in `serializers.py` adds `q`; `staff_booking_rows` in `views/admin.py` passes it through.
  - `AdminBookingExportView` in `views/admin.py` is changed so Admin can use it, and the CSV adds Weekly series and Attendance columns; `usage_report` in `services/reports.py` is changed so Admin can also use it.
- **Endpoints**: `GET admin/bookings/?q=` and `GET admin/bookings/export/?q=`.
- **Frontend**:
  - `features/records/BookingRecordsPage.tsx` (Records and Usage statistics tabs); filters become endpoint parameters in `features/records/records.ts` (`recordQuery`, `sydneyMidnight`, `creatorText`, and `attendanceText`).
  - `listBookingRecords` and `downloadBookingRecords` in `features/booking/api.ts`.
  - Route `/admin/records` (`routes.ts`, `AppRouter.tsx`, and `AppLayout.tsx`); the old `/manager/usage` address redirects here.
  - The export button is removed from `features/manager/ManagerBookingsPage.tsx`.
- **Tests**: `test_manager_tools.py` (`q` search, Admin export, and new columns) and `test_usage_report.py`; frontend `tests/sprint3-records.test.mjs`; Playwright `staff search booking records and export the same list as CSV` and `students do not see Booking Records`.

## 13. Combine a Recurring Series into One Card

- **Frontend**: `groupBookings` and `seriesSummary` in `features/booking/my-bookings.ts`; `SeriesCard` in `MyBookings.tsx`.
- **Tests**: `tests/sprint3-records.test.mjs`; Playwright `my bookings shows a weekly series as one card`.

## 14. Durations in Hours and a More Compact Page Header

- **Frontend**:
  - `fmtDuration` in `features/booking/format.ts` (`1.5 h`); `fmtSpan` is used separately for wording such as “a few minutes ago.” The duration selector in `FindTime.tsx` also uses it.
  - `BookingApp.tsx`: induction information on one line (`bk-induction-strip`).
  - `CalendarSubscribe.tsx`: initially shows only the Subscribe in calendar button.
  - Styles are in the Sprint 3 section at the end of `booking.css`.
- **Tests**: `tests/sprint3-records.test.mjs`; Playwright `book a resource shows all inductions on one line with an upload link` and `my bookings: check in, and get the calendar subscription link`.

## 15. First Visualisation Set

- **Bell**:
  - `features/notifications/notifications.ts`: `notificationIcon` (type → icon), `groupNotifications` (group by Sydney date into “Today / Earlier”), and `shouldRing` (animate only when the unread count increases, not on the first load).
  - `NotificationBell.tsx`: `ringKey` remounts the icon to replay the ringing animation, while `key={badge}` replays the badge pop; the panel has groups, icons (`KindIcon`), two-line messages, and blue unread dots.
  - `notifications.css`: badge selector `.nt-bell-button > .nt-badge` (overrides the 27px rule in `shell.css`), `nt-ring`, `nt-pop`, and `nt-panel-in`; on narrow screens (≤600px), the panel becomes fixed to the viewport.
- **Resource covers**: `coverKey` in `features/booking/covers.ts` (keywords in room/category/name → cover type); `ResourceCover` and `COVER_ICONS` in `ResourceCard.tsx`; styles in the `.bk-cover` section of `booking.css`.
- **Time cells**: colours and borders in the `.ui-tl-*` and `.ui-legend` sections of `ui/ui.css`; “now” line: `nowLineFraction` in `features/booking/slot-cells.ts` and `NowLine`/`NowLegend` in `features/booking/NowLine.tsx`, used by `SlotPicker.tsx` and `FindTime.tsx`.
- **Base animations**: variables `--motion-fast`, `--motion-base`, `--ease-out`, and `--ease-spring`, plus the global reduced-motion switch in `index.css`; page fade-in in `app/AppLayout.tsx` (`app-page`, `key={pathname}`) and `app/shell.css`; modal animation in `booking.css` (`bk-modal-in`), confirmation dialogs and buttons in `ui/ui.css`, and home-page number cards in `features/dashboard/dashboard.css`.
- **Tests**: `tests/sprint3-visual.test.mjs`; Playwright `the bell badge stays small, and the panel groups notifications with an icon each`.

## 16. User-Experience Report Changes (1.16.0)

- **Time-change requests**:
  - Backend: `request_time_change` (who can request and when), `open_change_for`, and `_apply_time_change` (cancel the original booking when the new request is approved, called by `_save_booking` in `base.py`) in `services/changes.py` (`ChangesMixin`). The `replaces` argument of `create_booking` in `bookings.py` excludes the original booking from duplicate, weekly-limit, and conflict checks; `also_exclude` in `_overlaps` in `checks.py`; waitlist promotion in `waitlist.py` applies the same exclusion. Notifications are in `notifications.py` (`CHANGE_REQUESTED`, `CHANGE_APPROVED`, `CHANGE_REJECTED`, and `_old_time_note`).
  - Data: `Booking.replaces_id`; database column `booking.replaces_id` and partial unique index `booking_one_open_change_idx` (one booking can have only one pending change request).
  - Endpoint: `POST bookings/{id}/change/` (`BookingChangeView` in `views/bookings.py`); booking JSON adds `replaces_booking` and `open_change`.
  - Frontend: `features/booking/ChangeTimeBox.tsx` and `change-requests.ts` (`canAskForChange`, `openChangeText`, `replacesText`, and `changeSentMessage`); Change time in `MyBookings.tsx`; `takenNote` in `SlotPicker.tsx` (explains that a selected occupied time can only join the waitlist).
- **Maintenance and closure notifications**: `set_resource_status` → `_notify_status_change` in `services/resources.py` (`RESOURCE_OUT_OF_SERVICE`/`RESOURCE_REOPENED`, one per affected booking, sent only when the status actually changes); email kinds are in `EMAIL_NOTIFICATION_KINDS` in `settings.py`. Frontend confirmation dialog and `is-attention` row in `ManagerBookingsPage.tsx`.
- **Contact details**: `SiteContact` in `domain.py`; `site_contact` and `update_site_contact` in `services/site_contact.py`; new single-row `site_contact` table; endpoint `GET/PATCH site/contact/` (`SiteContactView`). Frontend `features/contact/contact.ts` (`hasContact`, `mailtoLink`), `site-contact-store.ts` (`useSiteContact`), and `LabContact.tsx` (`LabContactCard`, `ContactLink`), used in Help, My Bookings, and induction guidance.
- **Induction guidance and creation**: `how_to_complete`, `accepted_evidence`, `reviewer`, and `contact` on `QualificationRequirement`; `create_requirement`, `update_requirement`, and `_check_requirement_fields` in `services/qualifications.py`; endpoints `POST admin/qualification-requirements/` and `PATCH …/{id}/`. Frontend `features/induction/guide.ts` (`guideItems`) and `InductionGuide.tsx`; `InductionRow.tsx` displays the guidance.
- **Lab setup page** (Manager, `/manager/setup`): `features/manager/LabSetupPage.tsx` (Inductions and Contact details tabs) and `lab-setup.ts` (`requirementChanges` sends only changed fields).
- **Resource information**: `ResourceDetail` and `Resource.capacity`/`details` in `domain.py`; `_check_resource_fields` in `services/resources.py` (capacity 1–1000, rooms only, up to `MAX_DETAILS = 12` rows); database columns `bookable_resource.capacity` and `details jsonb` (`_JSON_LISTS` in `postgres.py`). Frontend `ResourceFacts` in `ResourceCard.tsx`; Fits at least filter in `BookingApp.tsx`; `DetailsEditor` in `ManagerResourcesPage.tsx`; validation and hour conversion (`hoursFromMinutes`, `minutesFromHours`, `describeHours`) in `resource-form.ts`.
- **Separate room and equipment booking guidance**: `SEPARATE_BOOKING_TEXT` in `features/booking/format.ts`, displayed in `BookingForm.tsx` and `BookingApp.tsx`.
- **Find a free time**: backend `too_long` and `not_bookable` from `day_overview` in `services/availability.py`; frontend `features/booking/find-time.ts` (`FIND_DURATIONS`, `hiddenSummary`) and `FindTime.tsx`.
- **Booking form**: `submitBlocker` in `format.ts` (what is still missing); `BookingForm.tsx` (required markers and `bk-submit-row`); `SlotPicker.tsx` (`onAskEarlier`, start-time and duration selectors through `chooseByInputs`).
- **Staff Today home page**: `staff_overview` in `services/overview.py` (`DUE_SOON_HOURS = 6`, `LIST_LIMIT = 10`); endpoint `GET admin/overview/` (`StaffOverviewView`). Frontend `features/admin/TodayPage.tsx` and `today.ts` (`todoCards`, `attendanceLabel`); `homePath` in `app/routes.ts` sends staff to `/admin/today`.
- **Other**: `BookingReviewPage.tsx` (Purpose column, Details button, and Change from); `CalendarSubscribe.tsx` (`CALENDAR_APPS`); styles in the `Sprint 3 (1.16.0)` sections of `booking.css` and `ui/ui.css`.
- **Database**: repeatable `database/migrations/007_change_requests_guidance_details_contact.sql`; synchronised `schema.sql`.
- **Tests**: backend `tests/test_change_requests.py` and `tests/test_lab_setup.py`, two additions to `test_postgres.py`, and one change to `test_day_overview.py`; frontend `tests/sprint3-review.test.mjs`; Playwright `a student asks to move a booking; a taken time can only join the waitlist`, `staff start on Today, whose cards open the pages that handle them`, `the induction page says how to get an induction and offers the lab's email`, `Find a free time says why nothing can be booked`, and `a Manager saves the lab's contact details on Lab setup`.

## All New Files

- **Backend**:
  - Services (`booking/services/`): `attendance.py`, `calendar_feed.py`, `notifications.py`, `series.py`, `reminders.py`, `reports.py`, `changes.py`, `site_contact.py`, and `overview.py` (the last three in 1.16.0)
  - Other code: `booking/ics.py`, `booking/notification_channels.py`, `booking/email_channel.py`, `booking/management/commands/create_manager.py`, and `send_test_email.py`
  - Migrations: `database/migrations/006_calendar_notifications_attendance_series.sql` and `007_change_requests_guidance_details_contact.sql` (1.16.0)
  - Tests (`booking/tests/`): `test_sprint3.py`, `test_resource_setup.py`, `test_reminders.py`, `test_usage_report.py`, `test_change_password.py`, `test_create_manager.py`, `test_email_channel.py`, `test_change_requests.py`, and `test_lab_setup.py` (the last two in 1.16.0)
- **Frontend**:
  - Pages and components:
    - `features/auth/ChangePassword.tsx`
    - `features/booking/CalendarSubscribe.tsx` and `RecurringBookingForm.tsx`
    - `features/manager/ManagerResourcesPage.tsx` (`ManagerUsagePage.tsx` became `features/records/UsageTab.tsx` in 1.14.0)
    - `features/records/BookingRecordsPage.tsx` and `UsageTab.tsx`
    - `features/notifications/NotificationBell.tsx`
    - `features/booking/NowLine.tsx` (1.15.0)
    - 1.16.0: `features/booking/ChangeTimeBox.tsx`, `features/admin/TodayPage.tsx`, `features/manager/LabSetupPage.tsx`, `features/contact/LabContact.tsx`, and `features/induction/InductionGuide.tsx`
  - Supporting files:
    - `features/booking/attendance.ts`, `series.ts`, and `my-bookings.ts`
    - `features/records/records.ts`
    - `features/manager/resource-form.ts` and `usage.ts`
    - `features/notifications/notifications.ts` and `notifications.css`
    - `features/booking/covers.ts` (1.15.0)
    - 1.16.0: `features/booking/change-requests.ts`, `find-time.ts`, `features/admin/today.ts`, `features/manager/lab-setup.ts`, `features/contact/contact.ts`, `site-contact-store.ts`, and `features/induction/guide.ts`
  - Tests: `tests/sprint3.test.mjs`, `tests/resource-form.test.mjs`, `tests/usage.test.mjs`, `tests/sprint3-records.test.mjs`, `tests/sprint3-visual.test.mjs` (1.15.0), `tests/sprint3-review.test.mjs` (1.16.0), and `tests/ui-internal-tool.test.mjs` (Section 20)
- **Documentation**: `SPRINT3.md` (this file) and `backend/docs/email-setup.md`

## Modified Existing Files (all additions are marked Sprint 3)

- **Backend**:
  - Entities and storage: `domain.py`, `repository.py`, and `postgres.py`
  - Rules and configuration: `rules.py`, `config/settings.py`, and `.env.example`
  - Endpoints: `serializers.py`, `views/`, `urls.py`, and `middleware.py`
  - Services (`booking/services/`): `__init__.py`, `accounts.py`, `availability.py`, `base.py`, `bookings.py`, `checks.py`, `qualifications.py`, `resources.py`, and `waitlist.py`
  - Command: `management/commands/process_due.py`
  - Database: `database/schema.sql`
  - Tests: `tests/test_postgres.py`, `tests/test_user_management.py`, `tests/test_manager_tools.py`, and `tests/test_day_overview.py` (1.16.0)
- **Frontend**:
  - Framework: `app/AppLayout.tsx`, `app/AppRouter.tsx`, `app/routes.ts`, and `app/UtilityPages.tsx`
  - Booking pages: `features/booking/BookingApp.tsx`, `MyBookings.tsx`, `ResourceCard.tsx`, `FindTime.tsx`, `SlotPicker.tsx`, `slot-cells.ts`, `BookingForm.tsx`, and `icons.tsx` (the last two in 1.16.0)
  - Other pages (1.16.0): `features/admin/BookingReviewPage.tsx` and `features/induction/InductionRow.tsx`
  - Global styles (1.15.0): `index.css`, `app/shell.css`, `ui/ui.css`, and `features/dashboard/dashboard.css`
  - Manager page: `features/manager/ManagerBookingsPage.tsx`
  - API, types, and formatting: `features/booking/api.ts`, `types.ts`, `format.ts`, and `booking.css`
  - Tests: `tests/routing.spec.ts` and `tests/session-routing.test.mjs` (1.16.0)
- **Documentation**:
  - Repository root: `ARCHITECTURE.md`, `CHANGELOG.md`, and `README.md`
  - Backend: `backend/README.md`, `backend/database/README.md`, `backend/docs/frontend-api.md`, `backend/docs/database-interface.md`, `backend/docs/outlook-setup.md`, `backend/docs/email-setup.md`, and `backend/docs/openapi.json`
  - Frontend: `frontend/README.md`

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
| DB | `database/migrations/008_notification_preferences.sql`, `schema.sql` `notification_preference` | New and upgraded databases compared with `pg_dump --schema-only` |
| Docs | `backend/docs/openapi.json` 1.18.0 (69 routes), `backend/docs/frontend-api.md`, CHANGELOG 1.18.0 | openapi check |

## 23. Review fixes, demo sign-up and Docker deployment (API remains 1.18.0)

No API, schema or booking-rule change. Review: project docs `claude/reports/2026-10-25-review-1.18.0.md`.

| ID | Code locations | Verification |
| --- | --- | --- |
| RV-D1 | `features/booking/SlotPicker.tsx` wheel effect (depends on `data`; hands the wheel back to the page at either end) | routing test `a mouse wheel scrolls the day timeline sideways once the day has loaded` (fails on the old effect) |
| RV-D2 | `services/notifications.py` `save_notification_preferences` (check all names, then save in `repo.atomic()`) | `test_notification_preferences.py` `test_a_refused_save_changes_nothing` |
| SU-1 | `features/auth/MockSsoPage.tsx` `create` (Create one → Create account form, `demoRegister`); `features/auth/mock-sso.css` `.mock-sso-create`, `.mock-sso-back` | routing tests `a new demo student creates an account on the mock sign-in page`, `the mock sign-in page offers no sign-up when demo registration is off` |
| DK-1 | `docker-compose.yml`, `.env.docker.example`, `backend/Dockerfile`, `backend/entrypoint.sh` (new database: schema + optional `seed_*.sql` in one transaction; `migrate` subcommand), `backend/.dockerignore`, `frontend/Dockerfile`, `frontend/nginx.conf`, `frontend/.dockerignore`; steps in `DEPLOY.md` | `entrypoint.sh` run against a temporary local PostgreSQL (new database, restart keeps a changed password, `migrate`); containers not yet run (no Docker on the dev machine) |
## 24. Independent Notification Channels and Announcement Board (1.19.0, Sprint 3)

Scope: checklist items N1, N2, A1–A4, and D1. D2 is excluded; Docker/deployment files are unchanged, and EC2 is not redeployed.

| Item | Files and main functions | Automated verification |
| --- | --- | --- |
| N1 settings page and sidebar | `frontend/src/features/notifications/NotificationPreferences.tsx`; `app/routes.ts`, `AppRouter.tsx`, `AppLayout.tsx`, and `UtilityPages.tsx`; `features/booking/api.ts` and `types.ts`; `ui/workspace.css` | `1.19 notifications` for all three roles in `routing.spec.ts`: five categories and ten switches, selections retained after failure, persisted after refresh, entire email column unchecked while email is disabled, saved selections restored when email is re-enabled (review Q1), Account link, equal width at 390px, new text ≥12px |
| N2 notification channels | `Notification/NotificationPreference` in `backend/booking/domain.py`; `_category_channels/_notify`, preference functions, and notification-read functions in `services/notifications.py`; `notification_channels.py`; `serializers.py`; `views/notifications.py` | channels / partial_preferences in `Acceptance119` in `test_119.py`; `test_notification_preferences.py` updated for the new contract; HTTP `API119Tests` |
| A1 / A3 / A4 announcements and permissions | New `services/announcements.py`; new `views/announcements.py`; `services/__init__.py`, `views/__init__.py`, and `urls.py`; `Announcement` in `domain.py`; `repository.py` and `postgres.py` | expiry_order_history, ownership_matrix, and removal_time_must_be_in_the_future in `Acceptance119` (review R1); HTTP verifies student writes return 403, `kind` cannot be forged, and cross-author Admin/Manager permissions |
| A2 status announcements | `set_resource_status` in `services/resources.py`; `AnnouncementsMixin._status_announcement`; `ResourceStatusSerializer` in `serializers.py`; `views/admin.py` | Shared Memory/PG status_upsert (change reason without changing status, maintenance → closed, reopen, rooms and equipment, recovery estimate does not expire); status_and_announcement_roll_back_together |
| Database | `backend/database/schema.sql`; new `migrations/009_announcements_notification_channels.sql`; Memory transaction snapshots in `repository.py`; announcement reads/writes in `postgres.py` | New `Postgres119Tests` in `test_postgres.py` shares six service acceptance tests, plus old-preference upgrade and two consecutive runs of 009; a `pg_dump --schema-only` comparison of old and new databases |
| Frontend announcements | New `features/announcements/AnnouncementBoard.tsx`, `AnnouncementsPage.tsx`, and `dates.ts`; `dashboard/DashboardPage.tsx` and `admin/TodayPage.tsx`; new `manager/ResourceStatusDialog.tsx`; `manager/ManagerBookingsPage.tsx`; API/types/routes/workspace styles above | `routing.spec.ts` covers announcement publish/edit, failed-removal dialog, author on home page, student permissions, no section when empty, and 390px; status-dialog errors and retained inputs; new `announcement-dates.test.mjs` covers daylight saving and invalid dates |
| D1 documentation | `openapi.json` 1.19.0 (72 routes); `frontend-api.md`; `database/README.md`; CHANGELOG; this section; Section 10 of ARCHITECTURE; usage instructions in `frontend/README.md` and `PROJECT_GUIDE.md` | OpenAPI validation and route coverage; the task card records the actual output lines from the complete checks |

Pre-implementation failure logs and complete check results are outside the project in `9900/output/1.19.0-checks/`. See `claude/tasks-1.19.0.md` and this delivery report for final acceptance and the screenshot index. Actual external email delivery and the live EC2 page were not verified in this round.

## 25. Structure Cleanup S1 + S3 (2026-10-27, API remains 1.19.0)

Moves and deletions only; no behaviour changes. Report: Sections 4.3 and 4.4 of project document `reports/2026-10-27-code-structure-review.md`.

| Item | Content | Evidence |
| --- | --- | --- |
| S1 | Delete 31 unused CSS class names: 21 from booking.css, 8 from workspace.css, 3 from shell.css, and 2 from auth.css (`ttf` in the review checklist is a font extension, not a class name) | No class name is found in src/tests (task card); PostCSS comparison before and after deletion shows every removed selector contains a listed class and no declaration in retained rules changed (review report); all local checks pass; see screenshot comparison below |
| S3 | Move `features/booking/api.ts` and `types.ts` to `src/api/`: functions split into seven domain files plus `client.ts`, types split into eight files, and `index.ts` exports them together; delete old files without forwarders | Mapping table (task card); TypeScript syntax-tree comparison of 128 top-level statements: 126 are byte-for-byte identical, `post` only adds `export`, and the `ApiError` forwarder only changes the relative path; explanatory comments remain above their original declarations (review fix R1); `grep "features/booking/(api\|types)"` returns no results; all local checks pass; screenshot comparison: all 44 updated screenshots are pixel-identical to one screenshot from `8ae931f` (review fix R2) |
| Documentation | Section 7 of `ARCHITECTURE.md` and the path explanation in `frontend/README.md` | review |

## 26. Page Fluency Card B (2026-10-27, API remains 1.19.0)

Frontend only. Task card: project document `claude/tasks-fluency-2026-10-27.md`. Card A's maintenance flow is excluded.

| Item | Files and behaviour | Verification |
| --- | --- | --- |
| V2 | `frontend/src/features/booking/BookingApp.tsx` and `ui/workspace.css`: capacity and equipment-room filters are independent of the tab area | V2 in `tests/fluency.spec.ts` (320/390/1440px, full labels, tab only, equipment filter, no horizontal overflow) |
| V4 | `features/records/BookingRecordsPage.tsx` and `ui/workspace.css`: retain results and their filters; fade/use aria-busy/disable export while updating; recover after failure; CSV uses filters for the visible result set | V4 in the same file (delay, success, failure, and export query for old results) |
| V5 | New `features/announcements/use-announcements.ts`; `AnnouncementBoard.tsx` changed to receive state; `dashboard/DashboardPage.tsx` and `admin/TodayPage.tsx` coordinate the first home-page display | V5 in the same file (three roles, 1.6-second announcement delay, zero first-frame shift, failure/retry/empty announcements, late home-page data, announcements remain expanded during refresh) |
| V6 | `features/manager/ManagerBookingsPage.tsx`: initial-load error display and text retry only | V6 in the same file (no Loading after error, recovery after retry); existing routing tests verify other pages |
| V8 | `ui/workspace.css`: remove full-page entrance without affecting state animations | V8 in the same file (computed style has no entrance animation, reduced-motion still works) |

Failure logs, before/after screenshots, and complete check results are outside the project in `9900/output/fluency-2026-10-27/`; see the task card for the index and acceptance status.

## 27. Maintenance Flow Card A (2026-10-28, API remains 1.19.0)

Frontend only. Task card: project document `claude/tasks-maintenance-2026-10-27.md`.

| Item | Files and behaviour | Verification |
| --- | --- | --- |
| M1① | `listUnfinishedBookings(since)` in `frontend/src/api/admin.ts` (replaces `listApprovedBookings`); `features/manager/ManagerBookingsPage.tsx` requests only bookings and requests that have not ended | M1 in `tests/maintenance.spec.ts` (four requested statuses and `since`) |
| B1 | Booking table and Upcoming column in `ManagerBookingsPage.tsx` use only approved (`confirmed`) bookings; `manager/ResourceStatusDialog.tsx` shows the combined count of bookings and requests | B1 in the same file (dialog has three entries including pending and waitlisted; table contains only approved bookings) |
| V3 | `onSaved(resource)` in `ResourceStatusDialog.tsx` returns the resource received from the endpoint; `ManagerBookingsPage.tsx` updates the row immediately and disables status buttons during refresh | V3 in the same file (row already shows Maintenance and Reopen is disabled while refresh is delayed; recovers after refresh) |

## 28. Booking Filters, Personal History, and Home Page (2026-10-28, 1.20.0, migration 010)

| Item | Files and entry points | Verification |
| --- | --- | --- |
| F1 | `features/booking/MyBookings.tsx` and `ui/workspace.css`: resource/status intersection, URL, count, and Clear filters | booking history resource in `tests/routing.spec.ts` (three roles, refresh, empty results, and mobile) |
| H1 backend | `remove_booking_history` in `services/bookings.py`; `BookingHistoryRemoveView` and `my_bookings` in `views/bookings.py`; `urls.py`; `hide_booking` and `hidden_booking_ids` in `repository.py` / `postgres.py`; migration 010 / schema.sql | `test_booking_history.py`: permissions, statuses, idempotency, both parties in proxy bookings, rollback, preservation of source record/absence/calendar, API and Dashboard; persistence and two consecutive migration runs in `test_postgres.py` |
| H1 frontend | `removeBookingHistory` in `api/bookings.ts`; `MyBookings.tsx` and `SeriesCard.tsx`; `canRemoveBookingHistory` in `my-bookings.ts` | routing booking history removal (three roles, cancel confirmation, preserve on 503, success and refresh), removal by date |
| D1 | `DashboardPage.tsx`, `dashboard.css`, and `workspace.css`: separate statistics cards, compact Next session and booking list, staff Today banner | routing booking dashboard (real list shape, desktop and 320/390px); existing fluency cases regress announcements |
| Documentation | OpenAPI 1.20.0 / frontend-api.md, database README, Section 10 of ARCHITECTURE, CHANGELOG | openapi and schema checks; see the task card for exact output |

## 29. Load Testing (2026-10-29)

Scripts and results are in [load-test/README.md](load-test/README.md). See the three load-test rounds in CHANGELOG for code changes made for performance fixes.

## 30. Client Week 8 Meeting (2026-11-06, 1.24.0, no migration)

Task card: project document `claude/tasks-week8-2026-11-06.md`.

| Item | Files and entry points | Tests |
| --- | --- | --- |
| W1 Manager rule override | `_create_manager_booking` (called by `create_booking`) and `reschedule_booking` in `services/bookings.py`; `_availability` and `manager_override` for `day_overview` in `services/availability.py`; frontend guidance in `BookingForm.tsx`, `SlotPicker.tsx`, `dateRange` in `slot-picker.ts`, and `ManagerBookingsPage.tsx` | `test_a_manager_booking_overrides_the_rules_but_needs_free_time` in `test_approval_flow.py`; `test_a_manager_sees_times_inside_the_window_and_the_full_length` in `test_staff_booking.py`; time-change cases in `test_booking_window.py` and `test_sprint3.py` |
| W2 extend an in-progress booking | `extend_booking` in `services/changes.py`; `_period_violation` (`started` argument) in `checks.py`; `BookingExtendView` in `views/bookings.py`; `urls.py`; `BookingExtendSerializer` in `serializers.py`; frontend `extendBooking` in `api/bookings.ts`, `features/booking/extend.ts`, `ExtendBox.tsx`, `MyBookings.tsx`, and `ManagerBookingsPage.tsx` | `ExtendBookingTests` and `test_extend_a_booking_in_progress` in `test_change_requests.py`; `frontend/tests/extend.test.mjs` |
| W3 freezing disabled by default | Removed entirely in 1.25.0 (Section 31) | — |

## 31. Remove Freezing (2026-11-07, 1.25.0, migration 014)

Loy's decision: the client does not want an absence penalty, so freezing is removed completely. Task card: W4 in project document `claude/tasks-week8-2026-11-06.md`.

| Area | Removal or change |
| --- | --- |
| Database | `migrations/014_remove_booking_freeze.sql` drops table `unfreeze_request` and columns `app_users.no_show_count` and `frozen_until`; `schema.sql` synchronised |
| Backend | `domain.py` removes `Principal.no_show_count`, `frozen_until`, `frozen_at`, and `UnfreezeRequest`; `rules.py`, `settings.py`, and `.env.example` remove two freezing parameters; `attendance.py` retains only check-in and absence marking; remove all `frozen_violation` calls (`bookings.py`, `additional_hours.py`, `long_bookings.py`, and `series.py`), freezing fields in `availability.py`, `unfreeze_requests` in `overview.py`, unfreeze methods in both repositories, `views/unfreeze.py`, five endpoints, and four serializers |
| Frontend | Remove `FreezesPage.tsx`, `FreezeNotice.tsx`, the `/admin/freezes` route and menu entry, the unfreeze card on Today, and related API functions and types |
| Tests | Remove freezing and unfreeze tests; `test_missed_bookings_are_marked_and_notified_without_a_penalty` in `test_sprint3.py` confirms that five absences still do not affect booking |

## 32. Clear Differences Between the Three Roles (2026-11-07, 1.26.0, migration 015)

Client Week 8 meeting. Task card: W5–W7 in project document `claude/tasks-week8-2026-11-06.md`.

| Item | Files and entry points | Tests |
| --- | --- | --- |
| W5 Manager home page and role badge | New `features/manager/ManagerHomePage.tsx` and `manager-home.ts`; `MANAGER_DECIDES` and `cardsFor` in `admin/today.ts`; `TodayPage.tsx`; `homePath` and `/manager/home` in `app/routes.ts`; `AppRouter.tsx`; menu and `app-role-badge` in `AppLayout.tsx`; `ui/workspace.css` | `frontend/tests/roles.test.mjs`; Playwright `a Manager starts on the Lab overview, sees the role badge and looks up a zID` and `staff start on Today…` |
| W6 Admin sees only recent history | `booking_report` and `ADMIN_HISTORY_DAYS` in `services/resources.py`; `usage_report` in `services/reports.py` changed to `require_manager`; frontend `defaultRecordFilters` in `records/records.ts`, `BookingRecordsPage.tsx`, and `/manager/usage` in `routes.ts` | `AdminHistoryTests` in `test_roles.py`; `test_usage_report.py`; `roles.test.mjs`; Playwright `a Manager reads the usage statistics…` |
| W7 Manager-only equipment information | `ResourceInternalInfo` in `domain.py`; `get/save_resource_internal_info` in both repositories; `resource_internal_info`, `update_resource_internal_info`, and `INTERNAL_FIELDS` in `services/resources.py`; `AdminResourceInternalInfoView` in `views/admin.py`; `ResourceInternalInfoSerializer` in `serializers.py`; `migrations/015_resource_internal_info.sql` and `schema.sql`; frontend `api/resources.ts` and the Managers only section in `ManagerResourcesPage.tsx` | `InternalInfoTests` and `InternalInfoAPITests` in `test_roles.py`; `test_resource_internal_info_is_persisted` in `test_postgres.py` |

## 33. Extension Changed to Timeline Dragging and Manager Approval (2026-11-07, 1.27.0, migration 016)

Replaces the “takes effect immediately” behaviour in W2 of Section 30. Task card: W8 in project document `claude/tasks-week8-2026-11-06.md`.

| Area | Files and entry points | Tests |
| --- | --- | --- |
| Data | `Booking.extension_end` in `domain.py`; `migrations/016_extension_requests.sql` (adds the column and `booking_extension_end_check` constraint) and `schema.sql` | `test_extension_request_is_persisted` in `test_postgres.py` |
| Backend | `extend_booking` (student submits a request; Manager applies immediately), `review_extension`, `_check_extension`, and `_apply_extension` in `services/changes.py`; `extension_requests` in `services/overview.py`; `BookingExtensionReviewView` in `views/bookings.py`; `ExtensionReviewSerializer` in `serializers.py`; `urls.py`; notifications `EXTENSION_REQUESTED`/`APPROVED`/`REJECTED` (email kinds in `notifications.py` and `settings.py`) | Three `ExtendBookingTests` and `test_extend_a_booking_in_progress` in `test_change_requests.py` |
| Frontend | `features/booking/ExtendBox.tsx` (timeline, dragging, and arrow keys); `timelineCells`, `latestEnd`, `waitingExtension`, and `sydneyDate` in `extend.ts`; waiting message in `MyBookings.tsx`; `extensions` card in `admin/today.ts`; `ExtensionRow` in `manager/ManagerHomePage.tsx`; `reviewExtension` in `api/bookings.ts`; `.ext-*` in `ui/workspace.css` | `tests/extend.test.mjs`; Playwright `a student drags the end of a booking in progress…` and `a Manager approves an extension request on the Lab overview` |

## 34. GitLab CI (2026-11-09, no website change)

Continuous integration only; no automatic deployment (see the section with the same name in CHANGELOG for the reason).

| Job | Image | Runs | Not included |
| --- | --- | --- | --- |
| `backend-tests` | `python:3.12-slim` | Install `backend/requirements-postgres.txt`; run `python manage.py test booking` (memory storage; PostgreSQL cases skip automatically) | PostgreSQL integration tests (see next row) |
| `postgres-tests` (2026-11-12) | `python:3.12-slim` + `postgres:16-alpine` service | Run `python manage.py test booking.tests.test_postgres` against the temporary database provided by the job | Old/new database structure comparison (`pg_dump --schema-only`) |
| `frontend-checks` | `node:22-alpine` | `npm ci`, `npm test`, `npm run lint`, and `npm run build` | Playwright e2e (see next row) |
| `e2e-tests` (2026-11-12) | `mcr.microsoft.com/playwright:v1.64.0-noble` | `npm ci` and `npx playwright test`; retain `frontend/test-results/` for one week on failure | — |

When upgrading `@playwright/test`, update the image version for `e2e-tests` at the same time.

Configuration is in `.gitlab-ci.yml` at the repository root. Results appear under Build → Pipelines in GitLab and on each MR page.

## 35. Lab Overview and Long-Form Dialog (2026-11-09, frontend only, API unchanged)

Loy feedback: `claude/reports/2026-11-09-loy-feedback-lab-rules-overview.md`.

| Area | Files and entry points | Tests |
| --- | --- | --- |
| Lab overview | `features/manager/ManagerHomePage.tsx` (`mh-chips` one-line labels, `SplitBar`, and this week's `mh-usage` bars); `segments` and `busiest` in `manager-home.ts`; `.mh-*` section in `ui/workspace.css` | Two 2026-11-09 cases in `tests/roles.test.mjs`; Playwright `the Lab overview shows waiting counts as chips and this week as bars` (screenshots `output/manager-ui-2026-11-09/lab-overview-*.png`) |
| Long-form dialog | `DialogTitle` in `ui/components.tsx` (adds × to title); `.ui-dialog-form` (960px, fixed title and buttons), `.mr-columns`, and `.mr-two-columns` in `ui/ui.css`; two-column `ResourceDialog` with Booking rules group in `ManagerResourcesPage.tsx`; `LabSetupPage.tsx` and `ManagerUsersPage.tsx` use `DialogTitle` | Playwright `the resource form opens wide in two columns and closes with the close button` (screenshots `resource-dialog-*.png`); existing `a Manager adds equipment…` continues to pass |
