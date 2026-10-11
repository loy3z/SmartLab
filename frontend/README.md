# SmartLab frontend

React + TypeScript + Vite + React Router. Frontend A provides the application shell, authentication, role routes, shared API client and student dashboard. Existing booking and administration features are mounted inside that shell.

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

| Demo zID | Role | Starting page |
| --- | --- | --- |
| `z1000001` | Student with general induction | Dashboard |
| `z1000002` | Student without induction | Dashboard |
| `z9000001` | Administrator | Qualification review |
| `z9000002` | Manager | Room management |

The shell resolves the current user through `auth/me/` before showing protected content. It restores sessions after refresh, handles sign-out across tabs, refreshes identity on window focus or protected 403 responses, and clears only the matching session on 401. Temporary network failure retains the token and provides Retry. Successful demo registration always creates a student; roles are controlled by the server.

## Routes and ownership

React Router's `HashRouter` keeps the existing `#/...` URLs. These work with static hosting without server rewrite rules, preserve deep links and support browser Back/Forward. Frontend route guards complement server authorization.

| URL fragment | Access | Feature owner |
| --- | --- | --- |
| `#/login` | Public | A: sign-in and demo registration |
| `#/dashboard` | Student | A: booking counts, upcoming bookings and induction overview |
| `#/resources` | Student | B: resource search and booking |
| `#/bookings` | Student | B: bookings, cancellation and rescheduling |
| `#/induction` | Student | C: evidence upload and review status |
| `#/admin/qualifications` | Admin, Manager | C: qualification review |
| `#/admin/bookings` | Admin, Manager | C: booking review |
| `#/manager/bookings` | Manager | C: room booking management |
| `#/account`, `#/help` | All authenticated roles | A: account details and portal guidance |

`src/App.tsx` wraps the application in `HashRouter`. `src/app/AppRouter.tsx` maps addresses to feature pages with `Routes` and `Route`. `ProtectedLayout` redirects anonymous users to login, and `RequireAccess` checks the permission map in `src/app/routes.ts`. An allowed deep link is saved in router location state and restored after login; explicit sign-out clears this destination. Loading and session-recovery errors are handled before protected pages can render.

`AppLayout.tsx` owns responsive navigation and the account menu. `NavLink` highlights the current menu item, `Link` handles internal links, and `Outlet` displays the matching child page. Booking completion uses `useNavigate` to open My Bookings. The former custom `navigation.ts` hash listener has been removed. When adding a protected page, add its `Route`, its role permissions in `routes.ts`, and its navigation entry if needed.

`src/features/auth/` owns authentication state and the login screen. `src/lib/api-client.ts` owns JSON/file transport and session invalidation. `src/features/booking/api.ts` retains the existing business API exports for B/C compatibility.

Dashboard data comes from `dashboard/`, `resources/` and `qualification-requirements/`. Upcoming bookings count only approved bookings whose start is in the future. Qualification summaries use each requirement's latest submission. Errors and empty states are distinct; users can refresh the overview. Dates are shown in Australia/Sydney. No mock totals are displayed.

The prior `features/booking/Layout.tsx` is retained for the team's reference but is no longer mounted. Shared UI styles are in `src/app/shell.css`, authentication styles in `features/auth/auth.css`, and dashboard styles in `features/dashboard/dashboard.css`. Existing B/C styles remain in `features/booking/booking.css`.

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
- Backend data currently lives in memory and resets when its process restarts.
- Outlook is configured on the backend; the frontend displays booking sync results. No Microsoft secrets belong in this app.
- Account details are read-only because the backend does not offer profile editing.
- Resource management, reporting, and more detailed administration pages remain separate Frontend C work.
- The login page and signed-in navigation use the same public UNSW logo. The login campus photo and logo sources are documented in `public/images/README.md`.
- Production hosting must route `/api` to the backend on the same origin; the Vite development proxy is not part of the production build.
