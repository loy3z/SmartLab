# Local PostgreSQL Database and Full-Stack Startup

Each team member uses a separate local database. The commands below are for Windows PowerShell and run from the project's `backend` directory. Start the frontend in another terminal.

## Included files and data

- `database/schema.sql`: 18 tables, including `resource_internal_info`, `site_contact`, `notification_preference`, `announcement`, `booking_history_removal` and durable email queue `email_delivery`, plus constraints, indexes, sequences and the audit-protection trigger.
- `database/seed_resources.sql`: two training requirements, with Advanced requiring General first; two rooms; and 20 equipment resources with containing rooms.
- `database/seed_users.sql`: six fictional demo accounts matching the in-memory identities and one verified induction for z1000001. Never commit real student zIDs.
- `database/migrations/`: repeatable upgrade scripts 001–017 for existing databases, applied in order; see Section 2.
- `booking/tests/test_postgres.py`: adapter integration tests against real PostgreSQL; see Section 6.
- `booking/postgres.py`: database and uploaded-file storage adapters.
- `requirements-postgres.txt`: backend dependencies and PostgreSQL driver.
- `config/settings.py`: reads the database connection from environment variables.

Initialisation files contain no bookings, Outlook sync records or audits. Room hours, booking lengths, review deadlines (`pending_hold_minutes`, default 1440 minutes or 24 hours), training validity and similar values are demonstration configuration that the team must confirm later.

## 1. Prepare software

Install and start PostgreSQL, preferably 18; versions 16 and later are verified. Import with the matching `psql`. Prepare Python 3.13, for example in an activated Conda environment, and a Node.js version that runs Vite 8.

Open the cloned project in VS Code and enter `backend` in the terminal. Adjust the PostgreSQL installation path for your machine:

```powershell
$pgBin = 'C:\Program Files\PostgreSQL\18\bin'
$dbName = 'SmartLab_9900_F15E_BREAD'
```

For a D-drive installation, use a path such as `$pgBin = 'D:\PostgreSQL\bin'`. Enter the password chosen during PostgreSQL installation when connecting. Never write it into a Git file.

## 2. Create and import the database for the first time

Use this only to create a new, empty database. If it already exists, creation fails and stops. Do not delete an existing database merely to continue.

```powershell
& "$pgBin\createdb.exe" --host=localhost --port=5432 --username=postgres --password --encoding=UTF8 --template=template0 $dbName
if ($LASTEXITCODE -ne 0) { throw 'Creation failed. Inspect the error; if the database exists, confirm its purpose first.' }

& "$pgBin\psql.exe" --host=localhost --port=5432 --username=postgres --password --dbname=$dbName --no-psqlrc --set=ON_ERROR_STOP=1 --single-transaction --file='.\database\schema.sql' --file='.\database\seed_resources.sql' --file='.\database\seed_users.sql'
if ($LASTEXITCODE -ne 0) { throw 'Import failed and the transaction was rolled back. Investigate the error first.' }
```

The schema creation statement in `schema.sql` should be `CREATE SCHEMA IF NOT EXISTS public;` for compatibility with a new database's existing public schema. This does not make the whole import repeatable: create the tables and seeds only once. Keep `\restrict` / `\unrestrict` from exported files and execute the complete file with `psql`.

If creation succeeds but import fails, fix the cause and rerun only the import command. Never experiment with these import commands on a database containing business data.

### Upgrade an existing database to the latest structure

To avoid rebuilding, apply every script in `database/migrations/` in numerical order. Each script is repeatable, skips work already complete and, except where explicitly noted below, does not delete data. It is safe to run the complete set without first finding the current version. Running them against an up-to-date database changes one thing only: 001 sets the review deadline of any resource that is exactly 30 minutes (the original default) to 1440 minutes. Staff passwords are never reset: 005 replaces only the earlier demo password from 003.

```powershell
Get-ChildItem .\database\migrations\*.sql | Sort-Object Name | ForEach-Object {
    & "$pgBin\psql.exe" --host=localhost --port=5432 --username=postgres --password --dbname=$dbName --no-psqlrc --set=ON_ERROR_STOP=1 --single-transaction --file=$_.FullName
    if ($LASTEXITCODE -ne 0) { throw "Upgrade failed: $($_.Name)" }
}
```

Each file prompts once for the PostgreSQL password. Set `$pgBin` and `$dbName` as in Section 1 in every new terminal.

