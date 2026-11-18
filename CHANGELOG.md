# Changelog

This file records what changed in each update and why. Other documents describe only the current rules. Version numbers refer to the API version in `backend/docs/openapi.json`, and migrations refer to scripts in `backend/database/migrations/`. The newest entries appear first.

## 1.29.0: Storage Interface in Its Own File; Two Unused Endpoints Removed (2026-11-17, no migration)

- **Storage interface apart from the in-memory implementation.** `booking/repository.py` now holds only the `Repository` interface, the list of reads and writes the booking rules need and the part a new storage adapter implements. The in-memory implementation used by tests and the local demo moved to the new `booking/memory.py` unchanged, with its two filter helpers. The setting value is now `REPOSITORY_FACTORY=booking.memory.MemoryRepository` (still the default; `.env.example`, `backend/README.md`, `ARCHITECTURE.md` and `docs/database-interface.md` updated). Deployment uses `booking.postgres.PostgresRepository` and is unaffected.
- **API 1.29.0: two endpoints the website never called are removed.** `POST admin/users/managers/` duplicated Add staff with the Manager role (`POST admin/users/staff/`). `GET / PATCH admin/resources/{id}/booking-policy/` duplicated the `pending_hold_minutes` field of Resource setup (`PATCH admin/resources/{id}/`). Removed with them: the two views, `BookingPolicySerializer`, the service method `set_booking_policy` and its audit action `RESOURCE_BOOKING_POLICY_UPDATED` (a change to the review window is now always recorded as `RESOURCE_UPDATED`; old audit rows keep the old name). `ManagerCreateSerializer` is folded into `StaffCreateSerializer`. The `create_manager` command is unchanged. Tests that used the removed endpoints now use the remaining ones.

## After 1.28.0: Two Rules Written Down: Extensions and Equipment Return (2026-11-18, documentation only)

- Extending a booking in progress has never counted towards the 12-hour weekly limit, but no document said so. The product owner confirmed that this is the rule: an extension always needs a Manager's approval, and the Manager decides whether the extra time is reasonable. `backend/README.md` now states it next to the weekly limit. No code changed.
- `backend/README.md` listed equipment collection and return as not implemented. It is a decision, not a gap: picking up and returning an item happens in the lab and is left to trust, in line with the client's wish (Week 8 meeting) not to rely on penalties, and a "returned" button could not prove that an item came back. The README now says so in its own line.

## After 1.28.0: `authentication.py` Explains Itself (2026-11-17, comments only)

- `backend/booking/authentication.py` had one line of explanation for 80 lines of code. Its module docstring now says what the file does, why no role from the user is trusted, and the three steps for connecting real university SSO; each class and function has a one-line docstring. No code changed.

## After 1.28.0: Booking Limits Are Configured in Hours (2026-11-17, API unchanged)

- The two fair-use limits were set as numbers of 30-minute slots (`MAX_SLOTS_PER_BOOKING=6`, `MAX_SLOTS_PER_WEEK=24`), which had to be multiplied out to read as 3 h and 12 h. They are now `MAX_HOURS_PER_BOOKING=3` and `MAX_HOURS_PER_WEEK=12`. `BOOKING_SLOT_MINUTES` stays as the step in which hours are counted; `SettingsRulesProvider` (`booking/rules.py`) converts each hour limit into that many steps and refuses a value that is not a whole number of steps. The rule checks, API fields and defaults are unchanged.
- **Deployment note:** the old names are no longer read. A `.env.docker` that sets `MAX_SLOTS_PER_BOOKING` or `MAX_SLOTS_PER_WEEK` to something other than 6 and 24 must set the hour values instead; with the old defaults nothing changes. `docker-compose.yml`, `.env.docker.example`, `backend/.env.example` and the rule table in `backend/README.md` use the new names. Test: `test_booking_window.py` `test_hour_limits_from_settings_become_counting_steps`.

## After 1.28.0: Running Migration 005 Again Keeps Changed Staff Passwords (2026-11-17, no new migration)

- `005_resource_category_demo_password.sql` set the two demo staff accounts (z9000001, z9000002) to the demo password every time it ran, so running the whole set of migrations again, as `backend/database/README.md` recommends, undid a password that had been changed. It now replaces only the earlier demo password from 003. A database upgraded from before 005 ends up the same as before; a database where the password was changed keeps it. Checked in a temporary database: before the change a changed password was reset, after it the password is kept on the first and the second run.
- `backend/database/README.md`, `DEPLOY.md` and the comment in `backend/entrypoint.sh` no longer warn against running 005 again. The README now names the one change a repeated run still makes (001 moves a 30-minute review deadline to 1440 minutes).

## After 1.28.0: Backend Top-Level Clean-up (2026-11-16, no behaviour change)

First pass of a file-by-file review of `backend/`, for a teammate to check.

