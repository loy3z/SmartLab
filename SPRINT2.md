# Sprint 2: Demonstrable MVP

> Revised with DeepSeek (reviewed by Loy), 25 October 2026.
> Positioning: Sprint 2 is the next delivery. Its goal is to refine the implemented booking system until it can be demonstrated end to end, deployed locally and handed over, without adding more business features.
> Current state: versions 1.10–1.17.1 have been implemented. The code labels them `Sprint 3`, which is the team's internal naming. Sprint 2 focuses on consolidation, documentation and the demonstration.

## Goal

One person should be able to run the project locally within 10 minutes and demonstrate the main workflow in 5 minutes without getting stuck, seeing blank screens or encountering errors.

## Scope

| ID | Item | Current state | Required outcome | Acceptance criterion | Status |
| --- | --- | --- | --- | --- | --- |
| S2-1 | Main demonstration workflow | Features complete | Write a five-minute demonstration script: student sign-in → find a resource → make a booking → approval → check-in → calendar subscription → freeze/unfreeze | Complete the script without interruptions | ○ |
| S2-2 | Simulated SSO | `MockSsoPage`, `mock-sso.css` and `staff-sign-in` exist | Add documentation that clearly states this is a simulation, not real university SSO; cover the Student, staff, Admin and Manager entry points | All four roles can enter from the sign-in page | ◐ |
| S2-3 | Simulated Outlook Calendar | `.ics` subscription exists; one-way Graph sync through the main account exists | Use `.ics` consistently in the demonstration (no authorisation or compliance risk); explain on the page: "Copy the link into Outlook → subscribe from the Internet" | A student can subscribe in Outlook and see their bookings | ◐ |
| S2-4 | Workflow refinement | Known defects exist | Fix the blank state after changing dates in SlotPicker, layout shifts on 17 busy buttons, and five pieces of dead code (bell movement, two page fade-ins, double dialog entrance, two reduced-motion rules and the unused `App.css`) | Changing dates displays `Loading times…`; button width stays fixed while busy; bell behaviour is explicit (either it rings or is removed completely) | ○ |
| S2-5 | Remove remaining AI-like presentation | First pass (copy, font size, font and naming) complete | Replace decoration with information, replace demonstration data with realistic data, and accept work by task | Check each item against Section 4 of `claude/reports/2026-10-25-ai-flavor-sources.md` | ◐ |
| S2-6 | Local deployment | `start-backend.ps1` (migration + startup), in-memory/PostgreSQL modes and frontend `npm run dev` exist | Add a beginner-friendly startup guide covering what to install, commands to run, seed data, demonstration accounts and common errors | A new machine can run the project and sign in by following the guide | ◐ |
| S2-7 | Stability | Unknown | Run the complete `claude-tools/check-local.sh` suite and fix failures | env, backend, pg, OpenAPI, unit, lint, build and e2e all PASS, or the reason for each SKIP is documented | ○ |

## Explicitly out of Sprint 2 scope

- Real SSO and real Outlook OAuth: wait for the client to confirm account types and permissions (see `claude/reports/2026-10-25-outlook-personal-calendar.md`).
- Cloud deployment and load testing: move to Sprint 3.
- Chart-based visualisation (charts in Usage statistics, graphics on Today, the Room Management timeline and progress bars in My Bookings): move to Sprint 3.

## Code mapping

| Item | Code location |
| --- | --- |
| Simulated SSO | `frontend/src/features/auth/MockSsoPage.tsx`, `auth/mock-sso.css`; backend `auth/staff-sign-in/`, `auth/demo-login/` |
| Calendar subscription | `backend/booking/ics.py`, `features/booking/CalendarSubscribe.tsx` |
| Outlook through the main account | `backend/booking/outlook.py`, `calendar_sync.py`, `OUTLOOK_INVITE_MODE` |
| Local startup | `backend/start-backend.ps1` (local file, not committed to Git), `npm run dev` in `frontend` |
| Tests | `claude-tools/check-local.sh` |

## Acceptance

1. Complete the S2-1 demonstration script with no errors or blank pages.
2. Include the complete S2-7 test results in this delivery.
3. Clearly use the word "simulated" in the S2-2 and S2-3 documentation so the demonstration is not mistaken for a real integration.