| Script | Contents |
| --- | --- |
| `001_client_approval_flow.sql` | Resource `status`, `status_reason`; review deadline default 1440 minutes |
| `002_week5_rules.sql` | Induction prerequisites `prerequisite_ids`, containing room `room_id`; demo Advanced → General and equipment rooms |
| `003_staff_sign_in.sql` | New `staff_credential` table for password hashes and invites; demo passwords set, other existing staff receive activation invites |
| `004_staff_booking_urgent.sql` | Add `created_by`, `urgent`, `urgent_reason` to `booking`; existing `created_by` becomes `student_id` |
| `005_resource_category_demo_password.sql` | Add `bookable_resource.category`, populate fictional categories only when empty; change demo z9000001/z9000002 from the earlier demo password to `123` (a password changed since then is kept) |
| `006_calendar_notifications_attendance_series.sql` | Add `notification`, `calendar_feed`, `unfreeze_request`, `booking_series`; add `no_show_count`, `frozen_until` to `app_users`; add `series_id`, `attendance`, `checked_in_at` to `booking`. On first run, approved bookings already started become `NOT_TRACKED`, not absent |
| `007_change_requests_guidance_details_contact.sql` | 1.16.0: add `booking.replaces_id` for change requests and a partial unique index for one unresolved change per booking; add four guidance fields to `qualification_requirement`; add room-only `capacity` 1–1000 and `details` JSON array to resources; add one-row `site_contact`. Existing data unchanged |
| `008_notification_preferences.sql` | Per-person/category in-app switch `notification_preference.enabled` |
| `009_announcements_notification_channels.sql` | Sprint 3 1.19.0: add `email_enabled DEFAULT true NOT NULL` while retaining `enabled`; add channel snapshots `in_app`, `email` to notifications; add `announcement`, one-active-status-announcement-per-resource partial unique index and time indexes |
| `010_booking_history_removal.sql` | 1.20.0: one personal history-removal row per user/booking; composite key provides idempotency and foreign keys preserve original entities; no booking is deleted or changed |
| `011_durable_email_delivery.sql` | Final recipient/content, send state, attempts, retry time and worker lease for email; cascade when its notification is deleted |
| `012_additional_hours_requests.sql` | Add additional-hours flag/reason and active-data-collection declaration/explanation to `booking`; old records default false/null and retain state/time. Constraints prohibit review holds and ordinary automatic deadlines and prohibit urgent combination |
| `013_long_booking_requests.sql` | Add long-booking flag/reason; old normal and additional-hours records remain. A long booking requires a reason, cannot be urgent, additional hours or recurring, and retains ordinary hold/waitlist behaviour |
| `014_remove_booking_freeze.sql` | 1.25.0: remove freeze table `unfreeze_request`, `app_users.no_show_count`, `frozen_until` and constraints. **Deletes freeze data**, while `booking.attendance` remains. Before rolling back to pre-1.25 code, rerun 006 to restore empty columns/tables |
| `015_resource_internal_info.sql` | 1.26.0: new one-row-per-resource `resource_internal_info` for owner, UNSW asset number, source and specifications, Manager-only; cascades on resource deletion. Adds only a table |
| `016_extension_requests.sql` | 1.27.0: add `booking.extension_end`, a requested later end awaiting Manager approval, with a later-than-`end` constraint; existing rows are NULL |
| `017_end_before_extension.sql` | After 1.29.0 (API unchanged): add `booking.end_before_extension`, the end before the first approved extension, so extensions stay out of the weekly allowance; fills it for already-extended bookings from the earliest `old_end` in their `BOOKING_EXTENDED` audit records; existing other rows are NULL |

The schema-only dump of an upgraded database must exactly match one created from `schema.sql` and seeds. For every schema change, create one new database and one from old scripts, run every migration twice on the latter, and compare `pg_dump --schema-only`.

If a local database contains only disposable test data, it may instead be deleted and recreated with pgAdmin or `dropdb`. Confirm nothing must be retained first.

## 3. Install backend dependencies and configure the connection

From `backend`, activate your Python environment and run:

```powershell
python -m pip install -r requirements-postgres.txt
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed' }

$env:DB_NAME = 'SmartLab_9900_F15E_BREAD'
$env:DB_USER = 'postgres'
$env:DB_HOST = 'localhost'
$env:DB_PORT = '5432'
$env:DB_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host 'PostgreSQL password' -AsSecureString)).Password
$env:DEBUG = 'true'
$env:ENABLE_DEMO_AUTH = 'true'
$env:AUTH_PROVIDER = 'booking.authentication.DemoIdentityProvider'
$env:SEED_DEMO_DATA = 'false'
$env:REPOSITORY_FACTORY = 'booking.postgres.PostgresRepository'
$env:FILE_STORAGE_FACTORY = 'booking.postgres.PostgresFileStorage'
$env:OUTLOOK_ENABLED = 'false'
```

