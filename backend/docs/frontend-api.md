# Frontend API Guide

The API base path is `/api/v1/`, and every path ends with `/`. See [openapi.json](openapi.json) for the authoritative schema; after startup, `GET /api/schema/` returns the same definition.

## 1.27.0: Extensions Require Manager Approval (migration 016)

- `POST bookings/{id}/extend/ {end}`: a booking-holder request no longer applies immediately. The returned booking contains `extension_end` while `end` remains unchanged, and the Manager receives `EXTENSION_REQUESTED`. Submitting again replaces the request. A Manager call still applies immediately. Submission checks only opening hours, the resource's own maximum duration, time step, and whether later time is free; the Manager decides the three-hour per-booking and weekly-hours limits.
- `POST bookings/{id}/extend/review/ {decision, reason, expected_end?}`: Manager only. The website submits the `expected_end` currently displayed. If the request has been replaced, return 409 `EXTENSION_CHANGED`. Approval rechecks that later time is free and changes `end` to `extension_end`; rejection requires a reason. Other 409 errors: `NO_EXTENSION_REQUEST`, `EXTENSION_EXPIRED`, and `BOOKING_CONFLICT`. The booking holder receives `EXTENSION_APPROVED`/`EXTENSION_REJECTED`, including email.
- `GET admin/overview/` adds `extension_requests` (bookings whose requested end time has not passed, maximum 10). Booking adds `extension_end`.
- UI: Extend in My bookings opens a timeline from start to closing time. Drag the end line or use arrow keys to select a new end, up to the next booking. Students select Ask a Manager; Managers select Extend now. The timeline reads `resources/{id}/availability/` (students add `urgent=true` so occupied times on the current day are visible).

## 1.26.0: Clear Differences Between the Three Roles (migration 015)

- **Home page**: `homePath` sends Manager to `/manager/home` (Lab overview), while Admin remains at `/admin/today`. Lab overview uses existing endpoints: `admin/overview/`, `resources/`, and `admin/reports/usage/` (current week). Admin Today does not show the `urgent`, `additional-hours`, or `long-bookings` cards (`cardsFor` in `today.ts`). The top bar shows `Student view`/`Admin view`/`Manager view`.
- **Admin sees only recent history**: for Admin, `GET admin/bookings/` and `admin/bookings/export/` return only bookings that ended within the last seven days or later (an earlier `since` is raised to this boundary). Only Manager can use `GET admin/reports/usage/`; Admin receives 403. Booking Records hides Usage statistics for Admin and defaults to seven days ago. Opening `/admin/records?q=z1234567` searches the previous year for that zID (Manager).
- **Internal equipment information**: `GET admin/resources/{id}/internal/` and `PATCH admin/resources/{id}/internal/` with `{owner?, asset_number?, provided_by?, specifications?}` (maximum 120/60/120/2000 characters; an empty string clears the field) are Manager-only; others receive 403. Resource JSON (`resources/`, `admin/resources/`, etc.) does not include these fields.

## 1.25.0: Remove Freezing (migration 014)

- The client did not want absence penalties at the Week 8 meeting, so Loy decided on 2026-11-07 to remove freezing completely. Absences continue to be recorded in booking `attendance`, and the usage report is unchanged.
- Removed endpoints: `account/unfreeze-requests/`, `admin/unfreeze-requests/`, `admin/unfreeze-requests/{id}/review/`, `admin/frozen-users/`, and `admin/users/{id}/unfreeze/`.
- Removed fields: user `no_show_count`, `frozen_until`, and `booking_frozen`; availability `frozen_until`; `unfreeze_requests` from `admin/overview/`; `FROZEN` from day overview `not_bookable`. Error codes `ACCOUNT_FROZEN`, `NOT_FROZEN`, and `UNFREEZE_ALREADY_REQUESTED` no longer occur.
- Frontend removes the Booking freezes page (`/admin/freezes`) and freezing notice.

## 1.24.0: Client Week 8 Meeting (no migration)

- **Manager rule override**: a Manager's `POST bookings/` (for themselves or with `on_behalf_of_zid`, excluding a time-change request) becomes directly `APPROVED` with `reason_code=MANAGER_OVERRIDE`. It does not check induction, the 7–28-day window, three-hour duration, 12-hour weekly quota, eight-future-booking limit, or freezing. It still checks that the resource is bookable, within opening hours and its own maximum duration, aligned to the time step, and free (conflict returns 409 `BOOKING_CONFLICT` without joining the waitlist). Admin is unchanged. `POST bookings/{id}/reschedule/` also stops checking induction, date window, weekly quota, and future-booking count.
- **Manager availability**: availability (outside additional-hours and long-booking modes) and day overview return `manager_override: true`. Dates start today, `latest_date=null`, `max_booking_minutes` is the resource's own maximum, and `can_request` depends only on whether the person and resource are active. Availability also returns `normal_booking_window`, which the staff recurring-booking form continues to use.
- **Extend an in-progress booking**: `POST bookings/{id}/extend/` with `{end}`. The booking holder or Manager can use it on an approved booking that has started but not ended. If later time is free, apply immediately without review, increment `revision`, update the original Outlook event, and notify the Manager with `BOOKING_EXTENDED`. A non-Manager must also satisfy the three-hour per-booking limit, weekly-hours quota, and induction through the new end. Errors: not started/ended/additional-hours/long booking → 409 `EXTENSION_NOT_AVAILABLE`; new end not later than old end → 400 `VALIDATION_ERROR`; later time occupied → 409 `BOOKING_CONFLICT`; otherwise normal errors (`DURATION_LIMIT`, `OUTSIDE_OPENING_HOURS`, `WEEKLY_LIMIT_REACHED`).
- **Freezing**: disabled by default in 1.24.0 and removed entirely in 1.25.0; see the previous section.

## 1.22.0: Long-Booking Requests (migration 013)

- **Separate submission**: `POST bookings/long-bookings/` with `{resource_id,start,end,purpose,long_booking_reason,on_behalf_of_zid?}`. Purpose and long-booking reason are required; reason maximum is 1,000 characters. Supports `Idempotency-Key`: retrying the same request returns `200`, first creation returns `201`. Changing the reason, beneficiary, time, or request type requires a new key. Clients cannot send review status, `urgent`, `additional_hours`, `series_id`, or similar fields.
- **Exemption scope**: relax only the normal per-booking duration limit (three hours by default). Duration must exceed that limit without exceeding the resource's own maximum. The 12-hour weekly quota, eight-future-booking limit, normal 7–28-day window, opening hours, time step, and qualification rules still apply, including to staff proxy bookings. Additional-hours, urgent, and recurring bookings cannot be combined with this flow. All numbers use configurable rules.
- **Hold and review**: if free, return `PENDING_APPROVAL` with `hold_until=review_due_at`, holding the time for the resource's existing review period. On conflict, return `WAITLISTED` under the normal FIFO waitlist. Promotion creates a new review deadline. Only a Manager may approve or reject through existing `POST admin/bookings/{id}/review/`, without self-review or reviewing a request they created. Approval rechecks qualification, weekly quota, future-booking count, resource limits, and conflicts. If not approved by the deadline, become `EXPIRED` with `reason_code=LONG_BOOKING_REVIEW_EXPIRED`, release the time, and promote the waitlist. Never auto-approve.
- **Date and duration selection**: `GET resources/{id}/availability/?date=YYYY-MM-DD&long_booking=true`; cannot combine with `urgent=true` or `additional_hours=true`. Returns the normal date window, `normal_max_booking_minutes`, first valid `min_booking_minutes` strictly above the normal limit, `max_booking_minutes` aligned to the resource's technical limit, and `selection_step_minutes`. Small-grid queries may still pass `duration_minutes=30`; the submitted full interval must satisfy long-booking requirements. If the resource has no valid long interval, `can_request=false` and the UI does not offer a long-booking entry point.
- **UI and tasks**: Booking adds `long_booking` and `long_booking_reason`. The resource page has a separate entry point; My bookings shows manual-review deadline, waitlist, or expiry reason. The review page has a Longer bookings tab; Admin is read-only. `GET admin/overview/` adds `long_booking_requests` and `can_decide_long_bookings`; normal `pending_bookings` excludes long requests. Manager receives `LONG_BOOKING_REQUEST`.
- **Errors and rescheduling**: not exceeding the normal limit returns `400 LONG_BOOKING_NOT_NEEDED`; exceeding the resource's technical limit returns `400 DURATION_LIMIT`. An approved exemption is fixed to the original resource and interval. change/reschedule returns `409 LONG_BOOKING_NEW_REQUEST_REQUIRED`; cancel and submit a new request. Normal booking, additional-hours, and recurring entry points still cannot create a long booking.

## 1.21.0: Additional-Hours Requests (migration 012)

- **Separate submission**: `POST bookings/additional-hours/` with `{resource_id,start,end,purpose,additional_hours_reason,active_data_collection?,data_collection_reason?,on_behalf_of_zid?}`. Purpose and request reason are required; reason maximum is 1,000 characters. If active data collection is declared, an explanation is required (maximum 1,000 characters); if not declared, the explanation should be empty. Staff may book on behalf of someone else, with identity and permissions checked by the backend. Supports `Idempotency-Key`; changing reason, declaration, request type, or beneficiary requires a new key.
- **No hold**: success returns `201`, idempotent replay returns `200`, both with the complete Booking. Mark `additional_hours=true`, status `PENDING_APPROVAL`, and both `hold_until` and `review_due_at` null. A request can be submitted even if the time is currently occupied and does not block normal bookings while pending; approval must recheck availability. It is never auto-approved or promoted through the normal waitlist, and expires if unresolved at start time.
- **Separate quota**: requests may be submitted before the normal quota is exhausted. Additional requests and approved additional bookings do not consume the normal 12-hour weekly quota, but still count toward eight active future bookings. The three-hour per-booking limit, opening hours, qualification, and maximum 28-day advance window remain. Because this flow permits short-notice requests, the seven-day minimum does not apply.
- **Quota for the selected week (2026-11-10)**: an individual resource's `availability` response includes `week_hours` (`week_start`, `used_hours`, `limit_hours`) for the week containing `date` (Monday–Sunday, Sydney time). The booking dialog uses it to show “Week of 16 Nov: 2 h left of your 12 h.” Day overview `resources/day-overview/` does not include this field.
- **Availability**: `GET resources/{id}/availability/?date=YYYY-MM-DD&additional_hours=true`. The date range starts today in the resource's location, `min_advance_days=0`, and the normal maximum advance applies. Duration is still capped at the normal limit. Returns `additional_hours_approval_window_hours` (default 48, configurable) for the UI to show the approval window. Cannot combine with `urgent=true`.
- **Review information**: Booking adds `additional_hours_reason`, `active_data_collection`, `data_collection_reason`, and `additional_hours_review`; normal bookings have a null review field. Additional-booking review contains `approval_opens_at,approval_window_hours,priority_group,priority_reasons,queue_position,can_approve,blocker_code,blocker_message`. `can_approve` represents only real-time business conditions; the UI must also check Manager role, no self-review, and data-collection confirmation.
- **Fair ordering**: among currently approvable requests for the same resource with overlapping times, `NO_USE_THIS_WEEK` and `ACTIVE_DATA_COLLECTION` belong to the same `PRIORITY` group, followed by `STANDARD`. The former means no started, `CHECKED_IN` use across resources during the target booking's local Monday-to-Sunday week; the UI should say “No recorded lab use this week.” Active-data declarations receive provisional priority and must be verified by the Manager; invalid declarations should be rejected. Within each group, order by `created_at,id`. Existing bookings and normal active holds are never displaced by additional requests.
- **Manager decision**: reuse `POST admin/bookings/{id}/review/`. Only Manager can approve or reject and cannot review their own request or one they created. Approval must occur between `start - approval_window_hours` and start time. When data collection is declared, submit `confirm_active_data_collection=true`. Rejection requires `reason` and may happen before the approval window opens. Approval rechecks qualification, capacity, and queue inside the transaction. Audit records the basis, window, confirmation result, and authorised interval.
- **Errors and scope**: `ADDITIONAL_HOURS_TOO_EARLY`, `ADDITIONAL_HOURS_NO_CAPACITY`, and `ADDITIONAL_HOURS_QUEUE_PRIORITY` are 409. Missing data-collection confirmation is 400 `DATA_COLLECTION_CONFIRMATION_REQUIRED`. Approval authorises only the original resource and start/end. Normal change/reschedule endpoints return 409 `ADDITIONAL_HOURS_NEW_REQUEST_REQUIRED`; the UI tells the user to cancel and submit again.
- **Frontend entry point and tasks**: add Request additional hours to resource cards. My bookings distinguishes “waiting for Manager, no time held” from normal pending requests. The staff review page has an Additional hours tab showing priority basis, approval time, and blocking reason; Admin is read-only. `GET admin/overview/` adds `additional_hours_requests`, `additional_hours_ready`, and `can_decide_additional_hours`; normal pending counts exclude additional requests. Manager receives `ADDITIONAL_HOURS_REQUEST`; results and expiry use existing booking notifications.

