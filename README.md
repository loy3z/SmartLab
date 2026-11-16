# SmartLab: Laboratory and Room Booking

**Online demo (Sprint 3 deployment):** http://3.24.73.197/#/login. Sign in with one of the zIDs under "Demo accounts" below.

Start here: [Project guide — workflows, pages and local startup](PROJECT_GUIDE.md).

UNSW COMP9900 group project (9900-F15E-BREAD). Students, Admins and Managers use the website to book laboratory rooms and individual pieces of equipment. The system checks induction eligibility, opening hours, booking windows and time conflicts, processes requests through an approval workflow, and synchronises approved bookings one way to Outlook Calendar.

- Backend: Django 5.2 + Django REST Framework, in [backend/](backend/)
- Frontend: React + TypeScript + Vite, in [frontend/](frontend/)
- Database: in-memory demonstration data by default; a local PostgreSQL database can also be used. See [backend/database/README.md](backend/database/README.md)

## Demo accounts

| zID | Role | Sign-in method |
| --- | --- | --- |
| `z1000001` | Student (General induction completed) | University sign-in (demo; enter the zID only) |
| `z1000002` | Student (no induction yet) | University sign-in (demo) |
| `z9000001` | Admin | Staff sign-in, demo password `123` |
| `z9000002` | Manager | Staff sign-in, demo password `123` |

All of these are fictional demonstration accounts. They work in the online deployment, the Docker setup below and the local in-memory demo mode.

## Run with Docker

This is the way to run the complete system (website, API, scheduler and PostgreSQL). It needs Docker with Docker Compose and nothing else.

From the repository root:

```bash
cp .env.docker.example .env.docker
docker compose --env-file .env.docker up -d --build
```

On Windows, use `copy .env.docker.example .env.docker` for the first line.

Then open **http://localhost** and sign in with one of the demo accounts above.

- The example file works unchanged for a local test: it turns on demo sign-in and loads the demo rooms, equipment, training requirements and accounts into a new database. Email and Outlook are off, so no external account is needed.
- The first build takes a few minutes. `docker compose --env-file .env.docker ps` should then show four containers running (`db`, `api`, `scheduler`, `web`), with `api` marked healthy.
- If port 80 is in use, set `WEB_PORT=8080` in `.env.docker` and open `http://localhost:8080`.
- To stop and delete everything, including the database: `docker compose --env-file .env.docker down -v`.

For a server deployment (passwords, host names, updates and backups), see [DEPLOY.md](DEPLOY.md).

## Local development (in-memory demo mode)

Use this mode when changing code or running tests. To view the application without developing it, open the online demo above.

Backend (from the `backend` directory):

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
$env:DEBUG = "true"
$env:ENABLE_DEMO_AUTH = "true"
$env:DJANGO_SECRET_KEY = "local-demo-only-change-this-key"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
export DEBUG=true ENABLE_DEMO_AUTH=true DJANGO_SECRET_KEY=local-demo-only-change-this-key
.venv/bin/python manage.py runserver 127.0.0.1:8000 --noreload
```

Frontend (open another terminal in the `frontend` directory):

```powershell
npm ci
npm run dev
```

Open the URL displayed by Vite (normally `http://localhost:5173`).

## Testing approach and coverage

### What is tested, and how

| Layer | Tests | Command | What it covers |
| --- | --- | --- | --- |
| Backend unit and API tests | 534 | `python manage.py test booking` (in `backend`) | Business rules, data validation, the permission matrix for the three roles, and error codes. Runs against the in-memory repository, so it needs no database |
| Backend PostgreSQL integration tests | 57 | `python manage.py test booking.tests.test_postgres` | The same acceptance cases run again on a real PostgreSQL database, plus transactions, row locks and migrations. Skipped when no database is configured; see Section 6 of [backend/database/README.md](backend/database/README.md) |
| Frontend unit tests | 99 | `npm test` (in `frontend`) | Logic modules: time and quota calculations, formatting, route guards, the API client |
| Frontend browser tests | 142 | `npm run test:e2e` | Component behaviour, user interactions and rendering for the pages of all three roles, in Chromium with Playwright |
| Static checks | — | `npm run lint`, `npm run build` | ESLint and the TypeScript compiler |

The counts are from 16 November 2026. All of these run in GitLab CI on every push and merge request ([.gitlab-ci.yml](.gitlab-ci.yml)); results are on the Pipelines page.

### Coverage

