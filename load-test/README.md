# Sprint 3: Load Testing

This suite measures SmartLab while 200 students, 10 Admins and 2 Managers use it concurrently. It uses only the Python standard library and requires no load-testing tool.

Pass criteria: 95% of requests finish within one second, fewer than 1% fail, and duplicate bookings never occur for the same time.

## Files

| File | Purpose |
| --- | --- |
| `stress-ec2.sh` | Orchestrates the run: starts a temporary test copy on the server, runs the load test, generates a report and removes the copy |
| `load.py` | Simulates user actions and records the duration and outcome of every request |
| `report.py` | Converts the results into `summary.md` and `chart.html` |
| `profile.py` | Measures the duration and SQL query count of individual requests while the server is idle |
| `seed.sql` | Load-test accounts used only in the temporary database |
| `fill.sql` | One semester of historical data: approximately 5,000 bookings, used only in the temporary database |

## Running the tests

Run these commands in Git Bash. Docker must be installed on the server:

```bash
export EC2_HOST=ubuntu@<server-address>
bash load-test/stress-ec2.sh --small
bash load-test/stress-ec2.sh
bash load-test/stress-ec2.sh --profile
```

The three commands perform a trial run (about five minutes), the full-scale run (about 15 minutes), and individual-request profiling respectively. Other options are documented at the beginning of `stress-ec2.sh`.

- The test uses the committed `HEAD`; add `--worktree` to test uncommitted changes.
- The test copy is an independent Compose project with its own database, randomly generated password and key, email disabled, and ports available only on the server itself. It is removed automatically after the run and does not touch the production containers or database.
- The test copy and the production website share CPU during the test, so the production site becomes slower.
- Results are saved outside the repository under `../output/stress/<time>/`.

## Three scenarios

1. **Everyday use:** everyone is online for five minutes and performs an action every 5–15 seconds.
2. **Peak:** 200 students submit a request for the same time simultaneously.
3. **Ramp-up:** read-only actions every 1–3 seconds per user, increasing from 10 to 400 users; stop when p95 exceeds five seconds or the error rate exceeds 5%.

## Results (t3.small, two cores, with 5,000 historical bookings)

| Metric | Before optimisation | Round 1 | Round 2 | Round 3 | After merging into main | Deployed version |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Student home page (single request) | 820 ms | 16 ms | 17 ms | 8 ms | 8 ms | 8 ms |
| Booking Records (single request) | 9.1 s | 8.2 s | 0.96 s | 0.97 s | 0.95 s | 0.96 s |
| Everyday median | Not recorded separately | 14.8 s | 2.0 s | 390 ms | 210 ms | 214 ms |
| Everyday p95 | 30 s timeout | 27.3 s | 4.0 s | 1.8 s | 1.5 s | 1.7 s |
| Everyday errors | 98% | 0.45% | 0 | 0 | 0 | 0 |
| Peak p95 | 30 s timeout | 8.6 s | 6.2 s | 4.6 s | 4.9 s | 4.8 s |
| Ramp-up: maximum users with p95 < 1 s | Not tested | 10 | 50 | 100 | 100 | 50 |

The first four columns were measured on 29 October 2026 (the last of them at `03c4657`). "After merging into main" was measured on 1 November 2026 (`2cdfc86`, including the background scheduler and email queue). "Deployed version" was measured on 2 November 2026 (`f0a9760`, including review fixes).

- At 100 users, the ramp-up test sits exactly on the one-second boundary: the first two runs were below one second, while the deployed version measured 1.0 seconds, which does not meet the "below one second" criterion. A practical interpretation is that 50 users pass consistently and 100 users are at the boundary.
- The everyday scenario's p95 still does not meet the one-second target. At this point each endpoint is already fast; requests spend most of their time waiting in a queue, with average CPU utilisation at about 80%.
- The peak scenario passed its correctness check: all 200 requests succeeded, producing one pending request and 199 waitlisted requests, with no duplicate booking. Before the fix, every request timed out and correctness could not be checked.
- Email was disabled during load testing, so the results do not include email-delivery overhead. Differences between the last three columns are within normal variation and do not show that the merge or review fixes changed performance.
