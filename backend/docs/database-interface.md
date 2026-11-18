# Database Interface

The business layer uses the `Repository` protocol in `booking/repository.py` and the entities in `booking/domain.py`. A database adapter is selected through `REPOSITORY_FACTORY`; attachments use private storage selected through `FILE_STORAGE_FACTORY`. Two adapters exist: the default in-memory adapter for demonstrations and unit tests, and the PostgreSQL adapter in `booking/postgres.py`. See `database/README.md` for the schema and local setup, and `booking/tests/test_postgres.py` for integration tests. The project does not use Django ORM models or Django migrations. Every schema change must update `database/schema.sql` and add a repeatable upgrade script under `database/migrations/`.

## Entity field conventions

The table lists fields that need particular attention. `booking/domain.py` is authoritative for the complete field definitions.

| Entity | Field | Persistence contract |
| --- | --- | --- |
| Principal | `university_email: str` | Required; in production it comes from a trusted SSO or identity record. Returned by the user API with the zID and name. Never infer a role or qualification from it |
| Resource | `pending_hold_minutes: int` | Required integer from 1 to 20160; default 1440 (24 hours). This is the Admin review deadline; the existing column name is retained. Persist changes made by a Manager and write an audit record |
| Resource | `status: str`, `status_reason: str \| None` | `status` is `AVAILABLE`, `MAINTENANCE` or `CLOSED`, defaulting to `AVAILABLE`; `status_reason` is optional and at most 500 characters. This differs from `active`: `active=false` archives and hides a resource, while `status` is an operational state a Manager can change at any time |
| Resource | `room_id: str \| None` | Room that contains a piece of equipment, as a foreign key to a room resource. It is empty for rooms themselves, enforced by `room_id IS NULL OR kind='EQUIPMENT'`. Used only for display and grouping; room status does not affect its equipment |
| Resource | `category: str \| None` | Equipment category used by booking-page filters; empty for rooms; 1–60 characters |
| QualificationRequirement | `prerequisite_ids: tuple[str, ...]` | Column `prerequisite_ids uuid[] NOT NULL DEFAULT '{}'`; cannot contain its own ID. The business layer checks cycles. In demo data, Advanced requires General |
| Booking | `student_id`, `created_by: str \| None` | `student_id` identifies the beneficiary: their induction is checked, and locks and duplicate checks use this ID. `created_by` identifies the creator and differs from `student_id` when staff book for somebody else |
| Booking | `urgent: bool`, `urgent_reason: str \| None` | Urgent-request flag and reason, at most 500 characters |
| Booking | `hold_until`, `review_due_at: datetime \| None` | Optional, timezone-aware. When a normal request enters `PENDING_APPROVAL`, both receive `min(start, submission time + pending_hold_minutes)` and are not recalculated when resource rules change. An urgent request has no `review_due_at` and uses `hold_until=start` |
| ResourceInternalInfo | `resource_id`, `owner`, `asset_number`, `provided_by`, `specifications`, `updated_at`, `updated_by` | 1.26.0: table `resource_internal_info`, with `resource_id` as its primary key and a cascading foreign key to the resource. Intentionally separate from `Resource` because only Managers may read and write it |
| Booking | `revision: int` | Defaults to 1 and increments on every reschedule |
| Booking | `extension_end: datetime \| None` | 1.27.0: requested later end time for a booking in progress, awaiting Manager approval. Approval moves it to `end` and clears the field; rejection clears it. Constraint `booking_extension_end_check` requires a time later than `end` |
| Booking | `series_id: str \| None` | Staff recurring booking, as a foreign key to `booking_series`; empty for a single booking |
| Booking | `attendance: str \| None`, `checked_in_at` | Attendance marker meaningful only for approved bookings: `CHECKED_IN`, `NO_SHOW`, `EXCUSED` or `NOT_TRACKED`; empty until decided. Migration 006 marked approved bookings that had already started before the column was added as `NOT_TRACKED`, preventing them from being counted as absences |
| Booking | `replaces_id: str \| None` | 1.16.0 change request: points to the approved booking it will replace. Partial unique index `booking_one_open_change_idx` permits only one unresolved change request for a booking. When the request is approved, the business layer cancels the original booking in the same transaction |
| Resource | `capacity: int \| None`, `details: tuple[ResourceDetail, ...]` | 1.16.0: room capacity, available only for rooms, from 1 to 1000 and enforced by `bookable_resource_capacity_check`; `details` is a `jsonb` array `[{'label': …, 'value': …}]`, constrained to be an array and defaulting to `[]`. The adapter converts it back to `ResourceDetail` |
| QualificationRequirement | `how_to_complete`, `accepted_evidence`, `reviewer`, `contact: str` | 1.16.0 Manager-authored guidance, stored as `text NOT NULL DEFAULT ''` |
| SiteContact | `id`, `email`, `phone`, `hours`, `note`, `updated_at`, `updated_by` | 1.16.0: `site_contact` contains one row. Its `id` is fixed to `SITE_CONTACT_ID` by a constraint. If the row is absent, the business layer returns an empty record |
| Notification | `recipient_id`, `kind`, `title`, `body`, `created_at`, `link`, `booking_id`, `read_at` | Stored in `notification` in the same transaction as the change that caused it; read newest first for each recipient |
| CalendarFeed | `principal_id`, `token`, `created_at` | One `calendar_feed` row per person with a unique `token`; regenerating the link replaces the token |
| BookingSeries | `student_id`, `created_by`, `resource_id`, `weekdays`, `start_time`, `duration_minutes`, `first_date`, `last_date`, `purpose` | Table `booking_series`; `weekdays` is a comma-separated list of ISO weekdays (`"1,3"` means Monday and Wednesday), and `start_time` is in the resource's local time |
| Booking | `status` | Seven values: `WAITING_QUALIFICATION`, `PENDING_APPROVAL`, `WAITLISTED`, `APPROVED`, `REJECTED`, `CANCELLED`, `EXPIRED`. `WAITING_QUALIFICATION` occurs only in legacy data and is no longer created |
| OutlookSyncRecord | `booking_revision`, `ical_uid`, `last_success_at`, etc. | Event mapping, version, retry and lease information must all be persisted |
| StaffCredential | `principal_id`, `password_hash`, `invite_code`, `updated_at` | Table `staff_credential`, keyed by `principal_id` with a foreign key to `app_users`. Only Admins and Managers have one. `password_hash` is a Django password hash and is empty before activation; `invite_code` is empty afterward. Repository methods are `get_credential(principal_id)` and `save_credential(credential)`. A separate table prevents password hashes from being returned with user objects |