## Frontend Responsibilities

| Page / interaction | Frontend responsibility | Backend responsibility |
| --- | --- | --- |
| Sign-in and role entry points | Student: university sign-in (mock SSO); Admin/Manager: staff sign-in page (zID + password, first activation with invitation code); store token and show menus by role | Validate identity and role; each sign-in path rejects the other account type; endpoint permissions |
| Resource and slot queries | Room/equipment filters, date and duration selection, slot display | Query resources, generate slots, check conflicts |
| Student dashboard | Show qualifications, booking statuses and counts; refresh results | Return current-student data and summary |
| Induction submission | Choose requirement, enter notes, upload file, show review result | Validate attachment, save submission, protect download permissions |
| Booking request | Choose resource and time, enter purpose, show server status after submission | Validate qualification gate, time rules, automatic/manual review |
| My bookings | Show details and reschedule/cancel confirmation; refresh after actions | Check ownership and status, revalidate and perform reschedule/cancel |
| Admin qualification review | Review list, view evidence, approve/reject with reason; show validity returned by backend | Change qualification and set validity automatically; on rejection, automatically reject the student's undecided bookings that depend on it (pending and waitlisted) |
| Admin booking review | Review queue and details, approve/reject with reason, show conflict errors | Recheck qualification and conflicts before approval |
| Notifications, calendar subscription, check-in | Top-bar bell; subscription link and I'm here button in My bookings | Generate notifications and subscription content; record absence |
| Recurring booking (staff) | Repeat weekly on resource card | Validate each date and directly approve recurring bookings |
| Audit records | Admin/Manager filters by resource, student, action, and time with pagination; booking details may show that booking's history | Record and query request, approval, reschedule, cancellation, and qualification-review history |
| People and role management (Manager only) | People list, role filters, Add staff | Manager-only; roles fixed after creation and cannot convert; no self-modification; keep at least one Manager; audit |
| Manager review period | Show and edit review period in minutes per resource | Role validation, rule persistence, and audit; Admin cannot read or edit |
| Resource management (Manager only) | Resources page: create, edit, archive, and restore rooms/equipment; show bookings that no longer satisfy new rules | Validate resource rules, save and audit; list affected bookings without cancelling automatically |
| Booking records and usage (Admin sees only last seven days; usage is Manager-only) | Booking Records: Records tab filters by date, resource, status, name/zID and exports CSV; Usage statistics tab shows per-resource values | Filter, export CSV, calculate booking count, duration, and attendance rate |
| Email notification | None (backend sends after the request) | Email booking holder according to `EMAIL_MODE`; see [email-setup.md](email-setup.md) |
| Change password (staff) | Form on Account | Validate current password and save new password hash |

Hiding buttons improves only the experience. Identity, qualification, and conflicts are enforced by the backend. The frontend cannot directly set booking status, qualification status, or user role.

Demo student registration requires `zid`, `display_name`, and `university_email`; a missing or malformed email returns 400. User objects in sign-in/registration responses and `auth/me/` include the email. Demo mode does not verify email ownership. Under production SSO, the backend must map email and role from a trusted identity source.

## Two Sign-In Entry Points (staff sign-in)

- **Student**: `POST auth/demo-login/` (mock university sign-in, zID only). A staff zID returns 403 `USE_STAFF_SIGN_IN`.
- **Admin/Manager**: `POST auth/staff-sign-in/` with `{"zid":"z9000002","password":"…"}`, returning the same `{access_token, user, …}` as student sign-in. Errors: 401 `INVALID_CREDENTIALS` (wrong zID or password), 403 `ACCOUNT_NOT_ACTIVATED`, 403 `ACCOUNT_DEACTIVATED`, and 403 `STUDENT_USES_SSO` (student used staff entry point).
- **First activation**: `POST auth/staff-activate/` with `{"zid":"…","invite_code":"K7Q4-9MZD","password":"at least 8 characters"}`. Invitation codes are case-insensitive and may omit the hyphen. Success signs in directly and invalidates the code. Errors: 400 `INVALID_INVITE_CODE`, 400 `VALIDATION_ERROR` (password too short), and 403 `ACCOUNT_DEACTIVATED`.
- **Invitation-code source**: after a Manager creates an account through Add staff, the staff member in `admin/users/` has `activation_status=AWAITING_ACTIVATION`, and `invite_code` is the invitation code. After activation, status becomes `ACTIVATED` and `invite_code` becomes `null`. Both fields are `null` for students.
- **Reset**: `POST admin/users/{id}/reset-access/` (Manager only; not for self and not for students, which returns 409 `STUDENT_USES_SSO`) invalidates the old password, creates a new invitation code, and returns the updated user.
- `staff_sign_in_enabled` from `auth/config/` indicates whether the staff entry point is available. Both entry points currently work only in demo mode (`DEBUG` + `ENABLE_DEMO_AUTH`) and will be replaced after university SSO integration.
- Demo accounts: z9000001 (Admin) and z9000002 (Manager), password `123`.

## Roles

- **Student**: book resources for themselves and upload their own induction evidence.
- **Admin** (staff): review induction and booking requests and view audits; **can also make bookings** for themselves or on behalf of others; cannot access Manager pages or endpoints (403).
- **Manager** (staff): all Admin permissions plus people, resource status, review-period, and all-booking management. **Only Manager can directly reschedule**, and only Manager can decide urgent requests.
- Everyone uses the same rule set: qualification (induction including prerequisites), opening hours, booking window, and conflict rules also apply to staff; induction cannot be bypassed. A normal request from any role may be auto-approved when its review period expires.
- Student, Admin, and Manager are separate account types fixed at creation. A student is not “promoted” to Admin, and Admin/Manager cannot switch between each other. A Manager creates staff accounts through Add staff; the university identity system may provide them later.

### Booking on Behalf of Others and Urgent Requests

- **Book on behalf of another person**: Admin/Manager adds `on_behalf_of_zid` to `POST bookings/`. The booking belongs to that person (`student_id`, checking **their** induction), while `created_by` records the creator and audit `BOOKING_CREATED` has the beneficiary in `details.booked_for`. A student sending this field receives 403 `FORBIDDEN`; unknown zID returns 404 `PERSON_NOT_FOUND`; inactive account returns 409 `ACCOUNT_INACTIVE`.
- Before submission, staff can confirm identity with `GET people/lookup/?zid=z1234567`. `GET resources/{id}/availability/?for_zid=...` returns `can_request`, `qualification_status`, and `requested_by_me` for the beneficiary, plus `booking_for`.
- Booking responses include `created_by`, `booked_for`, `created_by_user` (`id`, `zid`, `display_name`, `role`), and `on_behalf`. For staff, `GET bookings/` returns “for me” plus “created by me for others.” The beneficiary can also view and cancel it.
- A reviewer cannot approve a request “for themselves” or one they created (403 `SELF_REVIEW_FORBIDDEN`).
- **Urgent request**: `urgent: true` plus required `urgent_reason` (≤500 characters). Use only when start time is earlier than the minimum advance period (seven days by default); a date within the normal window returns 400 `URGENT_NOT_NEEDED`. The latest date still applies. The time must be free (conflict returns 409 `BOOKING_CONFLICT` without joining waitlist). Status is `PENDING_APPROVAL`, `reason_code=URGENT_AWAITING_MANAGER`, `review_due_at=null`, and `hold_until=start`: **only Manager can decide** (Admin receives 403 `URGENT_NEEDS_MANAGER`), it is never auto-approved, and expires if undecided before start. With `urgent=true`, availability shows times inside the minimum advance period as selectable.
- **Manager-only rescheduling**: other roles receive 403 `FORBIDDEN` from `POST bookings/{id}/reschedule/`. A Manager can reschedule any approved future booking without the date window, induction, weekly quota, or future-booking count (1.24.0; opening hours, resource maximum, and conflicts still apply), with `reason_code=RESCHEDULED_BY_MANAGER`.
- Awaiting client clarification: what “override an existing booking” specifically means, and whether only certain roles may submit urgent requests (currently everyone can submit; only Manager can approve).
- Users in the people list (`admin/users/`) include `is_staff` (`true` for Admin or Manager). The frontend uses `role` from `auth/me/`.

## Recommended Call Sequence

