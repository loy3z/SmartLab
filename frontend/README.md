# SmartLab frontend

React + TypeScript + Vite + React Router. Frontend A provides the application shell, authentication, role routes, shared API client and student dashboard. Booking and administration features are mounted inside that shell.

## Run locally

Use Node.js 24 (the dependency-free test runner imports TypeScript directly).

Start the backend in a separate PowerShell terminal, following `../backend/README.md`. For an existing virtual environment, from the project root:

```powershell
cd backend
$env:DEBUG="true"
$env:ENABLE_DEMO_AUTH="true"
$env:DJANGO_SECRET_KEY="local-demo-only-change-this-key"
$env:OUTLOOK_ENABLED="false"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

Then, from this frontend directory:

```powershell
npm ci
npm run dev
```

Open the Local URL printed by Vite (normally `http://localhost:5173`). `/api` is proxied to `127.0.0.1:8000`; no credentials are stored in frontend configuration. The backend must be running for login and dashboard data.

## Authentication

The sign-in page reads `GET /api/v1/auth/config/`. Demo login and student registration appear only when the backend enables them. No password is requested in demo mode; it is not university SSO. If demo authentication is disabled, the page explains that university sign-in is not connected. The current API does not provide an SSO redirect flow.

The primary **University sign-in (Demo)** link opens `#/login/mock-sso`, a separate simulated university sign-in page with a campus background and centred white card. Enter an existing demo zID (for example `z1000001`) or its `@ad.unsw.edu.au` email form, then select **Next** or press Enter. Input is trimmed and matched case-insensitively; other email domains are rejected. The email form is only an alias for a demo zID, not verification of university identity or mailbox ownership. **Sign-in options** lists the seeded student accounts.

University sign-in is for students only: the backend refuses staff zIDs there (`USE_STAFF_SIGN_IN`).

**Staff sign-in** (`#/staff/login`, linked from the sign-in page) is for Admins and Managers: zID + password (`auth/staff-sign-in/`). A Manager adds staff in User Management, which shows an invite code until the person activates; **First time? Activate your account** takes the zID, invite code and a new password (`auth/staff-activate/`). A forgotten password is handled by the Manager's **Reset access**, which issues a new code. Students are refused on the staff page (`STUDENT_USES_SSO`). The demo staff password is `123`.

The form calls the existing `auth/demo-login/` API; the backend issues the session token and `auth/me/` determines the user's role. The plain zID form and student registration are under **Other demo sign-in options** on the SmartLab sign-in page. **Back to SmartLab** cancels the mock sign-in, ignores any pending login response, and preserves an allowed return destination for the next attempt.

This demonstrates the sign-in journey, session restoration, role-specific navigation and returning to an allowed page after login. It does not implement an external identity provider, an OAuth/OIDC callback or shared sign-on across applications; `sso_connected` remains false. No university password is collected.

| Demo zID | Role | Starting page |
| --- | --- | --- |
| `z1000001` | Student with general induction | Dashboard |
| `z1000002` | Student without induction | Dashboard |
| `z9000001` | Administrator (Staff sign-in, password `123`) | Qualification review |
| `z9000002` | Manager (Staff sign-in, password `123`) | Room management |

### Tutor demonstration

1. Start both servers with demo authentication enabled, then open `http://localhost:5173/#/login` (sign out first if already logged in).
2. Select **University sign-in (Demo)** and show the simulation notice.
3. Enter `z1000001@ad.unsw.edu.au` and select **Next** to open the student dashboard. Use the account menu to show the current user's details.
4. Sign out, choose **Staff sign-in** and sign in as `z9000001` (Administrator) or `z9000002` (Manager) with `123` to show the staff portal and its permissions.
5. To demonstrate returning after login, sign out, open `#/bookings`, then complete the mock sign-in as a student. SmartLab returns to My Bookings.

Entering a demo identity signs into the same existing backend account; it does not create a new account or reset its bookings or training records. Account descriptions reflect the initial seed data. In-memory changes reset when the backend process restarts.

The shell resolves the current user through `auth/me/` before showing protected content. It restores sessions after refresh, handles sign-out across tabs, refreshes identity on window focus or protected 403 responses, and clears only the matching session on 401. Temporary network failure retains the token and provides Retry. Successful demo registration always creates a student; roles are controlled by the server.

## Routes and ownership

React Router's `HashRouter` keeps the existing `#/...` URLs. These work with static hosting without server rewrite rules, preserve deep links and support browser Back/Forward. Frontend route guards complement server authorization.

