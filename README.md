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

All of these are fictional demonstration accounts. They work in both the online deployment and the local in-memory demo mode.

## Local development (in-memory demo mode)

Use this mode when changing code or running tests. To view the application without developing it, open the online demo above.

Backend (from the `backend` directory):

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DEBUG = "true"
$env:ENABLE_DEMO_AUTH = "true"
$env:DJANGO_SECRET_KEY = "local-demo-only-change-this-key"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export DEBUG=true ENABLE_DEMO_AUTH=true DJANGO_SECRET_KEY=local-demo-only-change-this-key
.venv/bin/python manage.py runserver 127.0.0.1:8000 --noreload
```

Frontend (open another terminal in the `frontend` directory):

```powershell
npm ci
npm run dev
```

Open the URL displayed by Vite (normally `http://localhost:5173`).

## Tests

```powershell
# backend
.\.venv\Scripts\python.exe manage.py test
# frontend
npm test
npm run lint
npm run build
npm run test:e2e
```

See Section 6 of [backend/database/README.md](backend/database/README.md) for instructions on running the PostgreSQL integration tests.

When code is pushed or an MR is opened, GitLab CI automatically runs `manage.py test booking`, `npm test`, `npm run lint` and `npm run build` (configured in [.gitlab-ci.yml](.gitlab-ci.yml)). View the results on the MR's Pipelines page. Since 12 November 2026, CI has also run the PostgreSQL integration tests and Playwright (`test:e2e`).

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