`hold_active`, `blocks_slot` and `waitlist_position` are API response fields calculated from status, submission order and server time. They are not persisted.

Student, Admin and Manager are separate account types. A role is fixed at creation and cannot be converted later. All three roles can make bookings under the same rules. A Manager creates an Admin or Manager through `POST admin/users/staff/`: `save_principal` stores the unique, lower-case zID and writes an `ADMIN_CREATED` or `MANAGER_CREATED` audit. `PATCH admin/users/{id}/` changes `active`, while the business layer writes `USER_UPDATED` in the same transaction. Deactivating a student also rejects that student's unresolved requests with `ACCOUNT_DEACTIVATED` and promotes the waitlist. `atomic` locks every Manager and the modified user together, preventing concurrent actions from leaving the system without an active Manager. Demo users may be inserted directly into the database. `role` must be `STUDENT`, `ADMIN` or `MANAGER`, and at least one Manager must remain active.

Every `Principal` requires an email address, which authentication adapters and database mappings must supply. Demo registration uses EmailField to validate format but does not prove ownership or a university domain and is not production authentication. Admin and Manager roles can be assigned only by a trusted source or system owner, never accepted from a student registration request.

## Blocking query

```python
def list_blocking_bookings(
    self,
    resource_id: str,
    start: datetime,
    end: datetime,
    at: datetime,
    exclude_id: str | None = None,
) -> list[Booking]: ...
```

Return bookings that overlap `[start,end)` and currently block the time. `at` comes from the backend clock and cannot be supplied by a browser. The query is conceptually as follows; map the field names to the actual schema as required:

```sql
WHERE resource_id = :resource_id
  AND start < :end AND "end" > :start
  AND (:exclude_id IS NULL OR id <> :exclude_id)
  AND (
    status = 'APPROVED'
    OR (
      status IN ('WAITING_QUALIFICATION', 'PENDING_APPROVAL')
      AND hold_until > :server_now
    )
  )
```

When reviewing a request, exclude only that booking ID, not the student's other bookings. Adjacent intervals do not conflict. Rooms and individual pieces of equipment are queried independently.

## Approval workflow