1. Read `GET auth/config/` to determine authentication mode. Students call `auth/demo-login/` or `auth/demo-register/`; Admin/Manager calls `auth/staff-sign-in/` (or `auth/staff-activate/` first), then uses the response token for `GET auth/me/`.
2. Call `GET resources/` and `GET qualification-requirements/` to display resources and their requirements.
3. A student views their qualifications through `GET qualifications/` or `GET dashboard/`. If no evidence was submitted for a requirement, show the upload entry point.
4. Call `POST qualifications/` with `multipart/form-data` fields `requirement_id`, `title`, `notes`, and `file`. Do not manually set the multipart Content-Type boundary; let the browser handle it.
5. Call `GET resources/{id}/availability/?date=YYYY-MM-DD&duration_minutes=60` to show slots, reading `can_request`/`qualification_status`. The date is the resource's local calendar date.
6. Call `POST bookings/` with `resource_id`, `start`, `end`, and `purpose`. Times must include a time zone, such as `2026-10-07T09:00:00+11:00`; never send a timezone-free string.
7. Show the result from response `status`, then refresh dashboard and availability. HTTP 201 means the request was created successfully; an idempotent replay returns 200. Only `APPROVED` means the booking is approved.
8. Admin reviews induction through `admin/qualifications/`; the review response includes `submission` and `updated_bookings`, so refresh related lists. Then use `admin/bookings/` to review bookings.

### Audit Records

`GET admin/audit/` is available only to Admin/Manager; students receive 403. It returns `{ count, limit, offset, results }`, where `count` is the total after filtering and before pagination, and `results` is newest-first. Each record includes `action`, `entity_type`, `entity_id`, `at`, `details`, and `actor` (`zid`, `display_name`, `role`; for automatic system processing, `actor_id` is `SYSTEM` and `actor` is `null`).

- Complete history of one booking: `?entity_id={booking_id}`.
- One resource: `?resource_id=...`, including records for all its bookings and hold-policy changes.
- One student: `?student_id=...`, including their actions and booking, evidence, and account records.
- Other filters: `action` (for example `BOOKING_CANCELLED`), `entity_type` (`booking|qualification|resource|principal`), `actor_id`, and `since`/`until` (timezone required; `until` exclusive).
- Pagination: `limit` 1–500, default 100; `offset` default 0. Unknown parameters return 400.

Fields in `details` vary by action; for example, booking creation has `status`, `reason_code`, and `hold_until`, while rescheduling has `old_start`/`new_start`. The frontend may display key-value pairs directly and must not depend on fixed fields.

### People and Role Management (Manager only)

Only a **Manager** can view the people list, create staff, change staff accounts, or deactivate accounts. Admin and students receive 403 from these endpoints.