These variables apply only to this terminal and its child processes. Set them again in every new backend terminal; `.env` is not loaded automatically. Both factory variables are required, otherwise memory storage remains the default. The backend connects to PostgreSQL only when `REPOSITORY_FACTORY` points to the adapter; without it, PostgreSQL need not be installed. Keep `SEED_DEMO_DATA=false` to prevent runtime demo reinsertion. For login sessions to survive a backend restart, also use a stable local `$env:DJANGO_SECRET_KEY`, never committed.

Optional: `DB_CONN_MAX_AGE` in seconds, default 60. A process reuses the connection for this period instead of opening one for every request, which costs about 12 ms. Set 0 to restore per-request connections. Docker uses the default; no setting is needed, based on the 29 October 2026 S3 load-test task.

Confirm that the adapter reads data:

```powershell
python manage.py shell -c "from booking.postgres import PostgresRepository; r = PostgresRepository(); print('Users:', len(r.list_principals())); print('Resources:', len(r.list_resources())); print('Requirements:', len(r.list_requirements())); print('Submissions:', len(r.list_submissions()))"
```

After first import, expect Users 6, Resources 22, Requirements 2 and Submissions 1.

## 4. Start backend and frontend

In the configured backend terminal, keep this running:

```powershell
python manage.py runserver 127.0.0.1:8000 --noreload
```

In another terminal, enter `frontend`:

```powershell
npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
npm.cmd run dev
```

Open the displayed URL, normally `http://localhost:5173`. Vite proxies `/api` to `http://127.0.0.1:8000`. If a port is occupied, identify the existing service first.

## 5. Demo sign-in and verification

Students use simulated university sign-in with zID only. Admins and Managers select **Staff sign-in** and use zID and password.

| zID | Role | Description |
| --- | --- | --- |
| z1000001 | STUDENT | General induction verified; can book Lab Room 1 and its equipment |
| z1000002 | STUDENT | No induction |
| z1000003 | STUDENT | No induction |
| z1000004 | STUDENT | No induction |
| z9000001 | ADMIN | Reviews evidence and bookings; demo password `123` |
| z9000002 | MANAGER | Room status, exports and user management; demo password `123` |

Suggested walkthrough: z1000002 uploads safe test evidence → z9000001 verifies it → z1000002 requests a booking → z9000001 approves. Stop and restart the backend and confirm the data remains. New operations write only to each member's local database and never enter Git automatically. If login expires after restart because development uses a temporary key, sign in again.

Do not re-import SQL for everyday startup. Start PostgreSQL, set the backend variables again, run the backend and then the frontend.

### Create a new Manager without SQL

From the configured backend terminal:

```powershell
python manage.py create_manager --zid z9000003 --name "Lab Manager" --email z9000003@ad.unsw.edu.au
```

The command prints a one-time invite. The user selects First activation on Staff sign-in and enters the zID, invite and a new password. Later staff are added through Add staff in User Management; rooms and equipment are added through Resources.

### Scheduled due processing

Visits incidentally process requests whose review deadline passed. Docker Compose uses a separate `scheduler`; local database development can run this persistently with the same variables:

```powershell
python manage.py run_scheduler
```

Alternatively use Windows Task Scheduler or server cron every minute:

```powershell
python manage.py process_due
```

It prints `Decided or expired N request(s).` and also records absence after an unconfirmed attendance window. It can be run once for a demonstration. Database mode is required; memory mode exits with an error.

## 6. Test the adapter against a real database

Run from the configured backend terminal. Django creates and removes a temporary `test_<database-name>` without changing your data:

```powershell
python manage.py test booking.tests.test_postgres -v 2
```

The suite covers record types and persistence, room status, induction prerequisites and containing rooms, staff activation and password sign-in, file upload, the full workflow from pending through approval, cancellation, waitlist promotion and automatic approval after 24 hours, rollback, immutable audits, simultaneous requests producing only one pending hold, plus notification, calendar feed, recurring booking, check-in and absence persistence.

Sprint 3 1.19.0 `Postgres119Tests` and `Memory119Tests` reuse one acceptance suite for four notification-channel combinations, partial saves and personal isolation, announcement permission matrix, expiry/removal, room/equipment status announcement update/reopen and transactional rollback. Separate tests cover old preference upgrade and running 009 twice.

Other tests, `python manage.py test booking`, use memory storage. Clear `REPOSITORY_FACTORY` and `FILE_STORAGE_FACTORY` first or use a new terminal.

## Verified scope and limitations

Section 6 integration tests and Section 2 upgrade verification pass on PostgreSQL 16. `process_due` runs in database mode. Full-stack upload, review, request, approval and room-status changes persist after backend restart.

Database advisory locks serialise writes. Tests cover correctness for concurrent requests to the same time, but this alone does not constitute production performance acceptance.

When committing, select only the documentation, initial SQL, adapter and configuration changes. Never commit `.env`, database passwords, complete data backups or personal test attachments.