| URL fragment | Access | Feature owner |
| --- | --- | --- |
| `#/login` | Public | A: sign-in and demo registration |
| `#/login/mock-sso` | Public, demo mode only | A: simulated university sign-in form (students) |
| `#/staff/login` | Public, demo mode only | A: staff sign-in and first-time activation (Admins, Managers) |
| `#/dashboard` | Student | A: booking counts, upcoming bookings and induction overview |
| `#/resources` | All roles | B: resource search and booking (Rooms / Equipment tabs, equipment grouped by room); **Find a free time** day grid with date, length, free-at, type, room and equipment-type filters (click a free time to book it); staff can book for someone else; urgent requests |
| `#/bookings` | All roles | B: bookings and cancellation (staff also see requests they made for others); Managers can reschedule |
| `#/induction` | All roles | C: evidence upload and review status |
| `#/admin/qualifications` | Admin, Manager | C: qualification review |
| `#/admin/bookings` | Admin, Manager | C: booking review |
| `#/admin/calendar-sync` | Admin, Manager | Development view (remove before delivery): Outlook connection check, sync status per booking, Retry |
| `#/manager/bookings` | Manager | C: room booking management, reschedule (Manager only) |
| `#/manager/users` | Manager | C: user list, Add staff (Admin or Manager; the role is fixed once created) with invite codes, reset staff access, deactivate/reactivate accounts |
| `#/account`, `#/help` | All authenticated roles | A: account details and portal guidance |

Everyone books under the same rules: Admins and Managers see **Book a Resource**, **My Bookings** and **Induction & Training** too, and can book for themselves or, under **Book for → Someone else**, for another person by zID (that person's induction is checked; the staff member is recorded as the creator). **Urgent request** lets anyone ask for a free time sooner than the normal booking window with a reason; only a Manager can approve it. Only Managers reschedule (My Bookings and Room Management). The student dashboard stays student-only, and an Admin cannot open any `#/manager/...` page. Students are never promoted to staff, and Admin and Manager do not switch: each role is fixed when the account is created. Managers create staff accounts with **Add staff**.

Induction prerequisites come from each requirement's `prerequisite_ids` (for example Advanced needs General). Until the prerequisite is verified the dependent induction shows as **Locked**, its upload is disabled, and resources that need it show which induction to complete first. Room maintenance does not affect the equipment kept in that room; each card shows its own status and reason.

`src/App.tsx` wraps the application in `HashRouter`. `src/app/AppRouter.tsx` maps addresses to feature pages with `Routes` and `Route`. `ProtectedLayout` redirects anonymous users to login, and `RequireAccess` checks the permission map in `src/app/routes.ts`. An allowed deep link is saved in router location state and restored after login; explicit sign-out clears this destination. Loading and session-recovery errors are handled before protected pages can render.

`AppLayout.tsx` owns responsive navigation and the account menu. `NavLink` highlights the current menu item, `Link` handles internal links, and `Outlet` displays the matching child page. Booking completion uses `useNavigate` to open My Bookings. When adding a protected page, add its `Route`, its role permissions in `routes.ts`, and its navigation entry if needed.

`src/features/auth/` owns authentication state and the login screen. `src/lib/api-client.ts` owns JSON/file transport and session invalidation. `src/features/booking/api.ts` holds the business API calls used by the booking and admin pages.

Dashboard data comes from `dashboard/`, `resources/` and `qualification-requirements/`. Upcoming bookings count only approved bookings whose start is in the future. Qualification summaries use each requirement's latest submission. Errors and empty states are distinct; users can refresh the overview. Dates are shown in Australia/Sydney. No mock totals are displayed.

`features/booking/Layout.tsx` is not mounted anywhere (kept for the team's reference). Shared UI styles are in `src/app/shell.css`, authentication styles in `features/auth/auth.css`, and dashboard styles in `features/dashboard/dashboard.css`. Booking and admin styles are in `features/booking/booking.css`.

## Checks

```powershell
npm run build
npm run lint
npm test
```

The Node tests cover role permissions, safe login return destinations, protected and public requests, multipart uploads, file downloads, expired sessions, network errors, and stale requests from a previous account.

Browser routing tests use Playwright with a separate development server on port 5174. API responses are mocked, so these tests do not require or modify backend data:

```powershell
npx playwright install chromium
npm run test:e2e
```

To use an existing Microsoft Edge installation instead of downloading Chromium:

```powershell
$env:PLAYWRIGHT_CHANNEL="msedge"
npm run test:e2e
```

For a manual walkthrough, sign in as each role, refresh a protected URL, use Back/Forward, try an unauthorized URL, open account details, sign out, and repeat navigation at mobile width. Students can reach the existing booking and induction flows from the dashboard; staff use the review/management pages.

## Integration boundaries

- University SSO still requires backend implementation and a frontend redirect/callback contract.
- Backend data lives in memory by default and resets when its process restarts; PostgreSQL mode keeps it (see `backend/database/README.md`).
- Outlook is configured on the backend; the frontend displays booking sync results and, for Admins and Managers, the Calendar Sync development page (`/admin/calendar-sync`: connection check, sync status, Retry). No Microsoft secrets belong in this app.
- Account details are read-only because the backend does not offer profile editing.
- Resource management, reporting, and more detailed administration pages remain separate Frontend C work.
- The login page and signed-in navigation use the same public UNSW logo. The login campus photo and logo sources are documented in `public/images/README.md`.
- Production hosting must route `/api` to the backend on the same origin; the Vite development proxy is not part of the production build.