- `GET admin/users/`: returns `{ count, results }`. Each item contains `id`, `zid`, `display_name`, `role`, `is_staff`, `active`, `university_email`, `inductions` (each induction's `name`, `status`: `NOT_SUBMITTED`/`PENDING`/`VERIFIED`/`REJECTED`/`EXPIRED`, and `valid_until`), and `induction_status` (`VERIFIED` when all are valid, otherwise `INCOMPLETE`). Staff can also book and likewise need valid induction. Filter by `role`, `active=true|false`, and `q` (matching zID/name/email).
- **Add staff**: `POST admin/users/staff/` with `{"zid":"z5123456","display_name":"…","university_email":"…","role":"ADMIN"}` (`role` is `ADMIN` or `MANAGER`). Success returns 201 with the user and writes `ADMIN_CREATED`/`MANAGER_CREATED` audit. Existing zID returns 409 `USER_EXISTS` (an existing student cannot become staff). Compatibility endpoint `POST admin/users/managers/` is equivalent to `role=MANAGER`.
- `PATCH admin/users/{id}/`: deactivate or reactivate an account (`active`). Role is fixed at creation and cannot change. A different `role` returns 409 `ROLE_CHANGE_NOT_ALLOWED`; the current role is ignored. To replace a person, create a new account through Add staff and deactivate the old one. The change takes effect on the user's **next request**; a deactivated user's next request receives 401, and the frontend should return to sign-in.
- **Deactivating a student** immediately rejects all their undecided requests (pending and waitlisted, `reason_code=ACCOUNT_DEACTIVATED`) and promotes the next request. Approved bookings remain for a Manager to decide whether to cancel.
- Self-modification is forbidden (`SELF_MODIFICATION_FORBIDDEN`, 403), and the system must retain at least one active Manager (`LAST_MANAGER`, 409). Every change writes a `USER_UPDATED` audit record.
- The list contains only users already known to the system (preloaded in the demo database or signed in/registered at least once).

`dashboard` returns `{ bookings, qualifications, counts }`. Both lists are arrays. Keys in `counts` are the seven uppercase booking statuses, such as `counts.APPROVED`; it is not a qualification count or total booking count. Other list endpoints use `{ count, results }`.

`qualification_status=NOT_CONFIGURED` means the resource has no induction requirement configured and cannot be requested; maintain the resource data before opening it. `qualification_status=PREREQUISITE_REQUIRED` means its induction requires another one first (for example, Advanced requires General). `missing_prerequisite_id` identifies the missing requirement, and the frontend can link directly to `/induction?requirement=<id>`.

### Induction Prerequisites

- Every item from `GET qualification-requirements/` contains `prerequisite_ids` (array). In demo data, Advanced laboratory training has General laboratory induction as its prerequisite.
- If a prerequisite is not verified, submitting evidence for the dependent requirement returns 409 `PREREQUISITE_REQUIRED` (`details.prerequisite_id`), and Admin approval returns the same error. The student page should say “Complete General first” and disable upload.
- When booking a resource that requires the dependent induction, **both the prerequisite and the target induction must be valid through the full booking**. Missing prerequisite makes `POST bookings/` return 403 `QUALIFICATION_REQUIRED` with `details.qualification_status=PREREQUISITE_REQUIRED`, `details.prerequisite_id`, and `details.prerequisite_status`.
- Manager can set `{"prerequisite_ids":["<uuid>"]}` through `PATCH admin/qualification-requirements/{id}/` (maximum 20, cannot include itself, cannot form a cycle: 409 `PREREQUISITE_CYCLE`), writing `REQUIREMENT_PREREQUISITES_UPDATED` audit.
- 1.16.0: each item also includes guidance `how_to_complete`, `accepted_evidence`, `reviewer`, and `contact` (empty string means unwritten). Induction & Training shows “How to get this induction” under each item. On **Lab setup** (`/manager/setup`), a Manager creates one through `POST admin/qualification-requirements/` (`name` required, other fields optional) and uses the same `PATCH` to edit `name`, `description`, and all four guidance fields (may be sent with `prerequisite_ids`). Names must be unique ignoring case (409 `REQUIREMENT_NAME_TAKEN`), and each guidance field is at most 2,000 characters. Copy changes do not affect verified users.

### Rooms and Equipment

A resource's `room_id` is the ID of the room containing equipment; it is `null` for a room itself. The frontend groups equipment by room (“N pieces of equipment in this room”). Maintenance/closure of a room **affects only the room itself**; equipment inside remains bookable according to its own `status`. Rooms and equipment are **booked separately**: booking a room does not include its equipment, and booking equipment does not reserve the room (stated in the UI from 1.16.0).

1.16.0: resources also have `capacity` (rooms only; number of people; `null` means unset) and `details` (`[{label, value}]`, Manager-defined “label: content” such as model and floor, maximum 12 rows). Resource cards show capacity and the first three rows; the booking form shows all. Room lists can filter by “at least N people” (rooms without capacity are not filtered out).

An availability query is a point-in-time snapshot; another user may occupy the time before or after submission. A slot with `available=false` must not say “book immediately.” A student may still request an occupied time, but will join the waitlist, which the UI must explain clearly. Each resource may have a different `required_qualification_id`; the frontend must read the resource requirement and cannot use one global “induction complete” flag for every resource.

`reason_code` in `slots[]` is `START_TIME_PASSED`, `RESOURCE_UNAVAILABLE` (maintenance/closed), `TOO_SOON` (less than seven days), `TOO_FAR_AHEAD` (beyond the default 28 days/four weeks), `BOOKED`, `TEMPORARILY_HELD`, or `null`. Top-level response also includes `earliest_date`, `latest_date`, `min_advance_days`, and `max_advance_days` for date-picker limits. A temporary hold returns `hold_until` (UTC deadline) and `held_by_me` (whether this student's own hold). `requested_by_me` means the current student already has an active overlapping request for the same resource; disable another submission. Other student identities are never returned. The UI may show a hold countdown and refresh at expiry; the server response is authoritative. `can_request` is `true` only when the current user is a student, the account is active, the required induction and prerequisites are verified and valid, and the resource is open; it does not guarantee approval for the selected time. When false, disable submission and prompt the user to complete induction. `review_window_minutes` is the resource's review period (default 1,440 minutes).

### Normal Booking Approval Flow

The automatic-decision and direct-rescheduling rules below apply to normal bookings. A long booking requires a manual Manager decision and expires if unresolved by its review deadline. Additional hours do not hold time and expire if unresolved at start. Neither special authorisation can be directly rescheduled; see the separate flows at the start of this document.

- **Only people with verified and valid induction may request** (also applies to staff). If evidence is under review (`PENDING`), rejected, or expired, `POST bookings/` returns 403 `QUALIFICATION_REQUIRED`, with the reason in `details.qualification_status`. Validity must cover the complete booking, otherwise `EXPIRES_BEFORE_END`. Only Admin/Manager manually reviews induction; approval never automatically approves a booking.
- **Every request first becomes `PENDING_APPROVAL`** (`reason_code=AWAITING_REVIEW`): it is not confirmed and does not write Outlook, but holds the time for the requester during the review period. `review_due_at` (same as `hold_until`) is the deadline: when entering pending, add the resource's `pending_hold_minutes` (24 hours by default), capped at booking start.
- **Admin/Manager approves or rejects before the deadline** (`POST admin/bookings/{id}/review/`; cannot review for themselves or a request they created; only Manager can decide urgent requests).
- **Still unresolved at deadline**: the system processes it automatically with `reviewed_by="SYSTEM"`. If account is active, qualification including prerequisites still covers the whole booking, resource is open, and no approved booking conflicts → `APPROVED` (`AUTO_APPROVED_AFTER_REVIEW_WINDOW`); otherwise `REJECTED` (`AUTO_REJECTED_ACCOUNT_INACTIVE`/`AUTO_REJECTED_QUALIFICATION`/`AUTO_REJECTED_RESOURCE_UNAVAILABLE`/`AUTO_REJECTED_BOOKING_RULES`/`AUTO_REJECTED_CONFLICT`) with the reason in `decision_reason`. The server processes this on the next access, through `admin/process-due/`, or scheduled command `manage.py process_due`; the frontend only refreshes.
- **One shared rule set**: creation, manual approval, automatic processing, waitlist promotion, and rescheduling use the same backend rule checks for consistent results.
- Rescheduling (Manager only): change date, time, and duration of an approved future booking (subject to latest date and qualification, but not minimum advance period), applying immediately. For slot selection pass `exclude_booking_id=<booking being changed>`, `for_zid=<booking holder>`, and `urgent=true`; the original time appears selectable.
- Manager sets a per-resource review period through `PATCH admin/resources/{id}/booking-policy/` with `{"pending_hold_minutes":1440}` (1–20,160 minutes).

**Room/equipment status**: `PATCH admin/resources/{id}/status/` (Manager only) with `{"status":"MAINTENANCE","reason":"Fume hood repair"}`. Status is `AVAILABLE`/`MAINTENANCE`/`CLOSED`; the latter two require a reason.
- Resource lists/details include `status` and `status_reason`. Maintenance/closed resources remain visible; the frontend should mark “under maintenance / closed” and the reason.
- During maintenance/closure: new requests return 409 `RESOURCE_UNAVAILABLE` (`details.resource_status`, `status_reason`); every slot query result is `RESOURCE_UNAVAILABLE` with `can_request=false`; no approval or promotion. **Existing bookings remain**. Response `affected_bookings` lists future bookings still requiring action; Manager can cancel each through `POST bookings/{id}/cancel/` (`reason_code=CANCELLED_BY_STAFF`). Returning to `AVAILABLE` automatically promotes the waitlist.

**Everyone's bookings**: `GET admin/bookings/` supports filters `status` (single, comma-separated multiple, or `ALL`), `resource_id`, `student_id`, `since`, and `until` (timezone-aware; returns bookings overlapping that interval), sorted by start time. Each item includes `student` (`id`, `zid`, `display_name`, `university_email`), `resource_name`, and `resource_kind`. Without parameters it returns the manual review queue. `GET admin/bookings/export/` (Manager only) exports CSV with the same filters (default `ALL`, UTF-8 with BOM for direct Excel opening). “Print” can invoke browser print on the frontend list page.

**Add staff** (top-right button on People management): see “People and Role Management” above. To remove a person, deactivate with `PATCH active=false` to preserve booking and audit history.

## Status and UI Copy

| Qualification status | Display meaning | Can request this resource? |
| --- | --- | --- |
| No submission | Submit induction evidence first | No |
| `PENDING` | Evidence awaiting staff review | No; request only after approval |
| Valid `VERIFIED` | Qualified for this resource | Yes |
| `REJECTED` or expired | Evidence rejected / qualification expired; submit again | No |

The latest submission determines current qualification. `status` is the evidence-review status; additional `effective_status` represents current validity and should be used to show expiry. Validity must cover booking end; being valid now does not guarantee coverage of the selected booking. A user cannot upload duplicate evidence for the same requirement while a PENDING submission or still-valid VERIFIED submission exists. They may resubmit after rejection or expiry.

**Validity**: on approval the backend automatically sets `valid_until = review time + QUALIFICATION_VALIDITY_DAYS`, default 120 days (about one term). Review requests do not accept `valid_until` (sending it returns 400); the review page only displays the response value. Student UI may show “Qualification valid until …” and explain that later bookings cannot be submitted. Early renewal is unavailable; upload again after expiry.

| Booking status | Suggested display | Blocks time? |
| --- | --- | --- |
| `PENDING_APPROVAL` | Awaiting staff review; show `review_due_at` and explain that the system applies the rules automatically after timeout | Holds during review (`hold_active=true`) |
| `WAITLISTED` | Waitlisted; show “Position `waitlist_position`” | No |
| `APPROVED` | Booking approved | Yes |
| `REJECTED` | Booking rejected | No |
| `CANCELLED` | Booking cancelled | No |
| `EXPIRED` | Request expired | No |

Every booking response includes `hold_until` (nullable deadline), `hold_active` (whether the hold is currently active), and `blocks_slot` (whether it currently blocks overlap). `APPROVED` has `blocks_slot=true` even when `hold_active=false`. Do not infer blocking from non-null `hold_until` alone: the value is retained for history, while the temporary hold ends after cancellation, rejection, or approval. `WAITING_QUALIFICATION` appears only in early data and is not produced by the current flow.

### First-In, First-Out and Waitlist

Overlapping requests for the same resource are processed strictly in submission order:

- **Time is free** (no approved booking and no other pending request): the new request becomes pending approval and holds the time.
- **Time is occupied**: the new request becomes `WAITLISTED` (`reason_code` is `TIME_CONFLICT` or `TEMPORARY_HOLD_CONFLICT`), does not hold time, and includes `waitlist_position` among overlapping waitlisted requests. Staff cannot directly approve a waitlisted request (`REQUEST_WAITLISTED`) but may reject it.
- **Promotion**: when time becomes free (cancellation, rejection, expiry, reschedule, or resource reopening), the backend takes the earliest submitted waitlisted request that fits. If it still satisfies rules → new `PENDING_APPROVAL` with `reason_code=PROMOTED_FROM_WAITLIST` and a recalculated review deadline, for Admin review or automatic timeout processing. Otherwise → `REJECTED` with the relevant error code such as `QUALIFICATION_REQUIRED` or `ACCOUNT_INACTIVE`. For partial overlaps, earlier submissions are checked first and receive the time if they fit.
- After the earlier request is approved, later requests remain `WAITLISTED` as backups. If the approved booking is later cancelled by the holder or Admin/Manager, the next request is promoted. A waitlisted request still unpromoted at booking start becomes `EXPIRED`.
- Promotion does not proactively notify. Students must refresh My bookings or dashboard to see changes; the frontend may poll.

**Limits**:
- **Booking window**: booking start date in the resource's local date must be between “today + 7 days” and “today + 28 days” (defaults from configurable backend `RulesProvider`; see “Configurable Rules” in backend/README), meaning at least one week and at most four weeks ahead. The maximum applies to all roles, proxy bookings, and every actual date in a staff recurring series. Example: on Saturday 10/10, earliest is Saturday 10/17 and latest is 11/7. Too near returns 400 `BOOKING_TOO_SOON`; too far returns 400 `BOOKING_TOO_FAR_AHEAD`. Both `details` contain `earliest_date`, `latest_date`, `min_advance_days`, and `max_advance_days`. Booking-holder time-change requests follow the same window. A direct Manager reschedule skips the minimum but still obeys the latest date. Existing requests are unaffected and continue through review and promotion as the date approaches.
  - Date picker: set `<input type="date" min max>` from `earliest_date`/`latest_date` in the availability response; do not hard-code day counts in the frontend.
  - Because the minimum is one week, the default 24-hour review deadline always precedes booking start. It is capped at booking start only when a Manager configures a review period longer than the advance period.

A `TEMPORARILY_HELD` slot may display “Another request is under review” and `hold_until`. A student may still submit and will join the waitlist. Refresh and idempotent replay do not extend the hold.

Example (default 24 hours): Monday 10:00, qualified A requests next Monday 10:00–12:00, becomes pending and holds until Tuesday 10:00 → Monday 11:00, B requests the same time and becomes waitlist position 1 → if Admin rejects A before Tuesday 10:00, B immediately becomes pending with a new 24-hour period; if nobody acts, A auto-approves Tuesday 10:00 and B remains waitlisted as backup → if A later cancels or is cancelled by Manager, B is promoted to pending.

**When evidence is rejected** (for example, resubmitted after qualification expiry): the backend automatically rejects all undecided bookings (`PENDING_APPROVAL` and `WAITLISTED`) by that student for resources requiring this qualification and promotes waitlisted requests into freed time. Status becomes `REJECTED`, `reason_code=QUALIFICATION_REJECTED`, `decision_reason` is the evidence rejection reason, and time is released immediately. Review response `updated_bookings` includes these bookings. Student UI should show: evidence rejected and reason (`rejection_reason`) → related bookings rejected → guide the student to upload again and rebook after approval or resubmission.

The review deadline never falls after booking start. A request still unapproved after start becomes `EXPIRED`.

## API Quick Reference

All paths below start with `/api/v1/`. A Bearer token is required except for health, authentication configuration, sign-in, registration, and staff activation. List endpoints consistently return `{ "count": 0, "results": [] }`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `health/` | Service status |
| GET | `auth/config/` | Current authentication configuration |
| POST | `auth/demo-register/` | Create a local student account: `zid`, `display_name`, `university_email` |
| POST | `auth/demo-login/` | Simulated university sign-in for students: `zid` (staff are rejected) |
| POST | `auth/staff-sign-in/` | Admin/Manager sign-in: `zid`, `password` |
| POST | `auth/staff-activate/` | First-time staff activation: `zid`, `invite_code`, `password` |
| GET | `auth/me/` | Current user |
| GET | `resources/?kind=ROOM&q=lab&category=` | Filter resources; `kind` may also be `EQUIPMENT`; `category` is the equipment category |
| GET | `resources/day-overview/?date=YYYY-MM-DD&duration_minutes=60` | Booking page "Find a free time": availability for all matching resources on that day (see below) |
| GET | `resources/{id}/` | Resource details |
| GET | `resources/{id}/availability/?date=YYYY-MM-DD&duration_minutes=60` | Availability and request eligibility; staff may add `for_zid`, and urgent requests add `urgent=true` |
| GET | `people/lookup/?zid=` | Staff only: confirm the other person's account before booking on their behalf |
| GET | `qualification-requirements/` | List of induction requirements |
| GET / POST | `qualifications/` | My submissions/upload evidence |
| GET | `qualifications/{id}/` | Evidence-submission details |
| GET | `qualifications/{id}/file/` | Permission-protected attachment download |
| GET / POST | `bookings/` | My booking list (staff also see bookings they created for others)/create a booking (may include `on_behalf_of_zid`, `urgent`, `urgent_reason`) |
| POST | `bookings/{id}/change/` | 1.16.0: the booking holder requests a new time for their approved booking (see "Request a Time Change" below) |
| POST | `bookings/{id}/extend/` | The holder requests an extension to an approved booking in progress (`end`; requires Manager approval from 1.27.0); a Manager call takes effect immediately |
| POST | `bookings/{id}/extend/review/` | 1.27.0, Manager only: approve or reject an extension request using `decision`, `reason` |
| GET / PATCH | `site/contact/` | 1.16.0: laboratory contact details; everyone can read, Manager can edit |
| POST | `admin/qualification-requirements/` | 1.16.0: Manager creates an induction |
| GET | `admin/overview/` | 1.16.0: counts and lists for the staff Today page |
| GET | `bookings/{id}/` | Booking details |
| POST | `bookings/{id}/cancel/` | Cancel a booking |
| POST | `bookings/{id}/reschedule/` | Manager only: reschedule an approved booking that has not started: `start`, `end` |
| GET | `dashboard/` | My bookings, evidence, and counts; `week_hours` contains the current week's booked `used_hours` and weekly `limit_hours` (Monday to Sunday in Sydney time), excluding additional hours (1.23.0) |
| GET | `admin/qualifications/?status=PENDING` | Administrator qualification queue (`PENDING`/`VERIFIED`/`REJECTED`); each item includes `student` (`id`, `zid`, `display_name`, `university_email`), so the review page can show the name and zID directly |
| POST | `admin/qualifications/{id}/review/` | `decision: VERIFIED\|REJECTED`, optionally with `reason`; does not accept `valid_until`, which is set by the backend |
| GET | `admin/bookings/?status=PENDING_APPROVAL` | Pending-review queue by default; use `status=WAITLISTED` for the waitlist; use `status=ALL&resource_id=&student_id=&q=&since=&until=` for everyone's bookings (with student and resource names); `q` is a case-insensitive part of the holder's or creator's zID or name |
| GET | `admin/bookings/export/?status=ALL` | Admin/Manager: export CSV using the same filters (including `q`); the final two columns are Weekly series and Attendance |
| POST | `admin/bookings/{id}/review/` | `decision: APPROVED\|REJECTED`, optionally with `reason`; waitlisted requests can be rejected but not approved |
| GET | `admin/users/?role=&active=&q=` | Manager only: people list |
| POST | `admin/users/staff/` | Manager only: Add staff with `zid`, `display_name`, `university_email`, and `role` (`ADMIN`/`MANAGER`); response includes `invite_code` |
| POST | `admin/users/{id}/reset-access/` | Manager only: reset staff sign-in and generate a new invite code |
| POST | `admin/users/managers/` | Manager only: compatibility endpoint equivalent to selecting Manager in Add staff |
| PATCH | `admin/users/{id}/` | Manager only: `{"active":false}` deactivates/`{"active":true}` restores; role cannot be changed |
| PATCH | `admin/qualification-requirements/{id}/` | Manager only: set prerequisite inductions with `{"prerequisite_ids":[...]}` |
| GET | `admin/audit/?resource_id=&student_id=&action=&since=&until=&limit=100&offset=0` | Admin/Manager view audit records (requests, reviews, rescheduling, cancellation, and so on), newest first |
| POST | `admin/process-due/` | Immediately process requests whose review deadline or start time has arrived (automatic approval or rejection) |
| GET / PATCH | `admin/resources/{id}/booking-policy/` | Manager only: read and modify the review period `pending_hold_minutes` |
| PATCH | `admin/resources/{id}/status/` | Manager only: `AVAILABLE`/`MAINTENANCE`/`CLOSED` + `reason` |
| GET | `admin/outlook/` | Admin/Manager: Outlook configuration, statistics, and per-booking sync/check status (does not call Microsoft) |
| POST | `admin/outlook/check/` | Test Microsoft sign-in and calendar permission, `{}` |
| POST | `admin/outlook/process/` | Process waiting calendar updates, `{"limit":1}` (maximum 5) |
| POST | `admin/bookings/{id}/outlook-retry/` | Immediately retry a failed calendar update, `{}` |
| POST | `bookings/{id}/check-in/` | Booking holder confirms attendance (I'm here), `{}` |
| POST | `bookings/series/preview/` | Staff: preview every date in a recurring booking |
| POST | `bookings/series/` | Staff: create recurring bookings (approved directly); `skip_dates` lists dates to skip |
| GET | `bookings/series/{id}/` | Recurring series and its individual bookings (staff or beneficiary) |
| POST | `bookings/series/{id}/cancel/` | Staff: cancel all remaining dates in a series |
| GET | `calendar/link/` | My calendar subscription address (generated on first call) |
| POST | `calendar/link/reset/` | Generate a new subscription address and immediately invalidate the old one |
| GET | `calendar/{token}.ics` | Subscription content (iCalendar), no sign-in required |
| GET | `notifications/?unread=&limit=50` | My notifications, newest first, with `unread_count` |
| POST | `notifications/{id}/read/` | Mark as read |
| POST | `notifications/read-all/` | Mark all as read |
| GET | `notifications/preferences/` | My five in-app/email switches and the site's email capability; see 1.19.0 |
| PUT | `notifications/preferences/` | Save switches: `{"preferences": {"bookings": true, "reminders": false}}`; unknown categories return 400 |
| GET / POST | `admin/resources/` | Manager only: all resources (including archived ones)/create a room or equipment item |
| PATCH | `admin/resources/{id}/` | Manager only: edit a resource (send only changed fields); returns `resource` and `bookings_outside_rules` |
| POST | `admin/resources/{id}/archive/`, `…/restore/` | Manager only: archive/restore, `{}` |
| GET | `admin/reports/usage/?first_date=&last_date=` | Manager only (1.26.0): usage report |
| GET / PATCH | `admin/resources/{id}/internal/` | Manager only (1.26.0): equipment custodian, UNSW asset number, source, and specifications |
| POST | `auth/change-password/` | Admin/Manager: change their own password using `current_password`, `new_password` |

`POST bookings/` may include `Idempotency-Key`. Reuse the same key when the same user retries the same request; generate a new key for a different booking. A key may be at most 128 characters and may contain only letters, numbers, periods, underscores, colons, and hyphens. Do not rely only on disabling the button to prevent duplicate requests. The `start` and `end` fields represent the interval `[start,end)`. Cancellation is allowed only for active requests that have not started; repeating cancellation of an already cancelled record returns the original record. Only a Manager may reschedule a future `APPROVED` booking; the backend rechecks time rules, qualification validity, and conflicts. On success, `revision` increases and the original Outlook event is updated.

Slot queries default to 30 minutes. Ordinary bookings use 30-minute fair-use slots and may select at most six slots (three hours); the resource itself may define a shorter technical limit. Resource and availability responses return `booking_slot_minutes`, `max_booking_slots`, `selection_step_minutes`, and `effective_max_booking_minutes`; the frontend must use these server values to limit selection. A booking cannot cross a local calendar-day boundary.

The Manager rules page sends `PATCH admin/resources/{id}/booking-policy/` with `{"pending_hold_minutes":1440}` (the field name follows the database column and represents the review period in minutes). Both GET and PATCH return `{"resource_id":"<uuid>","pending_hold_minutes":1440}`. The value must be an integer from 1 to 20,160 and defaults to 1,440 (24 hours). If nobody acts before the deadline, an ordinary booking is automatically approved or rejected according to the rules, while a long booking expires and releases the time. A change affects only requests that enter pending review afterward; existing deadlines do not change. Resource details include `pending_hold_minutes`, and slot-query responses include the same value as `review_window_minutes`. The request must contain `pending_hold_minutes`; sending `auto_approve_max_minutes` returns 400.

Attachments support PDF, PNG, and JPEG and may be at most 5 MiB. The backend checks size, extension, MIME type, and file-format signatures. The `file_url` in evidence is a protected API path, and downloads still require Authorization. The frontend may request it as a Blob for display/download; it must not assume that `<img src>` or an ordinary link automatically includes the Bearer token. Attachments have no public address.

## Errors and Time

Errors consistently use this format:

```json
{
  "error": {
    "code": "BOOKING_CONFLICT",
    "message": "This time slot is already booked.",
    "details": {}
  }
}
```

The frontend handles errors according to `error.code` and HTTP status rather than relying on fixed English message text. `details` may contain field errors or conflict information. User-facing messages must not disclose another student's information.

| HTTP status | Frontend handling |
| --- | --- |
| 400 | Show field, time, or file-validation errors |
| 401 | Session expired; sign in again |
| 403 | Insufficient permission or evidence-submission requirements are not met |
| 404 | Record does not exist or is inaccessible to the current identity |
| 409 | Conflict, duplicate request, or action invalid in the current state; refresh data |

Common business errors:

| `error.code` | HTTP | Frontend action |
| --- | --- | --- |
| `QUALIFICATION_REQUIRED` | 403 | Submission is allowed only when the induction has been verified and remains valid; when `details.qualification_status` is `PENDING`, show "Evidence is under review; you can book after approval"; otherwise direct the user to upload evidence |
| `QUALIFICATION_NOT_VERIFIED` | 409 | An administrator must process the qualification first; the booking cannot be approved directly. `details.qualification_status` explains why (including `PREREQUISITE_REQUIRED`) |
| `ACCOUNT_INACTIVE` | 409 | The applicant's account is inactive, so the request cannot be approved and staff cannot book for them |
| `PERSON_NOT_FOUND` | 404 | The zID supplied for a proxy booking does not exist |
| `URGENT_REASON_REQUIRED` | 400 | An urgent request requires a reason |
| `URGENT_NOT_NEEDED` | 400 | The time is inside the ordinary booking window; submit an ordinary request |
| `URGENT_NEEDS_MANAGER` | 403 | Only a Manager may decide an urgent request |
| `BOOKING_CONFLICT` | 409 | Manual approval or urgent request failed because the time already has an approved booking (for urgent requests, this also includes a pending-review hold) |
| `BOOKING_HOLD_CONFLICT` | 409 | Manual approval failed because the time is still temporarily held; `details.hold_until` is the current hold deadline |
| `REQUEST_WAITLISTED` | 409 | A waitlisted request cannot be approved directly and will be promoted automatically in order; an administrator may reject it |
| `SELF_REVIEW_FORBIDDEN` | 403 | A person cannot review their own induction evidence or a booking request for themselves or created by them; assign it to another Admin or Manager |
| `RESOURCE_POLICY_NOT_CONFIGURED` | 409 | The resource has no required induction configured and cannot currently be booked; tell the user to contact a Manager |
| `RESOURCE_UNAVAILABLE` | 409 | Resource is under maintenance or closed; show `details.status_reason` and pause new bookings |
| `USER_EXISTS` | 409 | The zID already exists when using Add staff |
| `USE_STAFF_SIGN_IN` | 403 | Staff used student sign-in; direct them to the staff sign-in page |
| `STUDENT_USES_SSO` | 403/409 | A student used staff sign-in (or staff access reset was attempted for a student); direct them to university sign-in |
| `INVALID_CREDENTIALS` | 401 | Staff sign-in zID or password is incorrect |
| `ACCOUNT_NOT_ACTIVATED` | 403 | Staff have not activated the account with an invite code |
| `INVALID_INVITE_CODE` | 400 | zID or invite code is incorrect; ask a Manager for a new code |
| `ACCOUNT_DEACTIVATED` | 403 | Account is inactive |
| `ROLE_CHANGE_NOT_ALLOWED` | 409 | A role is fixed after account creation; Student/Admin/Manager cannot be converted into one another |
| `PREREQUISITE_REQUIRED` | 409 | Complete the prerequisite induction (such as General) before submitting or approving this one; see `details.prerequisite_id` |
| `PREREQUISITE_CYCLE` | 409 | The prerequisite configuration would create a cycle |
| `FORBIDDEN` | 403 | A student tried to book for someone else, a non-Manager tried to reschedule, or an Admin called a Manager endpoint |
| `BOOKING_TOO_SOON` | 400 | Booking must be made at least seven days ahead; `details.earliest_date` is the earliest bookable date |
| `BOOKING_TOO_FAR_AHEAD` | 400 | By default, booking is limited to 28 days (four weeks) ahead; `details.latest_date` is the latest bookable date |
| `QUALIFICATION_ALREADY_PENDING`/`QUALIFICATION_ALREADY_VERIFIED` | 409 | Keep the current evidence and refresh qualification status |
| `IDEMPOTENCY_CONFLICT` | 409 | The same key cannot be used for a different request; generate a new key for a new action |
| `DUPLICATE_BOOKING` | 409 | The current student already has an active overlapping request for the same resource; show the existing request instead of adding another waitlist entry |
| `REQUEST_NOT_REVIEWABLE`/`ALREADY_REVIEWED` | 409 | Queue state has changed; refresh the list |
| `REQUEST_NOT_CANCELLABLE` | 409 | The booking has started or the request has ended; refresh the booking |
| `REQUEST_NOT_RESCHEDULABLE` | 409 | Only a future approved booking may be rescheduled; refresh the booking |
| `INVALID_TIME`/`INVALID_TIME_INCREMENT`/`INVALID_SLOT_COUNT`/`OUTSIDE_OPENING_HOURS`/`DURATION_LIMIT` | 400 | Correct the time according to the resource and ordinary-booking slot rules |
| `VALIDATION_ERROR` | 400 | Display `details` errors beside the corresponding fields, including attachment format/size problems |
| `TOKEN_EXPIRED`/`INVALID_TOKEN` | 401 | Sign in again |
| `WEEKLY_LIMIT_REACHED` | 409 | Active requests in the week plus this request would exceed 24 half-hour slots; read `limit_slots`, `used_slots`, `requested_slots`, `remaining_slots`, `slot_minutes`, and `week_start` |
| `FUTURE_BOOKING_LIMIT_REACHED` | 409 | The person already has eight active future bookings; read `limit`, `used`, `requested`, and `remaining`, then guide the user to cancel one they no longer need |
| `RESOURCE_NAME_TAKEN` | 409 | Resource management: another unarchived resource already uses this name |
| `KIND_IS_FIXED` | 409 | Resource management: a room cannot be changed into equipment or vice versa; create a new resource and archive the old one |
| `RESOURCE_HAS_BOOKINGS`/`ROOM_HAS_EQUIPMENT` | 409 | Archiving rejected because future bookings remain (`details.booking_count`) or the room still contains equipment (`details.equipment`) |
| `CHECK_IN_NOT_OPEN`/`CHECK_IN_CLOSED` | 409 | Check-in has not opened (`details.check_in_opens_at`) or has already closed |
| `SERIES_TOO_LONG`/`SERIES_EMPTY` | 400 | Recurring-booking pattern exceeds 14 weeks/no dates match |
| `SERIES_CONFLICT` | 409 | Problem dates were not included in `skip_dates`; preview again |

A conflicting request submitted by a student returns 201 with `WAITLISTED`. `BOOKING_CONFLICT` is the error returned when an administrator tries to approve a request that still conflicts. Do not present "received 201" or "waiting for an administrator" as approval.

API output times use ISO 8601 UTC `Z`. The frontend displays them in `Australia/Sydney` with daylight-saving support; do not hard-code `+10:00` year-round. The availability `date` is a calendar date in the resource's timezone, while times in `slots` remain UTC. The frontend should label the local timezone.

Booking-related reads and actions cause the server to advance due states (automatic decisions after review deadlines, expiry, and waitlist promotion), so the browser does not need its own timer. The screen updates only through polling or user refresh; real-time notification after manual review has not yet been implemented.

## Boundary with Future Integrations

The frontend calls only the API. It does not read the database or connect directly to Outlook. The backend's `Repository` adapter handles the database (memory or PostgreSQL). When university SSO is integrated later, the backend will verify identity and map users. The interface structure and states remain unchanged when these integrations are added.

Demo identity selection is enabled only in local development mode and does not represent production SSO. A production frontend must not retain a demo entry point that signs in with an arbitrary zID or selects an administrator identity. In-memory data is lost when the backend restarts and cannot be shared across multiple backend processes; use PostgreSQL mode when data must persist.

## Calendar Subscription Link

- `GET calendar/link/` returns `{ path, created_at }`. `path` is relative (for example, `/api/v1/calendar/<random-code>.ics`). The frontend appends it to `window.location.origin` to create a full address for the user to copy.
- In Outlook, the user selects "Add calendar → Subscribe from Internet" and pastes the address; no Microsoft sign-in is required. Google Calendar and Apple Calendar also support it.
- The subscription contains **approved** bookings for which the user is the beneficiary (including bookings created for them by staff), starting with bookings that ended 60 days ago. Each booking has a stable UID (`<booking ID>@smartlab`); a reschedule is an update, and a cancelled booking disappears.
- The random code in the address is the only key. `POST calendar/link/reset/` generates a new address and makes the old one return 404 immediately. The page should warn the user not to share the link.
- Update frequency is controlled by the calendar application and may take several hours.

## In-App Notifications

- `GET notifications/` returns `{ count, unread_count, results }`, newest first. `unread=true` returns only unread items, and `limit` is 1–200 (default 50). `unread_count` counts all unread in-app-visible records and excludes email-only records (Sprint 3, 1.19.0).
- Each record contains `kind`, `title`, `body`, `created_at`, `link` (an in-app page such as `/bookings`, `/induction`, or `/admin/bookings`), `booking_id`, and `read_at`.
- Events that generate notifications:
  - For the booking holder: `BOOKING_SUBMITTED` (their request was received and is now pending or waitlisted), `BOOKING_APPROVED`, `BOOKING_REJECTED` (including automatic system decisions, ineligibility during waitlist promotion, and related rejection after evidence is rejected), `BOOKING_PROMOTED` (waitlist to pending review), `BOOKING_RESCHEDULED`, `BOOKING_CANCELLED` (cancelled by staff), `BOOKING_CREATED_FOR_YOU`, `SERIES_CREATED` (staff's own recurring series), `SERIES_CREATED_FOR_YOU`, `QUALIFICATION_VERIFIED`/`QUALIFICATION_REJECTED`, `NO_SHOW_RECORDED`, and reminders: `BOOKING_REMINDER` (24 hours before an approved booking starts, reminding the user to select I'm here), `INDUCTION_EXPIRING` (a verified induction expires within 14 days, linking to `/induction?requirement=…`), and `BOOKING_EXPIRED` (a waitlisted or pending request reaches its start without promotion or a decision). Each reminder is sent once.
  - For a Manager: `URGENT_REQUEST`.
  - Added in 1.16.0: `CHANGE_REQUESTED`/`CHANGE_APPROVED`/`CHANGE_REJECTED` (time-change request), `RESOURCE_OUT_OF_SERVICE` (a resource with one of the user's bookings or requests enters maintenance or closes, including the Manager's reason; one per booking), and `RESOURCE_REOPENED`. These are also among the default email types.
- Ordinary new requests do not notify administrators, who use the review queue. A user's own cancellation does not notify them.
- Frontend: the top-bar bell displays the unread count and loads on page open, on returning to the page, and every 60 seconds. Selecting an item calls `POST notifications/{id}/read/` and navigates to `link`; "Mark all as read" uses `POST notifications/read-all/`. Navigate only to in-app paths.
- Email: after the backend email channel is enabled (`EMAIL_ENABLED=true`), the booking outcomes, reminders, and confirmation notifications listed above are also sent to the booking holder's university email. See [email-setup.md](email-setup.md). Email delivery also depends on the user's `email` preference for that category; email type and site configuration still apply. See 1.19.0 below for the independent-channel interface.

## Attendance Confirmation

- Booking responses now include `attendance` (`CHECKED_IN`/`NO_SHOW`/`EXCUSED`/`NOT_TRACKED`/`null`), `checked_in_at`, `check_in_open`, `check_in_opens_at`, and `check_in_closes_at`.
- When `check_in_open=true` and the current user is the booking holder (`student_id`), My Bookings displays an **I'm here** button that calls `POST bookings/{id}/check-in/` (`{}`). By default, the window runs from 15 minutes before the start until 30 minutes after the start, without extending beyond the end. Another user receives 404; too early returns 409 `CHECK_IN_NOT_OPEN`, and too late returns 409 `CHECK_IN_CLOSED`.
- If the user has not confirmed by the end of the window, the server records `NO_SHOW`. If the resource was under maintenance or closed during that time, it records `EXCUSED`, which is not a no-show.
- A no-show is only recorded and reported to the holder (`NO_SHOW_RECORDED`, reminding them to cancel next time); there is no penalty. Version 1.25.0 removed freezing: `auth/me/` no longer has `no_show_count`, `frozen_until`, or `booking_frozen`; slot queries no longer have `frozen_until`; and all unfreeze endpoints have been removed. Cancelled bookings with `reason_code=ACCOUNT_FROZEN` in old data continue to display normally.

## Weekly Limit

- One beneficiary may occupy at most 24 half-hour slots (12 hours) in one week, Monday through Sunday in the resource's local time. Pending, waitlisted, approved, and staff-created recurring bookings all count by their actual duration. If the limit would be exceeded, `POST bookings/` returns 409 `WEEKLY_LIMIT_REACHED`; details include `limit_slots`, `used_slots`, `requested_slots`, `remaining_slots`, `slot_minutes`, and `week_start`. The same rule applies when a Manager reschedules into an over-limit week.
- Slots are released automatically after cancellation, rejection, or expiry. A proxy booking counts against the beneficiary. The server recalculates the allowance within the same database transaction, so concurrent submissions cannot bypass it.

## Active Future Booking Limit

- One beneficiary may hold at most eight active bookings that have not started. `PENDING_APPROVAL`, `WAITLISTED`, `APPROVED`, and every date in a recurring series all count. A ninth request returns 409 `FUTURE_BOOKING_LIMIT_REACHED`.
- A place is released automatically after cancellation, rejection, expiry, or reaching the start time. Proxy and urgent bookings count against the beneficiary. An approved booking and its pending change request count as one in total, and an in-place Manager reschedule does not consume another place.
- The server recounts within a database transaction while locking the beneficiary record. The default eight comes from `MAX_ACTIVE_FUTURE_BOOKINGS` and can be adjusted with client policy.

## Recurring Bookings (Staff Only)

- The **Repeat weekly** button on a resource card (visible only to Admin/Manager) opens a form for the beneficiary (self or another person by zID), weekdays (1=Monday … 7=Sunday), start time, duration, first and last dates (pattern span is at most 14 weeks; each actual booking date remains subject to the current booking window), and purpose.
- First call `POST bookings/series/preview/` with `resource_id`, `weekdays`, `start_time` such as `"09:00"`, `duration_minutes`, `first_date`, `last_date`, and optional `on_behalf_of_zid`. It returns `available` and `reason_code` for each date.
- Then call `POST bookings/series/` with the same fields plus `purpose` and `skip_dates`. Every unavailable date from the preview must be included in `skip_dates`, otherwise the endpoint returns 409 `SERIES_CONFLICT` and the user must preview again. Conflicting dates do not join the waitlist.
- After creation, each date is immediately `APPROVED` (`reason_code=SERIES_CREATED_BY_STAFF`, with `series_id`) and does not enter review. Whether staff book for themselves or someone else, each date must satisfy the current booking window (seven to 28 days ahead by default). Preview entries later than the latest date show `BOOKING_TOO_FAR_AHEAD` and must be included in `skip_dates` at creation. The 14-week limit applies only to the pattern span and does not extend bookable dates. Other rules are checked normally. Each retained date counts against the corresponding week's 24-slot limit and the eight-active-future-booking limit; over-limit preview dates show `WEEKLY_LIMIT_REACHED` or `FUTURE_BOOKING_LIMIT_REACHED` respectively. Attendance confirmation is still required.
- Cancel one occurrence with `POST bookings/{id}/cancel/`; staff cancel all remaining dates with `POST bookings/series/{id}/cancel/`. `GET bookings/series/{id}/` returns every date in the series.

## Resource Management (Manager Only)

The **Resources** page is at `/manager/resources`. All rules live in backend `booking/services/resources.py`; frontend `features/manager/resource-form.ts` only provides the same messages earlier.

- `GET admin/resources/`: all resources, including archived resources (`active=false`). Ordinary `GET resources/` returns only unarchived resources.
- `POST admin/resources/`: `kind` (`ROOM`/`EQUIPMENT`), `name`, `location`, and `required_qualification_id` are required. Optional fields are `description`, `room_id`, `category` (equipment only), `slot_minutes` (15/30/60; default 30), `max_booking_minutes` (default 480), `opening_time`/`closing_time` (`"HH:MM"`; defaults 08:00/20:00), and `pending_hold_minutes` (default 1440). Success returns the resource with 201.
- `PATCH admin/resources/{id}/`: send only fields to change. Returns `{resource, bookings_outside_rules}`. The latter lists future bookings that no longer fit the new rules (each booking includes `student`, `resource_name`, and a `problem` such as `OUTSIDE_OPENING_HOURS`). They are **not cancelled automatically**; the page should prompt the Manager to handle them. Sending `kind` returns 409 `KIND_IS_FIXED`.
- `POST admin/resources/{id}/archive/`: archive with `{}`. It is rejected when future bookings remain (409 `RESOURCE_HAS_BOOKINGS`) or the room still contains unarchived equipment (409 `ROOM_HAS_EQUIPMENT`). `POST …/restore/` restores the resource, provided its name is still available.
- Validation errors use 400 `VALIDATION_ERROR`; `details` contains the invalid field names, for example `{"max_booking_minutes": ["…"]}`.

## Booking Records and Usage (Manager; Admin Sees Only the Last Seven Days of Records)

The **Booking Records** page (`/admin/records`) has two tabs:

- **Records**: `GET admin/bookings/?status=ALL&since=&until=&resource_id=&q=`. Dates are Sydney local dates, which the frontend converts to timezone-aware times (`since` is midnight at the start of the first date; `until` is midnight after the last date). Table columns are time, resource, beneficiary (name and zID), creator (Self when `on_behalf` is false), status, and attendance. **Export CSV** calls `admin/bookings/export/` with the same parameters, so the CSV matches the table.
- **Usage statistics** (`?tab=usage`; the old `/manager/usage` address redirects here): see below.

### Usage Report

`GET admin/reports/usage/?first_date=2030-01-01&last_date=2030-01-28` (inclusive local dates, maximum 366 days) returns `{first_date, last_date, days, results, totals}`. Each row in `results` represents a resource and contains `approved`, `booked_hours`, `open_hours`, `utilisation` (0–1), `checked_in`, `no_show`, `excused`, `not_tracked`, `attendance_rate` (`null` when it cannot yet be calculated), `cancelled`, `rejected`, and `name`, `kind`, `category`, `room_name`, `active`. Attendance figures count only approved bookings that have ended.

## Change Password (Admin/Manager)

The Account-page form calls `POST auth/change-password/` with `{"current_password": "…", "new_password": "…"}` and returns `{"changed": true}` on success. An incorrect current password returns 400 `INVALID_CREDENTIALS`; a new password shorter than eight characters or identical to the current password returns 400 `VALIDATION_ERROR`; a student receives 403 `STUDENT_USES_SSO`.

## Booking-Page Filters and Day Availability Table

The Book a Resource page has two tabs: **Browse resources** (resource cards) and **Find a free time**. The latter lets the user choose conditions, view all matching resources' availability for the day in one table, and select a free time to open the booking form with the resource and time already selected.

- A resource has `category` (equipment category, such as `Microscopy`, `Electronics testing`, or `Fabrication`; rooms use `null`). Demo categories are placeholders and should later be replaced with the client's equipment list. `GET resources/` also accepts a `category=` filter.
- Parameters for `GET resources/day-overview/`:
  - `date`: required Sydney local date.
  - `duration_minutes`: default 60. From 1.16.0, when a resource cannot be booked for this duration (it exceeds the resource maximum or is not a multiple of its time increment), that resource is omitted and counted in `too_long` instead of causing the entire request to return 400.
  - `kind`: `ROOM`/`EQUIPMENT`.
  - `room_id`: the room itself plus equipment located in that room.
  - `category`: equipment category.
  - `q`: search by name, location, or category.
  - `bookable_only=true`: return only resources the current user can request now.
  - `free_at=HH:MM`: return only resources that are free for the full duration starting at this time.
- Response contents:
  - `date`, `duration_minutes`, `timezone`
  - Booking window: `earliest_date`, `latest_date`, `min_advance_days`, `max_advance_days`
  - `rooms` (`id`, `name`) and `categories` for filter dropdowns
  - `count`, `results`. Each row contains `resource` (complete resource object), `room_name`, `can_request`, `qualification_status`, `resource_status`, `status_reason`, and `slots`
  - `slots` has exactly the same format and rules as `resources/{id}/availability/`: opening hours, booking window, induction, conflicts, and maintenance status.
  - 1.16.0: `too_long` (number of resources omitted because of duration) and `not_bookable` (resources hidden when `bookable_only=true`, counted by reason, for example `{"NOT_SUBMITTED": 18, "MAINTENANCE": 1}`; reasons are `MAINTENANCE`/`CLOSED` or induction status). The frontend uses this to explain why there are no results and provides an Induction & Training link when an induction reason is present. Frontend duration options extend to eight hours.
- When the frontend selects a free cell, it opens BookingForm with `initialDate`, `initialStart`, and `initialMinutes`; SlotPicker automatically selects that interval. Automatic selection occurs only if the entire interval is free.

## Outlook Synchronisation

The website is the sole source of truth for bookings. Changes made in Outlook cannot become website bookings.

- The system performs one-way "website → Outlook" writes only. It never reads Outlook changes at runtime, so changes in Outlook cannot affect a booking.
- The frontend displays sync results only; it does not connect to Outlook or store Microsoft credentials.
- See [outlook-setup.md](outlook-setup.md) for configuration and live-test steps.

Every booking response (list, detail, dashboard, create, cancel, review, reschedule, and results from `admin/process-due/`) includes `outlook_sync`, which is independent of the booking `status`:

```json
{
  "status": "APPROVED",
  "outlook_sync": {
    "status": "SYNCED",
    "action": "CREATE",
    "web_link": "https://outlook.live.com/calendar/item/...",
    "last_error": null
  }
}
```

| outlook_sync.status | Frontend display |
| --- | --- |
| `DISABLED` | Calendar sync is not enabled; the booking status remains valid |
| `NOT_REQUIRED` | The current request does not require a calendar write (pending, waitlisted, rejected, and so on) |
| `PENDING`/`IN_PROGRESS` | Calendar sync is waiting/in progress |
| `SYNCED` + `CREATE`/`UPDATE` | Written to Outlook (rescheduling updates the same event; if the user deleted the event, it is recreated at the new time) |
| `SYNCED` + `DELETE` | Cancellation has been synchronised to Outlook |
| `FAILED` | Booking result is saved but calendar sync failed; prompt the user to contact an administrator |

Use only the booking `status` to determine whether it is approved or cancelled. Do not present calendar-sync failure as "booking failed". Read endpoints do not call Microsoft; poll the booking detail or dashboard when a refresh is needed.

The staff **Calendar Sync** page (`/admin/calendar-sync`, Admin and Manager) is a development-stage visualisation. Its data comes from `GET admin/outlook/` and contains:
- `summary`: `total`, `synced`, `pending`, `failed`.
- `items`: one row per synchronised booking, with failures first. Fields are:
  - `booking_id`, `booking_status`, `start`, `end`, `urgent`
  - `resource`, `booked_for`, `booked_by` (staff member who made the proxy booking), `invited`
  - `sync`: `status`, `action`, `attempts`, `last_error`, `next_attempt_at`, `last_success_at`, `web_link`
- `last_check`: result of the latest `POST admin/outlook/check/`.
- `invite_mode`, `enabled`, `configured`, `mode`, `direction`, `sync_records`.

Other rules:
- When sync is disabled, `outlook-retry` returns 409 `OUTLOOK_DISABLED`.
- Students always receive 403 from these endpoints.
- If this page is removed before final delivery, the backend endpoints may remain.

## 1.16.0: Time-Change Requests, Maintenance Notifications, Contact Details, and Staff Home Page

### Request a Time Change (Booking Holder)

- For an approved booking that has not started, the booking holder may select **Change time** in My Bookings, choose a new time, and call `POST bookings/{id}/change/` with `{"start": "…", "end": "…"}` (optionally with `Idempotency-Key`). The resource stays the same, and the purpose is copied from the original booking. A Manager still uses Reschedule for a direct change.
- The backend creates a new request whose `replaces_id` points to the original booking. If the new time is free, it becomes `PENDING_APPROVAL` and follows normal review. If another booking or hold occupies the new time, it becomes `WAITLISTED`. When the frontend selects an occupied time, it first explains that the request can only join the waitlist; the button and confirmation dialog state this as well.
- **The original booking remains valid until the new request is approved.** At the moment the new request is approved (manually by Admin, automatically at the review deadline, or after promotion from the waitlist), the original booking is automatically cancelled (`reason_code=REPLACED_BY_CHANGE`) and its time is offered to the waitlist. If the new request is rejected, withdrawn, or expires, the original is unchanged. Conversely, if the original booking is cancelled by the holder or staff, its pending time-change request is also cancelled with the same `reason_code` as the original (2026-11-12).
- The same rules as an ordinary request apply: booking window, opening hours, duration, induction, and weekly limit. The original booking itself is not treated as a conflict or duplicate and is not counted twice against the weekly limit. Urgent time changes are not supported.
- A booking may have only one pending time change at a time (409 `CHANGE_ALREADY_REQUESTED`; `details.booking_id` identifies that request). A booking owned by someone else returns 404/403; a booking that is not an approved future booking returns 409 `REQUEST_NOT_CHANGEABLE`; an unchanged time returns 400.
- New booking JSON fields are `replaces_id`, `replaces_booking` (the original booking referenced by a time-change request: `id`, `start`, `end`, `status`), and `open_change` (the pending time-change request on an original booking, with the same four fields). My Bookings uses these to connect the two cards; Booking Review displays "Change from …" below the time.

### Maintenance and Closure Notifications

- When a Manager changes a resource to `MAINTENANCE` or `CLOSED`, everyone with a future booking or request for that resource receives `RESOURCE_OUT_OF_SERVICE` according to their in-app/email preferences. It includes the Manager's reason. Approved bookings **remain in place**; the Manager decides whether to reschedule or cancel them, which generates separate notifications. Returning the resource to `AVAILABLE` sends `RESOURCE_REOPENED`. Changing only the reason without changing status does not send another notification. A room's status does not affect equipment inside it, so equipment booking holders are not notified.
- The Room Management confirmation dialog lists affected bookings and explains that notifications are automatic. The list below marks bookings that can no longer proceed normally.

### Laboratory Contact Details

- `GET site/contact/` returns `{id, email, phone, hours, note, updated_at, updated_by}`; unset values are empty strings. `PATCH site/contact/` (Manager only) changes only submitted fields, an empty string clears a field, `email` must resemble an email address, and the operation writes a `SITE_CONTACT_UPDATED` audit record.
- The details appear on the Help page, approved-booking cards ("Contact the lab"; the email subject and body already contain the resource, time, and booking number), and below each induction description. Only populated fields are displayed.

### Staff Today Home Page

- After sign-in, Admin and Manager go to `/admin/today` (previously Qualification Review and Room Management respectively).
- `GET admin/overview/` returns `pending_inductions`, `pending_bookings` (excluding urgent), `urgent_requests`, `waitlisted`, `changes_waiting`, `due_soon` (pending requests whose review deadline is within six hours, maximum 10), `out_of_service` (`[{resource, affected_bookings}]`), `today` (approved bookings that start today, maximum 10), `today_count`, `missed_today`, and `can_decide_urgent`. Each card links to the page that handles it.

### Other Interface Changes

- Booking Review now has a Purpose column and a Details button; the entire row can also be selected.
- Booking form: Purpose is marked as required; when the button is disabled, it says exactly what is missing. On the earliest bookable date, it explains that an earlier time requires an urgent request and offers a one-click switch. Start time and duration may be selected directly below the time bar. On mobile, the submit button and selected time remain fixed at the bottom of the dialog.
- The resource settings form accepts "maximum booking" and "review period" in hours, while the API still uses minutes.
- Calendar-subscription instructions are provided separately for Outlook, Google, and Apple and explain that updates may be delayed and website status is authoritative.

## 1.17.0: functional controls

### Urgent explanation and evidence

Urgent booking requests still require both `purpose` and `urgent_reason` in `POST bookings/`. The UI collects one **Purpose and urgency** value and sends it in both fields (up to 500 characters). Ordinary booking requests retain their separate Purpose field. Qualification submissions still require a multipart `file`; UI validation does not replace the server's size, MIME and file-content validation.

### Opt-in local test session

- `GET auth/config/` adds `test_console_enabled`. It is true only when `DEBUG=true`, `ENABLE_DEMO_AUTH=true`, `ENABLE_TEST_CONSOLE=true`, `AUTH_PROVIDER=booking.authentication.DemoIdentityProvider` and `REPOSITORY_FACTORY=booking.repository.MemoryRepository` (the in-memory store; with PostgreSQL it stays off). Any disabled condition hides the login endpoint (404) and invalidates existing test tokens (401). Default: disabled.
- `POST auth/test-login/` accepts exactly `{ "login_id": "1" }`; no password. Returns the usual session envelope with a signed token and user (`zid="1"`, initial `role="STUDENT"`, `test_account=true`, `bypass_booking_rules=true`). Database `id` remains a UUID. The stored role stays STUDENT.
- `POST auth/test-session/`, authenticated with that test token only, accepts `{ "role": "STUDENT" | "ADMIN" | "MANAGER", "bypass_booking_rules": true | false }`. It returns a fresh signed session. Replace the token and verify with `auth/me/`. Ordinary accounts receive 403 and cannot obtain overrides by adding fields to booking requests. Switching a session does not mutate another tab's already-issued token.
- Bypass applies to the test account's own bookings, moves and staff weekly series. Free valid future times become APPROVED immediately (`TEST_OVERRIDE` for single bookings); induction, 7–28 day window, opening hours, resource maximum duration, maintenance/closed status and weekly booking limit are bypassed. Archived resources remain unavailable. Single appointments are limited to 24 h; staff series to 52 weeks. Existing bookings and held requests cannot be displaced. Booking for someone else uses that person's normal rules. Turning bypass off restores normal booking windows and approvals; account 1 retains its automatically granted inductions.
- With bypass, availability and day-overview add `test_bypass=true`; `latest_date=null` means no upper calendar-date restriction and date inputs must omit `max`. `min_advance_days` and `max_advance_days` are 0. Single-resource availability adds `max_booking_minutes=1440` and `review_window_minutes=0`; slots cover the local calendar day and preserve past-time/conflict blocks. Normal sessions continue returning their normal window dates. Display a test-override label.
- Self time changes return APPROVED immediately and cancel the replaced original booking. Test attendance is NOT_TRACKED. Website notifications and audit remain; no test booking is sent to Outlook or external notification channels.

All test UI copy is English. This is a local testing facility; keep it disabled on deployed services.

### 1.17.1: account 1 owns every induction

On login and authenticated test requests, account 1 receives every induction as VERIFIED with `valid_until=null`, including requirements added after sign-in. This applies in Student, Admin and Manager views even with booking-rule bypass off. Grants are idempotent, explicitly marked as test access, have no uploaded file and return `file_id=""`, `file_url=""`. The induction UI omits the upload form for this account. Ordinary users still need valid evidence and manual review. No database migration or external notification is involved; the existing local-memory-only gate remains required.

## 1.19.0: Independent Notification Channels and Announcements (Sprint 3)

### Notification Settings

All three roles can access `#/settings/notifications`; the Account page contains only a **Notification settings** link. The five categories are `bookings`, `reminders`, `induction`, `account`, and `resources`.

Responses from `GET notifications/preferences/` and `PUT` have this form:

```json
{"results":[{"category":"bookings","in_app":true,"email":true}],"email_available":false}
```

The example shows one item, but the actual response always contains all five categories. A category with no saved preference has both columns set to true. `email_available` comes from the site's `EMAIL_ENABLED`; it does not mean Gmail/Outlook is connected or that delivery is guaranteed. When false, the frontend disables the email column, displays the entire column as unchecked, and shows **Email is not switched on for this site.** The API still returns and preserves saved selections.

```json
{"preferences":{"bookings":{"in_app":false,"email":true},"resources":{"email":false}}}
```

PUT changes only the submitted columns. Unknown categories, unknown columns, or an empty column object return 400, and nothing in that request is saved. Preferences are stored for the currently signed-in person. The four combinations are in-app and email, in-app only, email only, or neither. Each notification record stores its `in_app`/`email` values at creation time: an email-only record does not appear in `notifications/`, the unread count, or read-all, and enabling in-app notifications later does not add it to the bell. A Manager's `URGENT_REQUEST` does not belong to a user-disableable category.

### Announcement API

| Method | Path | Permission and response |
| --- | --- | --- |
| GET | `announcements/` | Signed-in user; `{count,results}` containing only unarchived, unexpired announcements, newest first |
| GET | `announcements/?include_ended=true` | Admin/Manager; includes ended records; students receive 403 |
| POST | `announcements/` | Admin/Manager; `{title,body,expires_at?}`, 201 |
| PATCH | `announcements/{id}/` | Author of a manual announcement only; partially update `title`, `body`, `expires_at`, 200 |
| POST | `announcements/{id}/remove/` | Author or Manager; empty object, soft archive, 200; repeated removal does not duplicate the audit record |

A student calling any announcement write endpoint receives 403 before request-body validation, even with an invalid body; form errors are not returned first. After trimming whitespace, `title` must contain 1–120 characters and `body` 1–1000 characters. `expires_at` is a timezone-aware ISO datetime or null (never expires). Requests cannot specify fields such as `kind`, `resource_id`, author, or status; doing so returns 400. A Manager may remove another person's manual announcement but may not edit it. An Admin may not edit or remove another person's announcement. Status announcements return 403 through these write endpoints.

Each announcement contains `id,title,body,kind,resource_id,created_by,created_at,expires_at,removed_at,removed_by,updated_at,author_role,expected_back`, plus `author:{id,display_name,role}` and `active`. `author_role` is the role at publication time, and attribution displays the person's name and role. A missing announcement returns 404; an archived manual announcement cannot be edited (409). Creation, editing, and removal are audited but do not generate notifications.

### Resource-Status Announcements

`PATCH admin/resources/{id}/status/` remains Manager-only; Admin receives 403. In addition to the existing `status,reason`, the request accepts optional `expected_back` (timezone-aware ISO datetime or null). Omitting it means there is no estimate. The response remains `{resource,affected_bookings}`, and the corresponding announcement is read through the announcement list.

Within the original transaction, `set_resource_status` creates or updates a `RESOURCE_STATUS` announcement for a room or equipment item, using the reason as the body and the Manager who changed the status as the attribution. Each resource has at most one unarchived status announcement at a time. Changing the reason does not create another record; `AVAILABLE` archives it automatically. `expected_back` is stored separately and is for display only. It does not automatically expire the announcement or reopen the resource; an announcement remains visible after the estimated time until a Manager returns the resource to available. Existing `RESOURCE_OUT_OF_SERVICE`/`RESOURCE_REOPENED` notification logic remains.

The Dashboard/Today home pages load only active announcements and do not render an announcement section for an empty list. The staff management page labels these announcements **From room status** and does not offer edit or remove controls. Page date input is converted to ISO using Australia/Sydney; a nonexistent daylight-saving time displays an error and preserves the input. Dialog errors appear inside the dialog.

## 1.20.0: Personal History Removal (Sprint 3)

- `POST bookings/{id}/remove-from-history/`: empty request or `{}`; success is `204` with no response body. Repeating the call still returns `204`.
- Only the booking beneficiary (`student_id`) or creator (`created_by`) may remove their own entry. Staff also cannot remove an unrelated booking from their personal history; the endpoint returns `404`. Identity comes from the server, and additional fields such as user_id are rejected (`400`).
- A booking may be removed when it is `CANCELLED`, `REJECTED`, or `EXPIRED`, or when `end <= now`. A future or in-progress active booking returns `409 BOOKING_NOT_HISTORY`; cancel or withdraw it first. Each date in a recurring series is handled independently.
- `GET bookings/` and `GET dashboard/` (including counts) exclude entries removed by the current user. The two sides of a proxy booking do not affect one another. Detail endpoints, staff records/CSV/usage, source bookings and no-shows, notifications, and calendars are unchanged. No cancellation or removal email is sent.
- The frontend button is `Remove from my history`; its confirmation explains that staff records are retained. A failed action leaves the item visible, and it is removed only after success. My Bookings intersects the Resource and status categories, and URL `view`/`resource` values remember the conditions. No backend filter parameter is added.