- Only a person whose required induction and prerequisites are verified and remain valid may submit. Otherwise the business layer returns 403 `QUALIFICATION_REQUIRED` and writes no booking record.
- Creation, manual approval, automatic processing, promotion and rescheduling all call `BookingService.rule_violation` in `booking/services/checks.py`. Checks run in this order: active account → available resource → valid time → booking window (creation and rescheduling only) → qualification and prerequisites. The adapter must make the latest user, resource and qualification records available while locked.
- Every request for a free time enters `PENDING_APPROVAL` with `reason_code=AWAITING_REVIEW`. It stores `hold_until = review_due_at = min(start, submission time + pending_hold_minutes)` and blocks overlapping times until that deadline. A request with an existing blocker is `WAITLISTED`, has `hold_until=None`, and **does not block any time**.
- An urgent request (`urgent=true`) requires a free time and does not join the waitlist. It uses `reason_code=URGENT_AWAITING_MANAGER`, can be decided only by a Manager, is never processed automatically, and expires if unresolved before it starts.
- An Admin or Manager approves (`APPROVED`) or rejects (`REJECTED`) within the deadline. Staff cannot review a request for themselves or one they created.
- At the deadline, `process_due_requests` rechecks the rules under the resource lock. A request that still has an active account, valid qualification, available resource and no conflict becomes `APPROVED` with `reason_code=AUTO_APPROVED_AFTER_REVIEW_WINDOW`. Otherwise it becomes `REJECTED` with `AUTO_REJECTED_ACCOUNT_INACTIVE`, `AUTO_REJECTED_QUALIFICATION`, `AUTO_REJECTED_RESOURCE_UNAVAILABLE`, `AUTO_REJECTED_BOOKING_RULES` or `AUTO_REJECTED_CONFLICT`. It sets `reviewed_by='SYSTEM'` and writes an audit. Automatic approval also creates an Outlook sync task. In database mode, the scheduled command `python manage.py process_due` triggers this processing; see `database/README.md`.
- Unresolved requests, including waitlisted requests, become `EXPIRED` when their start time arrives. Cancellation, rejection and expiry immediately stop blocking; `hold_until` is retained for traceability.
- When a student's induction is rejected, unresolved requests that depend on it (`PENDING_APPROVAL` or `WAITLISTED`) are also `REJECTED` with `QUALIFICATION_REJECTED`. Verifying an induction never approves a booking automatically.

## Waitlist and automatic promotion

The business-layer `_promote_waitlist(resource_id)` in `booking/services/waitlist.py` processes every `WAITLISTED` booking for the resource **inside the same transaction while holding the resource lock**:

1. Iterate in ascending `(created_at, id)` order. **This order defines first-come, first-served.** Persist `created_at` to microseconds. Where possible, add a monotonically increasing sequence column as the final ordering key to avoid ambiguity between simultaneous submissions.
2. Change requests whose start has passed to `EXPIRED`. Skip them when a blocker still exists or the resource is unavailable. Otherwise, change requests that still satisfy the rules to `PENDING_APPROVAL` with `reason_code=PROMOTED_FROM_WAITLIST` and recalculate `hold_until` and `review_due_at`. Change ineligible requests to `REJECTED`, using the rule error such as `QUALIFICATION_REQUIRED` or `ACCOUNT_INACTIVE` as `reason_code`. Write `BOOKING_PROMOTED` or `BOOKING_REJECTED` audits with actor `SYSTEM`. Promotion does not approve the request; it still has a review deadline.
3. Trigger promotion on cancellation, rejection, expiry, rescheduling, automatic rejection and restoration of a resource to `AVAILABLE`.

Promotion modifies bookings belonging to **other students** while holding only the resource lock. This is safe because every write that changes occupancy of the resource—creation, review, cancellation, rescheduling, evidence review and time advancement—locks that resource first. The adapter must reuse the outer transaction, or a savepoint, for nested calls to `atomic`, and must not lock another resource in a different order while already holding a resource lock.

Recommended indexes: `(resource_id, status, created_at)` for reading the waitlist, `(status, review_due_at)` for finding requests whose review deadline has arrived, and `(student_id, status)` for duplicate checks and cascading rejection after evidence is rejected.

## Transaction and concurrency requirements

`atomic(resource_ids, student_ids)` must implement a real database transaction with consistently ordered resource and student locks. Request creation, manual approval, automatic decisions at the deadline, cascading rejection after evidence rejection, and rule changes must follow the lock set supplied by the business service. Within one transaction, reread resource rules, qualifications and blocking bookings, then save the booking and audit; any failure rolls everything back.

Database indexes may cover resource, time interval, status and hold deadline. An interval exclusion constraint on `APPROVED` rows alone cannot prevent holds that conflict across statuses, so a resource lock and transactional recheck remain necessary. The availability API is only a snapshot and cannot replace validation in the write transaction. The adapter must verify that two concurrent requests create only one hold or approved booking and that an error rolls back every related write.