- Delete `backend/demo.http`: hand-written sample requests from Sprint 1 with dates that have passed. `backend/docs/openapi.json` is the complete API definition.
- Delete `backend/requirements.txt`: a second, unpinned copy of the dependency list used only by the local setup instructions. Local setup now installs `requirements-lock.txt`, the pinned list that Docker already uses (`README.md`, `backend/README.md`). `requirements-postgres.txt` (pinned list plus the PostgreSQL driver) is unchanged.
- Update two stale “Sprint 1” descriptions (`requirements-lock.txt`, `booking/__init__.py`).
- Delete three service methods that nothing calls, tests included: `_require_eligible` (`checks.py`; callers use `_qualification_violation`), `require_student` (`base.py`; replaced by `require_booking_user` when staff were allowed to book) and `set_pending_hold_minutes` (`resources.py`; a one-line alias of `set_booking_policy`).
- Delete `PrerequisiteSerializer` (`serializers.py`), which was defined and imported but never used, and an unused import of `booking_rules_bypassed` in `views/_common.py`.
- Remove three unused imports from the tests (`test_long_bookings.py`, `test_test_console.py`, `test_user_management.py`).
- Delete the management command `process_outlook`: `process_due --outlook-limit N` already pushes the due Outlook updates, and the Docker `scheduler` runs it every minute. The test that a separate worker refuses the in-memory repository now calls `process_due` (`test_outlook.py`); `backend/README.md`, `backend/docs/outlook-setup.md` and `ARCHITECTURE.md` no longer mention the command.
- Frontend `src/`, top level: delete `src/assets/` (three images from the Vite template that nothing references; the site's images are in `frontend/public/`), `features/booking/Layout.tsx` (the Sprint 1 shell, replaced by `app/AppLayout.tsx` and imported nowhere) and `features/manager/ManagerUsagePage.tsx` (replaced by `features/records/UsageTab.tsx` in 1.14.0 and imported nowhere). `features/manager/usage.ts` stays: `UsageTab.tsx` uses it.
- `backend/database/` and `backend/docs/`, documents only (2026-11-17): `backend/database/README.md` loses five “upgrade an existing database for …” subsections that repeated the migration table above them, two leftover notes about an earlier iteration not being deployed, and the line calling the PostgreSQL adapter local-only (the Docker deployment uses it); it now says exactly what running every migration again changes. `database-interface.md` said scripts 001–011 are repeatable; all of them are. `email-setup.md` no longer names one person's computer in a heading. Documents and the CI file describe checks by what they do instead of naming helper scripts that are not in this repository.

## After 1.28.0: Two Small Interface Fixes (2026-11-16, frontend only)

From the user-perspective walkthrough (`claude/reports/2026-11-10-user-perspective-audit.md`, U7 and U9).

- **No urgent-request entry when nothing can be requested.** A student without the induction for a resource (or looking at a closed resource) saw the “Urgent request” checkbox and the “Make an urgent request” button, although neither could lead to a request. Both are now hidden in that case (`BookingForm.tsx`, `SlotPicker.tsx`).
- **Calendar sync page speaks to Admins.** With synchronisation off, the page said “Set OUTLOOK_ENABLED=true on the server”. It now says that approved bookings are not written to Outlook on this site and that people can still subscribe from My bookings; “Check connection” is disabled together with “Sync now” (`calendar-sync.ts`, `CalendarSyncPage.tsx`).

## After 1.28.0: README Sections for Docker and Testing (2026-11-16, documentation only)

- `README.md` gains “Run with Docker” (copy `.env.docker.example`, one `docker compose` command, `http://localhost`) and “Testing approach and coverage” (what each test layer covers, the counts, backend line coverage of 94.8%, how races and external services are tested, and what is checked by hand). The old “Tests” section is folded into the latter.

## 1.28.0: The Author Can Delete an Ended Announcement (2026-11-16, no migration)

Based on Loy's feedback in `claude/reports/2026-11-16-announcement-delete-feedback.md`: whoever posted an announcement can delete it from the history.

- New `DELETE announcements/{id}/`. Only the person who posted the announcement may call it, for manual and resource-status announcements alike; a Manager who is not the author receives 403. The announcement must have ended (removed or expired); one still shown on the home pages returns 409 `ANNOUNCEMENT_ACTIVE` and has to be removed first. The row is deleted permanently; the audit log keeps `ANNOUNCEMENT_DELETED` with the title (`services/announcements.py`, `views/announcements.py`).
- The repository interface gains `delete_announcement(announcement_id)`, implemented by the in-memory and PostgreSQL adapters. No schema change.
- Announcements page: an ended announcement shows **Delete** to its author, with a confirmation that it cannot be undone (`AnnouncementsPage.tsx`).
- Tests: service and HTTP permission cases in `test_119.py` (run against both adapters), one browser case in `routing.spec.ts`.

## After 1.27.0: Book a Resource Layout (2026-11-16, frontend only)

Based on Loy's feedback in `claude/reports/2026-11-16-book-page-layout-feedback.md`.

- **No induction list at the top of Book a resource.** The “Training requirements” row grew with every new induction and room and pushed the page layout around. It is removed. On each resource card, the induction chip (“Induction not submitted”, “rejected”, “expired”, or “… needed first”) is now a link to the Induction page for the evidence still to submit (`BookingApp.tsx`, `ResourceCard.tsx`). This replaces R2 below.
- **Urgent request: the explanation is below the time picker.** Ticking “Urgent request” used to show “Purpose and urgency” above the time picker, while the normal “Purpose” is below it. Both now sit in the same place; the note about Manager approval stays under the checkbox (`BookingForm.tsx`).

## After 1.27.0: Add PostgreSQL and Browser Tests to CI (2026-11-12, no website change)

- Add two jobs to `.gitlab-ci.yml`: `postgres-tests` (PostgreSQL integration tests against the temporary database provided by the job) and `e2e-tests` (Playwright). These tests previously ran only locally, so nothing blocked changes merged directly into `main`. Automatic deployment is still disabled.

## After 1.27.0: Withdraw a Time-Change Request When Its Original Booking Is Cancelled (2026-11-12, backend only, API unchanged)

Based on Item 1 of `claude/reports/2026-11-12-delivery-acceptance.md`, decided by Loy on 2026-11-12.

- Previously, cancelling a booking with a pending time-change request left the request active. It could later be approved, giving the student a booking they believed they had cancelled. Now, when the booking holder or staff cancels the original booking, any pending time-change request is also cancelled with the same reason and its held time is released immediately (`cancel_booking` in `bookings.py`).

## After 1.27.0: Do Not Leave Stale State After a Successful Action Followed by a Failed Refresh (2026-11-12, frontend only)

Based on Items 2 and 3 of `claude/reports/2026-11-12-delivery-acceptance.md`.

- **Booking review**: after a successful approval or rejection, remove the row immediately instead of waiting for a refresh. If the refresh fails, show “Showing the previous results.” (`BookingReviewPage.tsx`).
- **My bookings**: after a successful time change, cancellation, extension, or check-in, update the card directly with the endpoint response. If the refresh fails, retain the filters and existing cards and state that the displayed data is stale (`MyBookings.tsx`, `ChangeTimeBox.tsx`).

## After 1.27.0: Lab Overview Review Fixes (2026-11-12, frontend only)

- Load tasks, resource status, and the weekly report independently, with an inline retry after failure. After an extension is reviewed, update the task list immediately and show confirmation. Fix the extension-request link and keyboard focus for zID errors, and allow long resource names to wrap on phones.

## After 1.27.0: Time Selection and Change-Request Quota Fixes (2026-11-12, API unchanged)

- **Old time remained submittable when a changed Length or Start no longer fit** (BB feedback, `claude/reports/2026-11-12-bb-length-past-closing.md`): when a selection from the dropdown or timeline is rejected, clear the previous selection and disable the submit button (`SlotPicker.tsx`).
- **Dropdowns no longer jump after rejection**: Start and Length continue to display the time described by the red error. Choosing a Length that fits selects it directly without requiring Start to be selected again.
- **Timeline and Length stay synchronised**: after selecting a length from the dropdown, clicking the timeline updates Length to match the timeline selection.
- **Weekly quota does not double-count a pending change request**: if the original booking has not started, the original booking and change request in the same week count only the longer of the two. If they are in different weeks, each counts in its own week. After the original booking starts, the two count separately. The quota is rechecked during approval, automatic approval, and waitlist promotion (`checks.py`; see `backend/README.md` for details).

## After 1.27.0: Translate Code Comments into English (2026-11-12)

- Translate Chinese comments in the backend qualification-validity setting and EC2 load-test scripts into English.

## After 1.27.0: Six Changes from a User-Perspective Walkthrough (2026-11-10, one API field added, version unchanged)

Based on U1–U6 in Section 1 of `claude/reports/2026-11-10-user-perspective-audit.md`.

- **U1**: below the date, the booking window says “Week of 16 Nov: 2 h left of your 12 h.”, showing the remaining quota for the selected date's week. Add `week_hours` to an individual resource's `availability` response (field addition only). Home-page cards are unchanged.
- **U2**: the bell icon and badge both used numeric React key 1, causing two bells to overlap when they appeared together. Add distinct prefixes (`ring-` and `badge-`).
- **U3**: when a student is deactivated, reject pending requests and also cancel approved bookings that have not started (treated as a staff cancellation, with a notification to the student and the time released). Reactivation does not restore them.
- **U4**: a deactivated student who signs in sees “This account has been deactivated. Contact the lab.” (403 `ACCOUNT_DEACTIVATED`) instead of being sent to create an account.
- **U5**: increase sign-in validity from one hour to eight hours (`DEMO_TOKEN_TTL_SECONDS`).
- **U6**: add a Booking rules section to the student's Help page and remove “Refresh the page to see the latest status.” The 7–28 days, 3 h, and 12 h in the guidance are defaults in `frontend/src/app/booking-rules.ts`; they do not update automatically when a Manager changes the limits.

## After 1.27.0: Lab Overview and Long-Form Dialogs (2026-11-09, frontend only, API unchanged)

Based on Loy's feedback in `claude/reports/2026-11-09-loy-feedback-lab-rules-overview.md`: the Lab overview was “too ugly,” and the resource-edit dialog was “one long vertical list” without a close button.

- **Lab overview** (`ManagerHomePage.tsx`): replace five large cards with one row of small labels for the four request types decided only by Managers and the Admin task list. When all are zero, show “Nothing is waiting for your decision.” Replace room/equipment open/maintenance/closed data and this week's check-in/absence/excused data with segmented bars and legends. Show the six most-booked resources this week as horizontal bars. Data is unchanged and there is no new endpoint.
- **Long-form dialogs**: widen resource editing and Lab setup induction editing dialogs to 960px. Split the resource form into two columns (resource information | Booking rules, Details | Managers only), arrange the four induction guidance fields two per row, and return to one column on phones. Keep the title and bottom Cancel/Save buttons visible while the middle content scrolls.
- **Close button**: add × beside the title (`DialogTitle`) in these two dialogs and the Add staff dialog. Esc still closes them.

## After 1.27.0: GitLab CI (2026-11-09, no website change)

Based on the Week 9 course teamwork assessment requirement to demonstrate engineering practice (CI/CD).

- **Add `.gitlab-ci.yml`**: run two jobs on every push and MR: `backend-tests` (`python:3.12-slim`, `manage.py test booking`, memory storage) and `frontend-checks` (`node:22-alpine`, `npm test`, `npm run lint`, and `npm run build`). Images and dependency installation match the two Dockerfiles. The pipeline first passed on the university GitLab on 2026-11-09.
- **No automatic deployment**: deployment stays manual, a dry run followed by manual confirmation (Section 3 of `DEPLOY.md`), because some migrations delete data (such as 014), and automatic deployment would require storing the server SSH key in GitLab.
- PostgreSQL integration tests and Playwright e2e are not included in CI and continue to run locally.

## After 1.27.0: Five Changes from the Three-Role Walkthrough (2026-11-07, frontend only, API unchanged)

Based on Loy's walkthrough in `claude/reports/2026-11-07-three-role-walkthrough.md`.

- **Automatic page refresh**: Today, Lab overview, My bookings, and Dashboard reread data every 30 seconds and when the user returns to the browser tab (`lib/use-auto-refresh.ts`). An Admin can see a student's submission without pressing F5, and the student can see the Admin's approval.
- **Correct reviewer wording**: urgent, additional-hours, and long-booking requests show “Waiting for Manager approval” in My bookings, Dashboard, and Booking review (`statusText` in `format.ts`). Urgent requests previously said admin.
- **Manager resource cards**: show “Manager booking: no induction needed” and the resource's own maximum duration instead of prompting for induction and saying the limit is three hours.
- **Additional-hours entry point**: Request additional hours on Dashboard opens `/resources?for=additional-hours`; the primary button on each card directly opens an additional-hours request.
- **Extension-request card**: links to `/manager/home?focus=extensions`, and the page scrolls to the review list, including on phones.

## 1.27.0: Extension Changed to Timeline Dragging and Manager Approval (2026-11-07, migration 016)

- Decided by Loy on 2026-11-07 according to the original intent of meeting 14:11–15:53: a student drags the booking end time on a timeline (like dragging in a calendar) to submit an extension request for Manager approval; it no longer takes effect immediately. A Manager extending their own booking still applies immediately.
- Store the request in `extension_end` on the booking (migration 016); a new request replaces the existing one. At request and approval time, check that later time is free, within opening hours, and within the resource's maximum duration. The later time is not held while the request is pending.
- A Manager approves or rejects in Extension requests on Lab overview (a rejection requires a reason). Today and Lab overview have Extension requests cards. Both parties receive notifications, and approvals and rejections are also emailed. New endpoint: `POST bookings/{id}/extend/review/`.
- Replace the 1.24.0 dropdown with a draggable, arrow-key-accessible timeline. Student extensions are no longer subject to the three-hour per-booking limit or weekly-hours limit because the Manager decides.
- Week 8 follow-up: retain extension requests in the pending list until the requested new end time, and make rejection decide the currently replaced time. Fix dates/durations for Manager availability and recurring bookings, retry after saving internal equipment information fails, and recovery guidance and flow after deployment fails following migration 014.

## 1.26.0: Clear Differences Between the Three Roles (2026-11-07, migration 015)

Based on the client Week 8 meeting (02:33–04:48 and 19:49–20:56: dashboards may look similar, but data access must differ completely; Admin does not need all history, while Manager does). Task card W5–W7 in `tasks-week8-2026-11-06.md`.

- **W5 Manager home page**: after signing in, a Manager lands on Lab overview (`/manager/home`), which shows decisions only Managers can make, room and equipment status, this week's usage, one-year zID history lookup, and lab-management links. Admin Today retains only approval work and no longer displays the three Manager cards for urgent, additional-hours, and long-booking requests. The top of each page shows a Student/Admin/Manager view badge.
- **W6 Admin sees only recent history**: Booking Records and CSV return only bookings that ended within the last seven days or later for Admin. The usage report becomes Manager-only.
- **W7 Manager-only equipment information**: person responsible, UNSW asset number, source, and specifications. Stored in separate table `resource_internal_info` (migration 015), edited by a Manager in the Resources dialog, through `GET/PATCH admin/resources/{id}/internal/`. Normal resource data does not contain these fields.

## 1.25.0: Remove Freezing (2026-11-07, migration 014)

- Loy, 2026-11-07: the client did not want an absence penalty at the Week 8 meeting, so the 1.24.0 “disabled by default” policy was changed to complete removal.
- Remove: freezing after N absences, cancellation of later bookings during freezing, unfreeze requests and the Booking freezes page, five endpoints, user fields `no_show_count`/`frozen_until`/`booking_frozen`, and configuration `FREEZE_AFTER_NO_SHOWS`/`FREEZE_DAYS`.
- Retain: check-in (I'm here), the absence marker on each booking, and the usage report. When a user is absent, notify them to cancel in future if they cannot attend. Bookings cancelled by freezing in old data continue to show their reason.
- Migration 014 drops table `unfreeze_request` and two columns, deleting that data. Before rolling back to old code, rerun 006 (see `DEPLOY.md`).

## 1.24.0: Three Items from the Client Week 8 Meeting (2026-11-06, no migration)

Source: client meeting on 11-04 (project document `reports/2026-11-04-client-meeting-week8.md`). Task card `tasks-week8-2026-11-06.md`.

- **Manager can override rules** (meeting 00:41–02:28 and 07:15–08:42): a booking made by a Manager for themselves or on behalf of someone else is approved directly without checking induction, the 7–28-day window, three-hour booking limit, 12-hour weekly limit, eight-future-booking limit, or freezing. The resource must still be bookable and free, within opening hours, and within its own maximum duration; other users are never displaced. A Manager's reschedule also skips induction and these limits. This reverses the 10-17 decision that induction could not be bypassed. Admin is unchanged.
- **Extend an in-progress booking** (14:19–15:53): new endpoint `POST bookings/{id}/extend/`; Extend buttons in My bookings and Manager Room bookings. It takes effect immediately if later time is free, and the Manager is notified. A student asks a Manager to extend beyond three hours or the weekly quota.
- **Freezing disabled by default** (15:56–17:27): the client did not want penalties in the first phase. Change the default `FREEZE_AFTER_NO_SHOWS` to 0 (no freezing); absences are still recorded, and the notification reminds users to cancel promptly. The feature remains and is restored by setting a positive value.
- Per-lab rule configuration (Item 1 of the meeting) was not implemented in this update. The proposal and questions for the client are in the task card.

## 1.23.0: Dashboard Shows Hours Remaining This Week (2026-11-03)

- Loy, 2026-11-03: students could not see how many hours they could still book that week and learned only after an over-limit request was rejected. Add a fourth “Hours left this week” card to the student Dashboard, showing remaining hours and “x booked / 12 h.” Selecting it opens Book a resource and explains that additional hours may be requested. Do not add a separate display for the eight-future-booking limit: Upcoming bookings plus Pending requests already equals that count.
- Endpoint: add `week_hours` (`week_start`, `used_hours`, and `limit_hours`) to `GET dashboard/`, calculated for the current Sydney-time week through the same `_week_slots_used` function as the weekly limit. Additional-hours bookings do not count.

## After 1.22.0: Limits Configurable on the Server (2026-11-03, API unchanged)

- The client's 11-02 email required values such as three hours and 12 hours to be easy to change. Add `BOOKING_SLOT_MINUTES`, `MAX_SLOTS_PER_BOOKING`, `MAX_SLOTS_PER_WEEK`, and `MAX_ACTIVE_FUTURE_BOOKINGS` to `docker-compose.yml` and `.env.docker.example`. Previously, the containers did not receive these variables, so server changes had no effect.
- Find a free time duration options now follow the resource's `effective_max_booking_minutes` instead of being hard-coded to three hours.

## 1.22.0: Long-Booking Requests (migration 013)

- Add a separate long-booking request form and API that relaxes only the normal per-booking duration limit. Weekly hours, future-booking count, normal advance window, and the resource's own limits remain enforced by the backend. Staff proxy bookings follow the same limits. Long bookings cannot be combined with additional-hours, urgent, or recurring bookings.
- Long requests retain time holds and the first-in, first-out waitlist. Only a Manager may manually approve or reject them, and self-review or review of a request created by the reviewer is forbidden. An unreviewed request expires at its review deadline and releases the time; it is never auto-approved. Approval rechecks the deadline, qualification, quotas, and capacity inside the lock.
- Add a dedicated review tab, task count, request reason, and deadline wording. An approved exemption applies only to the original time, so the normal reschedule path cannot transfer it. Migration 013 runs after 012 and preserves historical bookings. API version becomes 1.22.0.

## 1.21.0: Additional-Hours Requests (migration 012)

- Add a separate entry point and API for additional-hours requests, recording the reason, data-collection declaration, and explanation. A request does not reserve the resource and does not consume the normal weekly quota, but still counts toward future bookings. Per-booking duration, opening hours, qualification, and maximum advance window remain enforced.
- A Manager may approve only within a configurable period before the booking starts (48 hours by default) and may not review their own request or one they created. Approval rechecks free capacity inside the transaction. Requests from users with no checked-in usage that week and requests for active data collection share the priority group; requests within the group are first-come, first-served. The Manager must explicitly confirm a data-collection declaration, and the approval basis and authorised time are audited.
- Pending requests are never auto-approved and expire if unreviewed at their start time. Additional authorisation is fixed to the requested time; rescheduling requires cancellation and a new request. The frontend adds a separate review tab, approval time, priority basis, blocking reason, and task count.
- Add repeatable migration 012 while preserving existing booking records. API version becomes 1.21.0. The review list reuses qualification and queue calculations within one response; actual approval always revalidates.

## After 1.20.0: Book at Most Four Weeks in Advance (2026-11-02)

- At the client's request, change the default maximum advance booking window from 30 days to 28 days (four weeks), calculated using the resource's local date. Day 28 is bookable; day 29 onward is not. Retain the existing minimum seven-day advance rule; both values remain configurable.
- Check every date in a staff recurring series against the same booking window. Preview marks out-of-range dates, and creation cannot retain them. Staff proxy bookings and Manager rescheduling continue to follow the maximum advance limit.
- The recurring-booking form reads the backend date range, so its date picker and default range follow the configuration. Docker API and scheduler share the booking-window environment variables. Update the current API and usage documentation.

## After 1.20.0: Three Performance Rounds and Merge-Review Fixes (2026-11-01)

- Fix duplicate concurrent reminders: retain the batch deduplication query from the three performance rounds, then recheck the recipient and booking/induction link inside `_notify`'s write lock before sending. Notifications and email queue records are still written in the same transaction. Both Memory and PostgreSQL have concurrency regression tests; before the fix each created two notifications and two email records, and after the fix each creates one.
- When rerunning 011, support the automatically generated foreign-key name from the original migration, then rename it to `email_delivery_notification_fk` to match `schema.sql` while preserving the foreign key and existing emails. Add an old-database record-preservation test and verify identical structures through both the 010 and original-011 upgrade paths.
- Add PostgreSQL tests for email-background-thread disconnection, expired-connection recovery, and isolation from the main-thread transaction. Complete cross-repository boundary comparisons for submission filters and isolate the global email queue in PostgreSQL tests.

## After 1.20.0: Merge `main` Background Scheduling and Reliable Email Delivery (2026-11-01, migration 011)

Merge two features that Alaric Nan had merged into `main` (`13bac3d` background scheduler and `a39bf59` reliable email delivery and retry) into `backend/week5-fixes`. Conflicts occurred only in `postgres.py`, `repository.py`, and `test_postgres.py`; both sides contained separate additions, so both were retained. Three defects were fixed during the merge:

- **No recovery after disconnection**: Django cleans invalid database connections only before and after web requests. `run_scheduler` and the background email thread have no requests, so after a database restart they kept failing until the container restarted. Each round now begins with `close_old_connections()`. New test `test_scheduler_recovers_when_the_database_connection_is_lost` disconnects a real connection; before the fix only the first round succeeded.
- **Migration not repeatable**: after 011 adds its foreign key, rerunning 006 failed when it attempted to drop `notification_pkey`. Migration 006 now adds the primary key only when it does not exist.
- **New and upgraded database structures differ**: the foreign key in 011 was unnamed and differed from `email_delivery_notification_fk` in `schema.sql`. Migration 011 now names it explicitly. Databases that already ran the old 011 retain the auto-generated name without affecting behaviour.

## After 1.20.0: Add Load-Test Scripts to the Repository (2026-11-01, no website change)

At Loy's request, add the load tests to Git under new directory `load-test/` (see its README for instructions and the three rounds of results). The scripts previously existed only on team members' machines. The server address is not committed and is supplied at runtime through `EC2_HOST`. Also fix `report.py`, which incorrectly marked a `-history-worktree` directory as “without historical data.”

## After 1.20.0: Load-Test Performance Fixes, Round Three (2026-10-29, API and schema unchanged)

S7 and S8 from task card `claude/tasks-load-2026-10-29.md` (new findings after the second load-test round; Loy decided to run a third round). Rules and returned data are unchanged.

- **S7**: Find a free time no longer separately queries the person's induction records, freezing state, existing requests, and daily occupancy for each resource. Read them once and share across resources (`EligibilitySources`, `_DaySources`). Induction evaluation, including prerequisites, uses the same code with a different data source. Previously, 22 resources required about 130 SQL statements.
- **S8**: induction-expiry reminders no longer read every induction submission on every request. First query whether any verified submissions expire within the reminder period (normally none, requiring one query). If any exist, read only those users' submissions to determine the latest one, and fetch already-sent reminders in one query. Add keyword filters to `list_submissions`, add `list_kind_notifications`, and remove unused `_already_sent`.
- Tests: add two tests to `test_postgres.py` (adding five resources does not increase Find a free time query count and each resource's result matches an individual query, including missing prerequisites; 30 inductions that are not near expiry are not read, and the latest submission determines whether to remind). Both fail on `b5964d7`.

## After 1.20.0: Load-Test Performance Fixes, Round Two (2026-10-29, API and schema unchanged)

S2 and S6 from task card `claude/tasks-load-2026-10-29.md` (S6 was discovered during the first round and Loy added it to this round). Returned data is unchanged.

- **S2**: Booking Records and the review queue no longer query the database per row. Previously, every booking separately loaded the booking holder, creator, replaced booking, change request, and waitlist position, producing more than 9,000 SQL statements for 5,000 bookings. `BookingListLookups` now loads them together (there are few undecided bookings, loaded once). `booking_json` is shared between individual bookings and long staff lists with identical output. Status, resource, student, and date filters for `booking_report` are also executed by the database. With 5,000 historical bookings, Booking Records improves from 9.1 seconds to about 1 second, and the review queue from 1.2 seconds to 81 ms.
- **S6**: availability (Find a free time and an individual resource's day view) queries each resource's daily occupancy once, then evaluates each cell. Previously every half-hour cell queried separately, resulting in more than 500 SQL statements for one request across 22 resources.
- Tests: add three tests to `test_postgres.py` (availability query count does not grow with the number of cells; a shared-query staff list matches per-row output with Outlook both on and off; adding 40 Booking Records entries does not change the SQL count). All fail on `ec5c4b1`.

## After 1.20.0: Show Submission Failure Inside the Booking Dialog (2026-10-29, frontend only)

Based on Loy's screenshot feedback in `claude/reports/2026-10-29-weekly-limit-dialog.md`: after reaching the weekly limit, the error appeared only in the message box behind the dialog, while the dialog itself showed nothing. Reloading the day's times and clearing the selection after a failed submission also cleared the form error, and the message box was hidden beneath the native `<dialog>` backdrop. Reloading no longer clears the error. It appears beside the submit button as `Request not submitted: …` until the user selects a new time. Add e2e test `a refused booking request is explained inside the booking dialog`.

## After 1.20.0: Load-Test Performance Fixes, Round One (2026-10-29, API and schema unchanged)

Based on load test `claude/reports/2026-10-29-stress-test.md` (200 students + 10 Admins + 2 Managers failed because every request loaded all bookings into memory) and R1, S1, S5, and S3 in task card `claude/tasks-load-2026-10-29.md`. Business rules and returned data are unchanged.

- **R1**: add keyword filters to `list_bookings` (status, start/end time, expiry, creator, and attendance not recorded). PostgreSQL filters in SQL; the memory implementation uses the same `booking_matches`. Filters only narrow reads, preserving all caller-side checks. Add `list_booking_notifications` to perform reminder deduplication in one query.
- **S1**: expiry processing, absence marking, and tomorrow's reminders read only bookings that may require processing (undecided and expired; approved, attendance not recorded, and started; approved, attendance not recorded, and within the reminder period). They no longer read all bookings three times on every request. This was the previous P6 issue.
- **S5**: the Admin home page reads only undecided bookings, approved bookings that have not ended, and today's bookings. Staff My bookings queries by creator instead of reading all bookings to find “created by me for someone else.”
- **S3**: reuse database connections for 60 seconds within a process (`DB_CONN_MAX_AGE`; set to 0 to disable) instead of creating one per request (about 12 ms). Write locks are transaction-scoped, so connection reuse does not carry a lock into the next request.
- Tests: add four tests to `test_postgres.py` (both implementations return identical filtered results; expiry processing and one staff page read no rows among 200 historical bookings; query count is identical for one and 20 already-reminded bookings; connection reuse). All fail on `3377dd1`.

## After 1.20.0: Live Trial Feedback L1–L5 (2026-10-28, API unchanged)

Based on Loy's post-deployment trial feedback in `claude/reports/2026-10-28-live-feedback.md`. Frontend only.

- L1: when a staff account is used on the university sign-in page, make “Staff sign-in page” in the message a link directly to staff sign-in.
- L2: Today task cards use exactly three columns per row on desktop and no longer stretch a single card across the row. A sole “Decide soon” or “Out of service” card spans the row. The green tick on the right appears only when nothing is pending review.
- L3: move Edit/Remove on announcement cards to the top-right. True deletion and a collapsed seven-day section are not implemented and remain proposals for the client.
- L4: make “SmartLab” in the sign-in breadcrumb a link back to the sign-in home page, so staff sign-in is no longer a dead end.
- L5: add a red line to the top of Urgent cards on Today and make the number red, distinguishing them from normal yellow task cards.
- Also remove dead rule `.today-brief p`; the page no longer contains that element.

## 1.20.0: Booking Filters, Personal History, and Home Page (2026-10-28, migration 010)

Based on Loy's analysis of the eDoc and subsequent authorisation to “go ahead and change it,” task card `claude/tasks-booking-history-2026-10-28.md`.

- Under existing My bookings categories, add a Resource filter, match count, and Clear filters. The URL remembers both category and resource; changing local filters does not refetch bookings.
- Students, Admins, and Managers can remove their own ended/cancelled/rejected/expired history one item at a time; recurring bookings are handled by date. The server stores hidden records per user, independently for both parties in a proxy booking. The source booking, staff reports, absences, notifications, and calendar remain. Active future or in-progress bookings must first be cancelled or withdrawn.
- Give the student Dashboard separate statistics cards, make Next session smaller, and place later bookings beside it. Reduce the status banner on staff Today. Preserve announcements, training, review, and maintenance information; do not add charts or date filters.

## Maintenance Flow Card A (2026-10-28, API remains 1.19.0)

Based on project task card `claude/tasks-maintenance-2026-10-27.md` (on 2026-10-27 Loy decided B1 should show only the total and narrowed Card A to the smallest frontend-only version). Sources: Codex maintenance-flow review M1, B1, and V3, plus Claude Code's follow-up review.

- **M1①**: Room management no longer retrieves every historical approved booking. It requests only unfinished bookings and requests (`status=APPROVED,PENDING_APPROVAL,WAITLISTED,WAITING_QUALIFICATION&since=<now>`, using existing endpoint parameters). With 5,000 synthetic local bookings, the post-save refresh improves from about 3.7 seconds to about 0.76 seconds (few bookings exist online, so no online measurement). Replace `listApprovedBookings` with `listUnfinishedBookings`.
- **B1**: maintenance, closure, and reopening dialogs show the total of approved bookings plus pending and waitlisted requests, matching the scope actually notified by the backend. Previously they counted only approved bookings and showed 0 when only requests existed. The booking table and Upcoming column continue to count only approved bookings. Dialog copy: `N upcoming bookings and requests affected.`
- **V3**: after a successful save, immediately update the row with the resource status returned by the endpoint, then refresh as before (reopening advances the waitlist). Disable resource status buttons until refresh completes to prevent another action against stale state from sending another notification round.
- Not implemented yet (Loy: the system is already somewhat bloated): M1② serialisation batch queries, M3, and M4. Details such as separate counts by type remain ideas to discuss with the client.
- Verification entry point: `frontend/tests/maintenance.spec.ts` (intercepts all APIs).

## Page Fluency Card B (2026-10-27, API remains 1.19.0)

Based on V2, V4, V5, V6, and V8 confirmed by Loy in project task card `claude/tasks-fluency-2026-10-27.md`. Frontend only; no API, backend, or maintenance business-flow change.

- **V2**: move the capacity filter and Equipment room dropdown to a separate row below resource tabs, leaving only tabs in the scroll area. At 320px and 390px, users no longer need to scroll horizontally to see the complete filters.
- **V4**: when Booking records criteria change, retain and fade old results, mark the table `aria-busy`, show `Updating…`, and temporarily disable Print/Export. On success, update the count, rows, and associated criteria. On failure, retain old results, show the error, and re-enable buttons. Export CSV using the criteria originally associated with the visible table to avoid mismatch.
- **V5**: student Dashboard and staff Today both wait for home data and announcement requests before showing first-screen content. If announcements fail, still show the home page and existing error/retry; leave no blank area when there are no announcements. Shared `useAnnouncements` manages the first announcement result, and retry does not unmount the existing home page. Waiting applies only to first display: later Refresh overview / Refresh now keeps announcements in place (review fix: student Dashboard previously collapsed announcements during refresh).
- **V6**: after the initial Room management load fails, stop showing Loading and provide `Try again` below the error. RefreshStamp, maintenance dialogs, and refresh behaviour on other pages are unchanged.
- **V8**: remove the decorative full-page fade-in and its unused keyframes while retaining control feedback and reduced-motion settings.
- Verification entry point: `frontend/tests/fluency.spec.ts` (intercepts all APIs; covers delay, failure, retry, filter-result/CSV consistency, initial announcement position, and reduced-motion). Pre-change failures and before/after screenshots are outside the project in `9900/output/fluency-2026-10-27/`; see the task card for acceptance results.

## Move Email to Background Delivery and Stop Per-Row Locking for Expiry Processing (2026-10-27, API remains 1.19.0)

Based on P1–P4 in `claude/tasks-performance-2026-10-27.md` (Loy said “start” on 2026-10-27). After email was enabled online, submitting a booking stalled for 2–3 seconds because email was sent synchronously before the response returned. Connecting, encrypting, and signing in to Gmail from EC2 took a median 1,875 ms (five connect-only trials), and every email opened a new connection.

- **P1 background delivery**: `EmailOutbox` in `booking/email_channel.py`. A request only enqueues the composed email; one background thread per backend process sends it, so the API response no longer waits for the mail server. Delivery failures remain log-only. Trade-off: if the process is killed forcibly, queued unsent emails are lost; a normal shutdown waits up to `EMAIL_TIMEOUT` seconds to finish. `manage.py process_due` waits up to 60 seconds for email before exiting.
- **P2 shared connection**: emails queued together (arriving within about 0.2 seconds) use one SMTP connection.
- **P3 delivery logs**: log connection time per batch; for each email log notification ID, recipient domain, queue time, and delivery time. Add `LOGGING` to `config/settings.py` to send `booking` INFO logs to the console (adjustable with `LOG_LEVEL`). Previously there was no logging configuration; Python showed only WARNING and above, so INFO-level “email skipped” messages were absent from server logs.
- **P4**: keep `EMAIL_TIMEOUT` at 10 seconds; `backend/docs/email-setup.md` documents its current purpose, log format, and limits.
- Local result (temporary PostgreSQL with 5,000 bookings; fake email backend simulating Gmail at 1.9 seconds to connect and 0.3 seconds per email): median booking submission falls from 2,729 ms to 491 ms; all five emails are sent using three connections instead of five. The remaining about 0.5 seconds is `process_due_requests` (see task card; unchanged in this round).
- About four minutes of email delivery delay is not caused by the application: message headers show the time is spent at UNSW (Proofpoint 2m30s, Microsoft 365 1m19s, `claude/reports/2026-10-27-email-headers.md`), so these changes do not make final delivery earlier.
- Tests: add four to `test_email_channel.py`, all failing before the change. Existing email tests now wait for background delivery before checking.
- **P5 evaluate before locking during expiry processing** (Loy said “start” on 2026-10-27): every API request runs `process_due_requests` (`services/waitlist.py`). Previously, it opened a transaction, locked, and reread every undecided request even when it was not due. With 200 local pending requests, every request ran about 1,200 extra SQL statements, added about 0.2 seconds, and locked those resource and student rows every time. It now checks loaded data first (`_due_for_processing`: start time passed or review deadline reached) and skips items not due; it rechecks after locking as before, so rules are unchanged. Locally, `process_due_requests` improves from 1,204 SQL / 521 ms to 4 SQL / 329 ms; endpoints improve from about 530 ms to about 335 ms. Test `test_requests_that_are_not_due_yet_are_not_locked` in `test_approval_flow.py` failed before the change (2 != 0).
- Remaining about 330 ms (local 5,000 bookings): `process_due_requests`, `_process_attendance`, and `_booking_reminders` each read **all** bookings on every request and filter in Python, about 110 ms each, growing linearly with historical bookings. Not changed in this round.

## Structure Cleanup S1 + S3 (2026-10-27, API remains 1.19.0)

Following Sections 4.3 and 4.4 of `reports/2026-10-27-code-structure-review.md`, make moves and deletions only, without changing behaviour: no API, database, booking-rule, UI-copy, or visual-style changes.

- **S1: remove 31 unused CSS class names**: 21 from `features/booking/booking.css`, 8 from `ui/workspace.css`, 3 from `app/shell.css`, and 2 from `features/auth/auth.css` (three class names had rules in two files). The review checklist originally listed 32; `ttf` was the font URL `manrope-regular.ttf` misidentified as a class, so no such class existed and nothing was removed for it. Before deletion, each class was searched in `.ts`, `.tsx`, and `.mjs` under `frontend/src` and `frontend/tests`; all appeared only in CSS. For selectors containing `:is()`, remove only the target member (for example, the mobile `.app-shell :is(.ui-tabs, .bk-pills, .bk-mode-tabs)` retains the first two).
- **S3: move the API layer to `src/api/`**: split `features/booking/api.ts` (73 functions) and `types.ts` (52 types) by domain into `src/api/{auth,bookings,resources,admin,notifications,announcements,site}.ts`, `src/api/client.ts`, and `src/api/types/<domain>.ts`, with unified exports from `src/api/index.ts` and `src/api/types/index.ts`. Function bodies and type definitions are unchanged. Delete old files without forwarders. Move locally defined `BookingRequest` to `types/bookings.ts`. Review found that the split attached 19 explanatory comments to the wrong declarations (for example, the `lookupPerson` explanation moved above `listBookings`); restore all to their original declarations (Claude Code, R1 in `claude/reports/2026-10-27-review-structure.md`).
- Change all consumers to import from `src/api` (`index.ts`). Node unit tests continue to use full `.ts` extensions, and types use `import type`.
- Evidence of unchanged behaviour: all local checks pass (backend 379, pg 26, OpenAPI 1.19.0 / 72 routes, unit 72, lint, build, e2e 75). Screenshot comparison: 22 pages × desktop 1440×900 / phone 390×844 = 44 images; every updated screenshot is pixel-identical to one pre-change (`8ae931f`) screenshot (five pages show tens to thousands of random pixel differences even between consecutive captures of the same version, so they were captured several times). The delivery claim “all 44 images match” was invalid because the comparison script checked only the alpha channel, not colour, and eight images were blank. The script was fixed and screenshots retaken (review report R2).
- Documentation: Section 7 of `ARCHITECTURE.md` and the path explanation in `frontend/README.md`; Section 25 of `SPRINT3.md` lists the moves and deletions. The older SPRINT3 section is a historical record and remains unchanged.

## 1.19.0: Notification Settings Page and Attributed Announcements (2026-10-26, Sprint 3)

Based on `claude/tasks-1.19.0.md` confirmed by Loy (N1, N2, A1–A4, and D1). Notification settings were previously hidden on Account, with one switch controlling both in-app and email delivery. The separate **Notifications** sidebar page now shows five categories with independently and immediately saved **In the bell / By email** columns. Account retains only a settings link. When site email is disabled, the email column is disabled with an explanation.

- Save notification channels separately when creating a record. Email-only records never enter the bell or unread count. If both columns are disabled, no notification is created. Preserve Manager urgent-work notifications. Existing `enabled` continues to mean in-app delivery; email defaults to enabled after upgrade.
- Show active announcements and author attribution at the top of every role's home page, taking no space when empty. Announcements do not create personal bell or email notifications. Staff maintain manual announcements on **Announcements**, which shows active and ended records. Titles are limited to 120 characters, bodies to 1,000, with an optional removal time.
- Authors may edit and remove their own manual announcements. A Manager may also remove, but not edit, someone else's. An Admin cannot manage another author's. All student write endpoints return 403. Requests cannot choose announcement kind, resource, or author. Actions are audited.
- When a Manager places a room or device under maintenance or closes it, create a status announcement in the same transaction. Changing the reason updates the same announcement; reopening removes it automatically. Optional **Expected back** is a Sydney-time recovery estimate, not an announcement expiry and does not reopen automatically. Status announcements cannot be edited or removed through manual-announcement endpoints. Existing notifications for affected booking holders remain.
- Repeatable migration `009_announcements_notification_channels.sql`; synchronise new `announcement` table, notification-channel snapshots, and preference email column to `schema.sql`. `author_role` stores the role at publication; `expected_back` is separate from `expires_at`; resource-status announcements have a partial unique index.
- API version becomes 1.19.0, with OpenAPI coverage for all 72 routes. New behaviour is covered in Memory/PostgreSQL, HTTP permissions, date conversion, and 390px browser checks. See Section 24 of SPRINT3 for the code index.
- D2 is not included. EC2 was not updated; Docker and deployment files were unchanged.
- Review fix (Claude Code, R1 in `claude/reports/2026-10-26-review-1.19.0.md`): Remove at for manual announcements previously allowed a past time, making a newly published announcement immediately expired and invisible on every home page without explanation. Publication and editing now require a future time or return 400.
- Deployment-instruction correction (Section 3 of `DEPLOY.md`, comments in `backend/entrypoint.sh`): instructions previously said to replace the code with `up -d --build` before running the migration with `exec`, which briefly ran new code against the old schema. Now use `build`, run `run --rm api migrate <file>` with the new image, then run `up -d`.
- Review Q1 (decided by Loy on 2026-10-27): when site email was disabled, **By email** on Notifications was grey but still checked according to saved preferences, suggesting email was active. The entire column now appears unchecked. Saved preferences remain unchanged and reappear when site email is enabled. Frontend display only; API unchanged.

## 1.18.0 Review Fixes, Student Registration Entry, and Docker Deployment (2026-10-25, API remains 1.18.0)

Based on Claude Code's review of the previous round (`05f7752`) in project document `claude/reports/2026-10-25-review-1.18.0.md` (IDs match the report) and Loy's decisions. No API, database, or booking-rule changes.

- **D1 timeline wheel**: the wheel listener was attached to an element that did not exist during the first render and disappeared again after changing dates, so it rarely worked in normal use. Reattach on data changes. At either end, return wheel scrolling to the page so the page can continue scrolling while the pointer remains over the timeline.
- **D2 notification preferences**: when one save included an unknown category, earlier categories were previously saved before the error. Validate all categories first, then save in one transaction.
- **Student registration entry** (Loy's decision): when 1.18.0 removed direct demo sign-in from the login page, Create student account was also removed, leaving no way to create a student through the website. Add **No demo account? Create one** to the mock SSO page (zID, name, university email, using existing `auth/demo-register/`; hidden when demo registration is disabled on the backend).
- **Docker deployment** (new `DEPLOY.md`):
  - D4: under PostgreSQL, stop injecting demo data at runtime (`SEED_DEMO_DATA` fixed to false, otherwise every worker startup overwrites rooms, equipment, and staff passwords changed through the website). Instead, `entrypoint.sh` imports `seed_*.sql` once when creating a database (`LOAD_DEMO_DATA`).
  - Stop rerunning migrations on every startup (migration 005 resets demo staff passwords). Run each new migration once through `./entrypoint.sh migrate <file>`.
  - D5: always include `127.0.0.1` in `ALLOWED_HOSTS`, so health checks still work after configuring a public IP. D6: exclude `.venv` in `.dockerignore`. D7: install pinned versions from `requirements-postgres.txt` and pin `gunicorn`. D8: pass `SITE_URL`.

## 1.18.0 (2026-10-25)

Based on Loy's trial feedback. Add notification preferences, add induction-submission notification, turn the urgent entry point into a button, and remove meaningless direct demo sign-in from the login page.

- **Notification preferences** (`GET/PUT notifications/preferences/`): add a Notifications card to Account. Students and staff can disable in-app notifications by category (Booking updates, Reminders, Induction and training, Account and booking freeze, Room and equipment status). Unsaved categories default to enabled. Manager urgent-request notifications are unaffected. Preferences are stored per person (`notification_preference` table, migration 008).
- **Induction submission notification**: after a student submits induction evidence, the bell receives “Induction evidence received” (`INDUCTION_SUBMITTED`). It belongs to the induction category and may be disabled. Submission was previously silent.
- **Urgent entry point**: change “Need a date before …? Make an urgent request” above the timeline from a blue text link to a yellow button, making the urgent path obvious.
- **Login page**: remove “Other demo sign-in options” (direct zID sign-in + Create student account). Demo users use “University sign-in (Demo),” staff use Staff sign-in, and local testing uses Test console. Retain `auth/demo-login/` and `auth/demo-register/` for the mock SSO page and tests.
- API 1.18.0 (adds `GET/PUT notifications/preferences/`); migration 008; 69 OpenAPI routes; no booking-rule changes.

## Code Structure Cleanup (2026-10-25, API remains 1.17.1)

Following the structure review in project document `claude/reports/2026-10-25-code-structure-review.md`, remove dead code and split oversized files. No API, database, or booking-rule changes.

- **Backend**: split `backend/booking/views.py` (840 lines and 69 classes) into a `views/` package with ten domain modules. Shared imports and helpers are in `views/_common.py`; `from booking.views import X` remains valid.
- **Frontend**: delete unused `src/App.css`; move `RescheduleBox` and `SeriesCard` from `MyBookings.tsx` into same-named files; move date helpers from `SlotPicker.tsx` to `slot-picker.ts`; move the `ACTIVE` status group to shared `my-bookings.ts`.
- **Dead animation code**: remove duplicate page fade-in (retain one `.app-page` rule in `workspace.css`), duplicate dialog entrance (retain `.bk-modal` in `booking.css`), overridden reduced-motion rules (retain one in `workspace.css` and add `::backdrop`), overridden button press scaling, and the `animation: none` that overrode bell ringing. Bell ringing now actually plays.
- **Style layers**: add “Style layers” to `frontend/README.md`, requiring new styles to go only into `workspace.css`, freezing `ui.css`, and moving styles component by component.
- Verification: 355 backend tests pass (18 PostgreSQL tests skipped); frontend unit 68, lint, and build pass. See the delivery record for Playwright and complete script results.

## Internal-Tool Style: First Step to Remove the AI Look (2026-10-25, API remains 1.17.1)

Loy's direction: design the interface as a “school internal tool” rather than referring to award-winning websites. This round covers copy, font sizes, typeface, and naming (task list in project document `claude/tasks-ui-internal-tool.md`; D1–D8 accepted as recommended). No API, database, or booking-rule changes.

- **AI-2: conversational copy.**
  - Remove marketing lines, eyebrow labels, and explanatory sentences below headings: home-page greeting, Find a free time slogan and steps, “Everything is in good order.” on Today, “SHARED SPACE” on resource cards, “SPACES TO LEARN…” and feature strip on sign-in, “Student Portal” in the top bar, and “PAGE NOT FOUND” on 404.
  - Headings no longer end in full stops.
  - Only four staff pages retain a one-sentence description: Booking review, Booking freezes, Resources, and User management.
  - Change the home-page title to “Dashboard.” The sign-in page shows only “SmartLab” plus “Book lab rooms and equipment at UNSW.”
- **AI-3: polarised type sizes.**
  - Reduce type sizes to five levels: 28/20/16/14/12, with H1 at 24 on phones. No text is smaller than 12px.
  - Define H1 in one shared rule only.
  - Change small uppercase, letter-spaced labels outside the sidebar and table headers to normal text.
- **AI-5: editorial serif/sans pairing.**
  - Remove Instrument Serif and its font files; use only Manrope everywhere, including sign-in. The mock university SSO page is the exception: it represents Microsoft's sign-in page and remains unchanged.
  - Consolidate radii to 8px (buttons, inputs, badges) and 12px (cards, dialogs, tables), with circles for avatars and pill shapes.
- **AI-6: multiple names for one page.**
  - Use the same sentence-case name in navigation, H1, and browser tab. Rename Qualification Review to Induction review, using the same term as the student's Induction & training.
  - Format opening hours consistently as “8:00 am – 8:00 pm,” matching other times across the site (`fmtClock` and `fmtHours` in `format.ts`).

The acceptance criteria above are encoded in unit test `tests/ui-internal-tool.test.mjs`, so reverting these choices causes an immediate failure. See Section 20 of `SPRINT3.md` for code locations.

## 1.17.1 (2026-10-25)

- **FC-04: Account 1 still shows induction not submitted.** Loy explicitly required this test account to have all inductions without uploading evidence. The backend now automatically grants every training requirement permanently; new requirements are added on the account's next request. Qualifications remain when switching among all three roles or disabling booking-rule bypass. The UI removes the evidence form for this account and displays an English explanation. Automatic grants do not fake attachments: `file_id` and `file_url` are empty, and repeated requests do not create duplicate records. Normal accounts still require upload and review. The test console remains available only in explicitly enabled local memory mode, conflict protection is unchanged, and there is no database migration.

## Workspace UI Iteration (2026-10-25, API remains 1.17.0)

Loy requested a complete, usable first design before reviewing the result. Review typography, spacing, visual hierarchy, colour, animation, micro-interactions, responsiveness, and originality. Do not state “award-winning” or “nothing to improve” as facts. No API, database, or booking-rule changes.

- **UI-01: inconsistent visual language across pages.** Unify fonts, dark green/warm white/UNSW yellow, controls, tables, states, and navigation across the workspace. Fonts are provided locally under open licences.
- **UI-02: scattered information on home and resource pages.** Emphasise the student's next approved booking on the home page. Resource cards show real location, specifications, and training requirements with less decorative cover content. Staff Today prioritises modules with pending work and collapses empty secondary panels.
- **UI-03: users must reselect time after finding a resource by time.** Find a free time requests data only when search is submitted; changing criteria does not trigger an immediate query. Return a compact result list. Review booking retains the selected time, and the full time grid can be expanded. After changing search criteria, require another search to avoid using stale results.
- **UI-04: booking list lacks status navigation.** Add local filters and counts and store the selected category in the URL. Changing categories does not refetch booking data.
- **UI-05: long phone dialogs and unstable keyboard interaction.** Collapse resource guidance. Native dialogs trap focus, Escape closes and returns focus to the original button, phones retain the bottom submit area, and reduced-motion preference is handled.

See Section 18 of `SPRINT3.md` for code and test locations. The backend still revalidates qualification, conflicts, and time rules. This round does not reduce backend slot calculations or optimise database queries.

Changes after Claude's review (original review in project document `claude/reports/2026-10-25-workspace-ui-review.md`, with the same IDs):

- **R1: errors inside dialogs are invisible.** When a native dialog is open, an external toast sits beneath the backdrop and cannot be clicked. Room Management reschedule failures previously appeared only in a toast; the error now also appears inside the dialog (`RescheduleBox`). `Modal` documentation states that dialog content must provide inline errors.
- **R2: training requirements are collapsed.** When any induction is unverified, “Training requirements” is expanded by default with an amber count; it collapses only when all are verified.
- **R4: dragging to select text closes the dialog.** Close only when both pointer-down and pointer-up occur on the backdrop. Selecting text in an input and releasing over the backdrop no longer loses entered content.
- **R5: dialog names.** Name each dialog after its title (`Book <resource>`, `Repeat weekly: <resource>`, `Reschedule booking`) instead of using “Booking details” for all.
- **R7: cleanup.** Add missing `Sprint 3` markers, split JSX crowded onto one line, and delete unused `.bk-overlay` styles.
- **UI follow-up Item 1: page overflows on phones.** Original follow-up in project document `claude/reports/2026-10-25-ui-review.md`.
  - Symptom: at 390px wide, Room Management, Resources, Lab Setup, User Management, and student My Bookings expand to 478–579px, causing the whole page to shrink or scroll sideways; students cannot see the “Cancelled” tab.
  - Cause 1: screen-reader-only “Actions” in the table header is absolutely positioned outside the table's horizontal scroll area. Add `position: relative` to table wrapper `.ui-table-wrap`.
  - Cause 2: tab rows do not wrap. On phones, tabs now scroll horizontally within their own area.

## 1.17.0 (2026-10-25)

Implemented according to Loy's functional decisions after reviewing local screenshots. This round prioritises function and does not redesign the overall visuals. No database-schema changes.

- **FC-01: duplicate explanation fields for Urgent.** Keep one required **Purpose and urgency** field in the Urgent form, sending the same text as both `purpose` and `urgent_reason`. Normal bookings still show Purpose. Urgent requests from normal accounts still require Manager approval.
- **FC-02: every test requires switching accounts, waiting for approval, and following the booking window.** Add an explicitly enabled local Test console with sign-in ID `1` and no password. One account can switch among Student, Admin, and Manager and toggle booking-rule bypass. When enabled, self-bookings and self-reschedules are approved immediately, skipping advance days, qualifications, opening hours, maintenance state, maximum duration, weekly-count limit, and freezing. Self-testing supports weekly recurring bookings. Retain future-valid times, a 24-hour per-booking cap, duplicate and conflict protection, and a 52-week recurring-series maximum. When acting as another person, that person's normal rules apply. Permission exists only in a server-signed session and does not modify the persistent role; it defaults off and is unavailable under production authentication. Test bookings retain in-app notifications and audit, but do not send email or sync Outlook.
  - **Available only in memory mode** (decided by Loy after the 2026-10-25 review): `test_console_enabled` additionally requires `REPOSITORY_FACTORY` to be memory storage. With PostgreSQL, test bookings would enter the production database, appear in Booking Records, Usage statistics, and Today, and occupy real times. Do not create a separate table for the test account; restarting the backend clears it. Local `start-backend.ps1 -TestConsole` automatically uses memory mode.
  - Minor review fixes: default `TestPrincipal` bypass to off (all callers already passed it explicitly, so behaviour is unchanged); set bypass slot end to local midnight on the next day (avoiding a one-hour difference on daylight-saving days); use `booking_rules_bypassed(actor, person.id)` consistently for per-date and outer recurring checks (the endpoint does not accept `1` as a zID, so the previous version could not produce different behaviour but was inconsistent to read); add missing `Sprint 3` file markers and correct the `create_test_booking` explanation. Bypass still defaults on after sign-in (confirmed by Loy).
- **FC-03: evidence upload lacks required guidance.** Mark training requirement, title, and attachment as Required. Without a selected file, directly explain that a certificate must be uploaded and keep the button disabled. Empty, oversized, and unsupported files show English errors. File selection uses English “Choose file / No file selected.”

API version is 1.17.0. See `backend/docs/frontend-api.md` for the API contract and Section 17 of `SPRINT3.md` for feature code and test indexes.

## 1.16.0 (2026-10-25)

Sprint 3 batch five: address the third-party user-experience report from 2026-10-24 (14 items based on 1.15.0). Each numbered item below first states the reported issue (the reason for the change), then the solution. Loy's direction: book rooms and equipment separately, leaving combination logic to the client; students may request time changes, but an occupied new time can only join the waitlist; send automatic maintenance notifications. Loy chose among the uncertain options for Items 2, 3, 4, and 12. **Database change: migration 007.** New code is marked `Sprint 3 (1.16.0)`; see Section 16 of [SPRINT3.md](SPRINT3.md) for the checklist.

1. **Purpose is missing on the review page**: add a Purpose column and prominent Details button to Booking Review (the entire row also opens it). The details drawer already contained purpose, qualification, and deadline, but its entry point was unclear. A time-change request shows Change from below the time.
2. **No contact entry point, and students cannot request time changes themselves**:
   - Time-change request (`services/changes.py`, `POST bookings/{id}/change/`): the booking holder may request a new time for an approved future booking. A free new time becomes pending approval; an occupied time joins the waitlist, with a warning before selection. Keep the original booking until the new request is approved, then automatically cancel it (`REPLACED_BY_CHANGE`) and hand its time to the waitlist. Rejection, withdrawal, or expiry leaves the original unchanged. Apply normal request rules, excluding the original from conflict, duplicate, and weekly-quota checks. A booking can have only one concurrent time-change request (database partial unique index). Urgent time changes are forbidden. Previously only a Manager could reschedule, so a student had to cancel and rebook, risking loss of the time.
   - Contact details (new `site_contact` table, `GET/PATCH site/contact/`): Loy decided a Manager enters email, phone, response time, and notes on the new Lab setup page. Show entered fields only on Help, approved booking cards (Contact the lab, with resource, time, and booking ID prefilled in email), and under each induction.
3. **New students do not know how to obtain induction**: add four guidance sections to each induction (how to complete, accepted evidence, reviewer, contact). Induction & Training shows How to get this induction. Loy decided a Manager can create an induction in Lab setup, change its name and all guidance, and set prerequisites (`POST admin/qualification-requirements/`, `PATCH …/{id}/`). Copy changes do not affect already verified users.
4. **Insufficient resource information to choose correctly**: Loy chose a customisable “label: content” list plus room capacity because each lab needs different information. Rooms may specify `capacity`; all resources may have up to 12 `details` rows. Cards show capacity and the first three rows; the booking form shows all. Room lists can filter for “at least N people.” Card covers are smaller.
5. **Selecting time on a phone requires scrolling in two directions**: allow direct selection of start time and duration below the time strip. On phones, fix the selected time and submit button to the bottom of the dialog.
6. **Users wanting a near-term booking first hit the date restriction**: on the earliest bookable day, explain that earlier dates require an urgent request and provide one-click switching. Advance-day rules are unchanged.
7. **Bookings after maintenance require manual multi-step handling**: send automatic notifications as decided by Loy (`_notify_status_change` in `services/resources.py`). When a resource enters maintenance or closes, everyone with a future booking or request receives an in-app notification and email containing the Manager's reason; reopening also notifies, while changing only the reason does not send duplicates. Approved bookings remain for the Manager to decide. The confirmation dialog lists affected bookings, the list marks them, and Today shows resources under maintenance and the affected count.
8. **Room/equipment relationship is unclear**: as decided by Loy, book them separately without automatic combination. The page states that booking a room does not include its equipment and booking equipment does not reserve its room.
9. **Duration differs between the two booking methods**: Find a free time offers up to eight hours. If one resource cannot support the selected duration, skip only that resource and count it in `too_long`; previously the entire request returned 400 and the page showed an error.
10. **Empty results describe qualification issues as filter problems**: explain what was hidden by reason (for example, “19 hidden: 18 induction not submitted, 1 under maintenance”) and provide an Induction & Training link when induction is involved (`not_bookable` in `day_overview`).
11. **Calendar subscription discusses only Outlook**: provide separate steps for Outlook, Google, and Apple; explain update delays and that the website is authoritative; when generating a new link, explain that the old subscription must be removed.
12. **Manager has no work overview**: Loy chose a staff Today home page (`/admin/today`, `GET admin/overview/`). Admin and Manager initially see pending inductions, pending bookings, urgent requests, waitlists, time-change requests, requests near review deadline, unfreeze requests, resources under maintenance, today's bookings, and absences. Each card links to its handling page. Previously Admin landed on Qualification Review and Manager on Room Management.
13. **Required fields are unmarked and disabled buttons unexplained**: mark Purpose required and directly state what is missing when the button is disabled (`submitBlocker`).
14. **Management forms use minutes**: enter resource “maximum booking” and “review period” in hours and explain how the value applies (for example, “The system decides automatically after 24 h (1 day)”). The API remains in minutes.

- Demo data is unchanged: contact details, induction guidance, capacity, and resource information are empty for a Manager to complete through the website.
- Not implemented: Item 6's “choose a date before explaining the process,” adjacent-date recommendations in Item 10, single-event download in Item 11, sidebar grouping in Item 12, real photographs, or visualisation parts two and three.
- Migration 007 (`007_change_requests_guidance_details_contact.sql`, repeatable); OpenAPI 1.16.0.

## 1.15.0 (2026-10-24)

Sprint 3 batch four: the first visualisation set, based on Loy's 2026-10-24 review from user and leadership perspectives. Frontend only; no database or API behaviour changes (version synchronised according to policy). All new code is marked `Sprint 3`; see Section 15 of [SPRINT3.md](SPRINT3.md).

- **Notification bell**:
  - The badge was previously as large as the bell and covered it because `.app-icon-button > span { font-size: 27px }` in `shell.css` overrode the badge's 11px. The badge now uses a more specific selector, is smaller, moves to the bell's top-right, and gains a white border.
  - The bell rings once when unread count increases, and the badge pops when its number changes. It does not ring during initial page load, avoiding animation on every visit.
  - On phones, the panel previously expanded left from the bell beyond the screen edge. On narrow screens it is now fixed below the top bar with 16px margins.
  - Panel: group into “Today / Earlier” by Sydney date, add a type icon to each item (approval ✓, rejection or cancellation ✗, reminder clock, other i), limit the body to two lines, and show unread items with bold titles and a blue dot instead of an all-blue background. Previously each item used three or four lines, only two or three fit on screen, and message types were unclear.
- **Resource-card covers**: previously used the first letter of the name on a gradient, making two rooms identical and looking like placeholders. Now use icons and colours by type: room, microscopy, imaging, electronic testing, soldering, fabrication, analysis, and a generic icon for other equipment. Equipment cards show category at bottom-left. The type is inferred from category/name keywords, so future Manager-created categories such as “3D printing” also match. Replace these when real photographs are available.
- **Time-cell colours** (Book a resource dialog and Find a free time): previously “available” was the darkest blue across the screen, while “occupied” was subtle light-grey hatching. Available is now light blue, darkening with a blue outline on hover; occupied is solid dark grey; pending and own requests retain hatching; unavailable uses fine light-grey hatching; the full strip has a border. Add a red vertical “now” line during today's opening hours, also shown as Now in the legend.
- **Base animations**: shared duration and easing variables in `index.css`; fade content when changing pages; slightly lift resource cards and home-page number cards on hover; fade/lift dialogs and confirmations; slightly shrink pressed buttons. Disable all when the system requests reduced motion. Page fade uses opacity only, not translation, because translation displaces fixed-position dialogs.
- Not implemented: real photographs and Manager photo upload (waiting for photographs); Manager management of induction types on the website (undecided).
- OpenAPI 1.15.0 (API unchanged).

## 1.14.0 (2026-10-24)

Sprint 3 batch three, based on Loy's trial feedback on 2026-10-24. No database change. All new code is marked `Sprint 3`; see Sections 11–14 of [SPRINT3.md](SPRINT3.md).

- **Email notifications** (`booking/email_channel.py`):
  - Send from one Gmail system mailbox using SMTP and an app password, connected through the notification-delivery channel reserved in 1.12.0 without changing business code.
  - Send to the booking holder's university email: request received, approved or rejected (including automatic decision), expired, promoted from waitlist, time changed, cancelled by staff, reminder, booked on their behalf, or recurring booking created for them. Subject includes resource and time; body includes the website link.
  - Toggle `EMAIL_ENABLED` (off by default); recipient scope `EMAIL_MODE`: `none`, `allowlist` (default, listed addresses only), `redirect` (send everything to one address for demonstration), or `all`. Demo zIDs may belong to real students, so messages are not sent outside the allowlist by default.
  - Delivery failures are logged without affecting bookings. New command `manage.py send_test_email --to` checks configuration.
  - Why Gmail: since September 2024 Outlook.com no longer accepts password-based SMTP sign-in; Microsoft authorisation is required and tokens expire. See [email-setup.md](backend/docs/email-setup.md).
- **New “request received” notification** (`BOOKING_SUBMITTED`): after submitting, the bell and email confirm receipt, explain whether it is pending review or waitlisted, and say when a result is expected. Staff recurring bookings also receive confirmation (`SERIES_CREATED`). Previously there was no written confirmation after submission.
- **Booking Records page** (Admin and Manager, `/admin/records`):
  - Records tab: search everyone's bookings by date, resource, status, name, or zID; show booking holder, creator, status, and attendance. Export CSV exports the same list.
  - Usage statistics tab: move the old Usage Report page here and remove Usage Report from the menu (old address redirects automatically).
  - API: add `q` (part of zID or name for booking holder or creator) to `GET admin/bookings/` and `export/`; allow Admin to export CSV and view usage reports; add Weekly series and Attendance columns to CSV.
  - Room Management retains only Manager actions (open/close resource, reschedule, cancel). Export moves to Booking Records.
  - Reason: the client needs to see “who booked what and when,” and Admin also needs access.
- **Interface**:
  - Display durations consistently in hours (`0.5 h`, `1 h`, `1.5 h`). Only the time step in resource settings remains in minutes.
  - Combine a recurring series in My Bookings into one card showing pattern (weekday/time), start/end dates, remaining occurrences, and next occurrence. Today's I'm here button appears directly on the card. Show dates expands each date for individual cancellation; staff can Cancel the rest. Previously a ten-occurrence series produced ten cards.
  - Replace the large induction banner at the top of Book a Resource with one line (`General ✓ · Advanced ✗ Upload`), using warning colour only when something is missing. Calendar subscription in My Bookings becomes a small button that reveals the link when selected.
- OpenAPI 1.14.0.

## 1.13.0 (2026-10-23)

Sprint 3 batch two. No database change. All new code is marked `Sprint 3`; see [SPRINT3.md](SPRINT3.md).

- **Manager manages rooms and equipment on the website** (new Resources page):
  - Create, edit, archive, and restore through `GET/POST admin/resources/`, `PATCH admin/resources/{id}/`, `POST …/archive/`, and `POST …/restore/`.
  - Reason: adding resources previously required hand-written SQL, so the client could not maintain them independently after handover.
  - Editing does not change existing bookings; it lists future bookings that no longer satisfy the new rules for a Manager to handle. Changing opening hours therefore never silently cancels someone else's booking.
  - Archive instead of delete, so booking and audit records can always resolve the resource.
- **Reminders**: remind users to select I'm here 24 hours before a booking, remind when induction expires within 14 days, and notify when a waitlisted or pending request expires. This reduces forgotten attendance and discovering qualification expiry too late. Send each only once by checking existing notifications, without a new table. New configurable rules: `REMINDER_HOURS_BEFORE` and `INDUCTION_REMINDER_DAYS`.
- **Usage report** (new Usage Report page, `GET admin/reports/usage/`): booking count, hours, percentage of opening hours, attendance rate, and absences per resource, allowing the client to evaluate equipment use.
- **Staff change their own password** (Account page, `POST auth/change-password/`). Previously only a Manager could reset it.
- **`manage.py create_manager`**: create the first Manager without hand-written SQL. It shares `_create_staff_account` with Add staff, using the same rules.
- **Markers**: all Sprint 3 code is marked `Sprint 3` in files; ARCHITECTURE.md adds a section showing where every rule is implemented.
- OpenAPI 1.13.0.

## 1.12.0 (2026-10-23), migration 006

Based on requirements finalised by the team on 2026-10-23 (calendar subscriptions, notifications, check-in, weekly limit, and recurring bookings). The design references LibreBooking/Booked Scheduler (check-in, automatic release, quotas, iCal), NEMO (no-show handling), and MRBS (recurring bookings).

- **Calendar subscription link**: each person has a private address (`GET calendar/link/`, regenerated through `POST calendar/link/reset/`). Outlook, Google Calendar, or Apple Calendar periodically reads `GET calendar/{token}.ics`. No Microsoft authorisation is required, solving the “put it in each person's calendar” requirement; update frequency is controlled by the calendar application.
- **In-app notifications**: top-bar bell (`GET notifications/`, mark as read). Notify when a booking is approved or rejected, promoted from waitlist, rescheduled by a Manager, cancelled by staff, created by staff on the user's behalf, when induction review completes, for absence, freezing, and unfreezing. A Manager receives urgent requests. Normal new requests do not notify administrators. Reserve a delivery-channel interface for Outlook/email (`booking/notification_channels.py`, `NOTIFICATION_CHANNELS`), not implemented in this release.
- **Check-in and freezing**: the booking holder must select I'm here from 15 minutes before to 30 minutes after an approved booking starts (`POST bookings/{id}/check-in/`), otherwise record an absence (unless the resource is under maintenance or closed). The fourth absence freezes bookings for 30 days and cancels all later bookings and requests for that person. Freezing affects only booking; staff may continue reviewing. A frozen user may submit an unfreeze request, which Admin/Manager handles or bypasses through the new Booking freezes page.
  - Discussed trade-off: the website button can be selected from anywhere, so it prevents forgotten cancellations but not deliberate cheating. A more reliable method (a QR code at the door) remains a question for the client.
- **Weekly limit**: each person may have at most three pending, waitlisted, or approved bookings per Monday-to-Sunday week (`WEEKLY_LIMIT_REACHED`). Check only when creating a request or when a Manager reschedules, so waitlist promotion and automatic deadline processing are unaffected.
- **Staff recurring bookings**: Repeat weekly on a resource card previews each date, skips invalid dates, and **directly approves** the rest (staff created it and do not need to approve their own work). It may exceed the “30 days in advance” window for up to 14 weeks and is not subject to the weekly limit.
- New configurable rules: `MAX_BOOKINGS_PER_WEEK`, `CHECK_IN_OPENS_MINUTES`, `CHECK_IN_CLOSES_MINUTES`, `FREEZE_AFTER_NO_SHOWS`, `FREEZE_DAYS`, and `MAX_SERIES_WEEKS`.
- Migration 006: new tables `notification`, `calendar_feed`, `unfreeze_request`, and `booking_series`; add absence count and freeze end time to users; add series and attendance markers to bookings. Approved bookings that have already started are marked `NOT_TRACKED` and do not count as absences.
- OpenAPI 1.12.0. Also correct several nullable fields and the `ManagedUser` representation so strict validators pass (API behaviour unchanged).

## 1.11.1 (2026-10-20)

No API changes.

- **Backend refactor**: split `booking/services.py` into the `booking/services/` directory with nine topic-based files (see [ARCHITECTURE.md](ARCHITECTURE.md)). Only code location changes; behaviour is unchanged and `from booking.services import BookingService` continues to work.
- **Documentation cleanup**:
  - Each document describes only current rules; move version numbers, dates, and “new/previous” wording into this file.
  - Add `ARCHITECTURE.md` and `CHANGELOG.md`; replace the GitLab template in root `README.md` with project documentation.
  - Change upgrade steps in `backend/database/README.md` to run all migration scripts in order (verified to make no change when run against an already-current schema).
  - Correct outdated documentation: dashboard `counts` contains seven statuses, and staff can also make bookings.
- **OpenAPI**: wording only (remove Sprint, date, and version notes); set version to 1.11.1.

## 1.11.0 (2026-10-18), migration 005

Based on the client's 2026-10-17 email: one-way synchronisation is acceptable for the first phase, but Outlook must be genuinely integrated and tested. The website is the sole source of truth; Outlook edits must not bypass rules or become approved bookings.

- **Real Outlook integration (one-way)**:
  - Write calendars through Microsoft Graph: create an event after approval, update it when a Manager reschedules, and delete it on cancellation.
  - The system never reads Outlook. A user's edits or deletion in their calendar are ignored. Only when a Manager reschedules and the event has been deleted does the system recreate it at the new time (audit `OUTLOOK_EVENT_RECREATED`).
  - Invitation controls `OUTLOOK_INVITE_MODE` (`none`/`allowlist`/`all`, default `allowlist`) and `OUTLOOK_ALLOWED_ATTENDEES` prevent invitations to real people.
  - Two authorisation methods: `manage.py outlook_token` (paste a Graph Explorer token) and `manage.py outlook_login` (device-code sign-in with automatic renewal).
  - Live-check command `manage.py outlook_live_check`: connect, create, read back, reschedule, and delete in five steps.
  - New endpoint `POST admin/outlook/check/`; `GET admin/outlook/` adds `summary`, `items`, `last_check`, and `invite_mode`.
  - Add frontend Calendar Sync development page (`/admin/calendar-sync`), to be removed before final delivery.
- **Decided against after discussion**: checking whether Outlook events were changed (drift check) and automatically restoring them. Each person manages their own calendar, edits/deletions have no penalty, so checking has no value.
- **Find a free time on the booking page**:
  - New endpoint `GET resources/day-overview/`: one table lists available and occupied time for every resource matching the filters, using the same rule checks as individual resource slots.
  - Add resource `category` (equipment category; demo categories are invented). `GET resources/` supports a `category=` filter.
- **Demo staff passwords** changed to `123` for z9000001 and z9000002.
- Migration 005: `bookable_resource.category` and demo passwords.
- Standardise OpenAPI nullable fields to the 3.0 representation.

## 1.10.0 (2026-10-17), migration 004

Based on the client's 2026-10-17 email.

- **Everyone books under one rule set**: Admin and Manager can also book, and induction cannot be bypassed.
- **Book on behalf of another person**: staff use `on_behalf_of_zid`; the booking belongs to the person booked for (their induction is checked), while `created_by` records the creator. New endpoint `GET people/lookup/`; availability supports `for_zid`.
- **Urgent requests**: `urgent` + `urgent_reason` skips only the minimum advance period. The time must be free. Only a Manager decides; there is no automatic approval.
- **Rescheduling becomes Manager-only** and is not subject to the minimum advance period.
- A reviewer cannot approve a request for themselves or one they created (`SELF_REVIEW_FORBIDDEN`).
- Migration 004: `booking.created_by`, `urgent`, and `urgent_reason`.

## Staff Sign-In (migration 003)

No separate version number was recorded at the time; this falls between 1.8.0 and 1.10.0.

- Two sign-in entry points: students use university sign-in (demo requires zID only); Admin/Manager use staff sign-in (zID + password). Each path rejects the other account type.
- A Manager creates staff accounts through Add staff. The system issues an invitation code, and staff choose a password on first activation. If a password is forgotten, the Manager selects Reset access to issue a new invitation code.
- Migration 003: new `staff_credential` table storing only password hashes and invitation codes.

## 1.8.0 (Week 5, 2026-10-14), migration 002

- **People management (Manager only)**: people list, Add staff, deactivate and reactivate accounts. Deactivating a student immediately rejects undecided requests and promotes the next waitlisted request.
- **Induction prerequisites**: `prerequisite_ids`; for example, Advanced requires General first. Return `PREREQUISITE_REQUIRED` when a prerequisite is missing.
- **Rooms and equipment**: equipment records its room through `room_id`; pages group by room. Room maintenance does not affect equipment inside it.
- Migration 002: `prerequisite_ids` and `room_id`.

## 1.7.0 (2026-10-12), migration 001

Rebuild the approval flow based on the client's 2026-10-07 requirements.

- **Only people with a verified and valid induction can submit a request.**
- **Every request first becomes pending approval** and holds the time during its review period (24 hours by default, adjustable per resource by Manager). Admin/Manager approves or rejects before the deadline; if nobody responds, the system approves or rejects automatically according to the rules.
- **First-in, first-out waitlist**: when the time is held, a request joins the waitlist. When released, requests are promoted in submission order into new pending-approval requests.
- **Resource status**: a Manager can set a resource to maintenance or closed, pausing new requests while retaining existing bookings.
- **Everyone's bookings**: `GET admin/bookings/` filters by status, resource, student, and time; Manager can export CSV.
- **Remove**: immediate approval within 120 minutes, `auto_approve_max_minutes`, `needs_review`, `DURATION_REVIEW`, and `RESCHEDULE_NEEDS_REVIEW`; booking while evidence is under review (`WAITING_QUALIFICATION`, 30-minute holds, `HOLD_EXPIRED`, and `PENDING_REQUEST_LIMIT`). `WAITING_QUALIFICATION` remains only in early data.
- Migration 001: two resource-status columns; reinterpret `pending_hold_minutes` as the review period and change the default from 30 to 1,440.

## 1.5.0

- **Booking window**: start date must be between “today + 7 days” and “today + 30 days.” Values are in `RulesProvider` (`booking/rules.py`) and adjustable through environment variables.

## 1.3.0

- **Audit record query** `GET admin/audit/` (Admin/Manager).
- **Qualification validity is set by the backend**: 120 days from approval; reviewers can no longer enter a validity date.

## Earlier (Sprint 1 Foundation)

- Resource and slot queries, induction upload and review, booking request and review, cancellation, dashboard, `Idempotency-Key` duplicate-submission protection, and in-memory demo storage.