- **Backend: 94.8% of lines** (6,111 lines in `backend/booking`, tests excluded), measured on 16 November 2026 by running the backend suite under Python's built-in `trace` module. The PostgreSQL adapter (`postgres.py`) is not part of that figure because the in-memory run does not load it; the PostgreSQL integration tests exercise it instead. The lowest modules are the management commands that talk to a live Outlook account (72–81%).
- **Frontend:** no line-coverage figure is collected. The browser tests cover the pages of all three roles, and 30 of the 41 logic modules are imported directly by a unit test; the other 11 are small (the largest is 79 lines) and are reached through the browser tests.

### How the tests are written

- **Happy and sad cases.** Each rule is tested both ways: for example, a booking that is accepted, and the same booking refused for a missing induction, a closed room, a time conflict, a weekly limit or the wrong role. The error code and HTTP status are asserted.
- **Race conditions.** `test_approval_flow.py` starts four threads that request the same free slot at once and checks that only one holds it. `test_additional_hours.py` has two Managers approve the same request at the same moment and checks that it is confirmed once.
- **External services are mocked.** Microsoft Graph (Outlook) and SMTP (email) are replaced with mocks in `test_outlook.py`, `test_outlook_features.py` and `test_email_channel.py`, including failed deliveries and retries. No test contacts a real mail or calendar server.
- **Two storage adapters, one contract.** The service layer talks to a `Repository` interface. `test_119.py` and `test_postgres.py` run the same cases against the in-memory and the PostgreSQL implementation, so the two cannot drift apart.
- **Browser tests use synthetic API data.** Each Playwright test answers the API calls itself, and a call that no test data handles fails the test. This keeps the browser tests fast and independent of a database, so they do not fail for reasons outside the frontend. The cost is that they do not prove the frontend and backend agree; both sides are written against the shared API definition ([backend/docs/openapi.json](backend/docs/openapi.json)), and the deployed site is checked by hand as described below.

### What is not automated

- **Real Outlook and Gmail delivery.** These need live accounts. The manual steps and recorded results are in [backend/docs/outlook-setup.md](backend/docs/outlook-setup.md) and [backend/docs/email-setup.md](backend/docs/email-setup.md).
- **Load.** The scripts and method are in [load-test/README.md](load-test/README.md).
- **The deployed site.** After each deployment the health endpoint, the home page and the four containers are checked by hand; the steps are in [DEPLOY.md](DEPLOY.md).

### Running the tests locally

Set up the backend and frontend as in "Local development" below, then:

```powershell
# backend (from the backend directory)
.\.venv\Scripts\python.exe manage.py test booking
# frontend (from the frontend directory)
npm test
npm run lint
npm run build
npm run test:e2e
```

`npm run test:e2e` needs the Playwright browser once: `npx playwright install chromium`.

## Deployment

The online version is deployed and updated manually with Docker Compose. See [DEPLOY.md](DEPLOY.md). CI only runs tests and does not deploy automatically because some migrations delete data and require human confirmation.

## Documentation

| Document | Contents |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Overall structure, request flow and where to change a feature |
| [CHANGELOG.md](CHANGELOG.md) | Changes in each version and their reasons |
| [SPRINT3.md](SPRINT3.md) | Inventory of features and code added in Sprint 3 |
| [DEPLOY.md](DEPLOY.md) | Manual server deployment and updates |
| [backend/README.md](backend/README.md) | Features and rules, configuration, sign-in methods and handover notes |
| [frontend/README.md](frontend/README.md) | Frontend routes, sign-in flow and check commands |
| [backend/docs/frontend-api.md](backend/docs/frontend-api.md) | Frontend API instructions and error codes |
| [backend/docs/openapi.json](backend/docs/openapi.json) | Complete API definition (also available at `GET /api/schema/` while running) |
| [backend/docs/database-interface.md](backend/docs/database-interface.md) | Contract that database adapters must follow |
| [backend/database/README.md](backend/database/README.md) | Local PostgreSQL setup and upgrades |
| [backend/docs/outlook-setup.md](backend/docs/outlook-setup.md) | Outlook synchronisation configuration and test results |
| [backend/docs/email-setup.md](backend/docs/email-setup.md) | Email notification configuration and testing with a Gmail system mailbox |

## Notes

- Do not commit `.env`, database passwords, Microsoft tokens, Gmail app passwords or `backend/.local/` to Git.
- Use `git add` with specific file paths. Do not run `git add backend`, because it may include `.local`.