Under the same resource and student locks, check whether that student already has an active request overlapping the new time. Active statuses are `PENDING_APPROVAL`, `WAITLISTED` and `APPROVED`; legacy `WAITING_QUALIFICATION` also counts. If one exists, the business layer returns `DUPLICATE_BOOKING` and must not create another waitlisted record. Final records do not prevent another request. Requests for different resources at the same time are not duplicates.

A rule update writes a `RESOURCE_BOOKING_POLICY_UPDATED` audit with the before and after minute values. The business service sets `QualificationSubmission.valid_until` when status is VERIFIED, using the review time plus configurable `qualification_validity_days`, default 120. It is empty for PENDING or REJECTED. Details for the `QUALIFICATION_VERIFIED` audit include `valid_until`. `GET admin/audit/` filters and paginates the result of `list_audit()` in the business layer. As data grows, add indexes for audit `at`, `entity_type` + `entity_id`, `actor_id` and `action`, and push filtering into the query if necessary while preserving existing test results. Audit records are append-only and are never edited or deleted. Every resource has one `required_qualification_id`, which may differ between resources. Prerequisites are in `qualification_requirement.prerequisite_ids`. Do not replace this with a global inducted boolean on the user.

## Notifications, subscriptions, attendance and recurring bookings

Repository methods include `save_notification`, `get_notification`, `list_notifications(recipient_id)` in newest-first order; email queue methods `save_email_delivery`, `get_email_delivery`, `list_email_deliveries`, `claim_email_deliveries`; `get_calendar_feed(principal_id)`, `get_calendar_feed_by_token(token)`, `save_calendar_feed`; and `save_series`, `get_series`. Version 1.16.0 adds `get_site_contact()` (returns `None` when absent) and `save_site_contact(contact)`. Version 1.26.0 adds `get_resource_internal_info(resource_id)` (returns `None` when absent) and `save_resource_internal_info(info)`.

- The **notification and email outbox** is written in the same transaction as the booking and rolls back with it on failure. SMTP network calls run after commit. `claim_email_deliveries` must atomically set leases using row locks, `SKIP LOCKED` or equivalent, preventing multiple workers from claiming one task.
- **Absence processing** is the final step of `process_due_requests`, in `_process_attendance` in `attendance.py`. An approved booking with empty `attendance` whose check-in window has ended is reread under resource and beneficiary locks, then marked `NO_SHOW` or `EXCUSED` without changing other bookings. Version 1.25.0 removed freezes: `Principal` no longer has `no_show_count` or `frozen_until`, and `UnfreezeRequest` no longer exists.
- A **recurring booking** rechecks every date under resource and beneficiary locks, then writes the series and every booking together. Any failure rolls back the whole operation.
- The **weekly limit** counts the beneficiary's active non-series bookings in the same week under the resource and beneficiary locks during request creation.

## Integration and upgrades

- For an existing database, run every script under `database/migrations/` in order. Every script is repeatable. See Section 2 of `database/README.md`.
- Populate user email addresses from trusted identity data; never invent production user addresses.
- `DEFAULT_PENDING_HOLD_MINUTES` is only for creating demo seed data and cannot override Manager configuration stored in the database.
- Store time fields with time zones. The API emits UTC; opening-hour rules use the resource time zone.
- `save_booking`, `save_resource` and `save_principal` must read and write every field above. Replacing the adapter must not change the API structure.
- When a Manager creates a resource through the website, `save_resource` inserts a row whose UUID is generated by the business layer. Archiving sets `active=false` and does not delete the row, so foreign keys from bookings and audits remain valid. The business layer checks resource rules such as unique names, the containing room for equipment and time increments; no new database constraint is required.
- Create the first Manager with `python manage.py create_manager --zid … --name … --email …`, which outputs a one-time invite code. Hand-written SQL is unnecessary.
- Reminders for an upcoming booking or expiring induction are sent once. Before sending, the business layer searches that person's `notification` records for the same reminder kind, so no additional table or field is required.

## Outlook synchronisation records

Outlook uses `OutlookSyncRecord` and repository methods `get_outlook_sync`, `list_outlook_sync` and `save_outlook_sync`. The booking, audit and sync task commit in one transaction; the network call runs outside it. A pending request has no Outlook event; synchronisation starts only after manual or automatic approval. Synchronisation is one way and the system never reads changes made in Outlook. If a reschedule finds that the user deleted the event, change the task to CREATE and write it again, retaining the old iCal UID as a marker but using a new transactionId, then write an `OUTLOOK_EVENT_RECREATED` audit. Multiple backend processes and independent background commands require a shared database such as PostgreSQL. The in-memory demo neither shares nor persists data.
