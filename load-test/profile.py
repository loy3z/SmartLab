# Sprint 3: single-request timing, see README.md.
"""Where does one request spend its time? Run inside the stress copy's api container (no load running):

    docker compose -p smartlab-stress --env-file .env.stress exec -T api python - < profile.py

Times each endpoint 20 times on an idle server, counts SQL queries, then profiles a mixed batch.
"""
import cProfile
import io
import os
import pstats
import statistics
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()
from django.db import connection, reset_queries  # noqa: E402
from django.test import Client  # noqa: E402

client = Client(HTTP_HOST="localhost")
token = client.post("/api/v1/auth/demo-login/", {"zid": "z5000001"}, content_type="application/json").json()["access_token"]
staff = client.post("/api/v1/auth/staff-sign-in/", {"zid": "z9000001", "password": "123"},
                    content_type="application/json").json()["access_token"]
import datetime as _dt  # noqa: E402
_day = (_dt.datetime.now(_dt.timezone(_dt.timedelta(hours=11))).date() + _dt.timedelta(days=10)).isoformat()
student_paths = ["announcements/", "resources/", "qualification-requirements/", "dashboard/", "bookings/", "notifications/",
                 f"resources/day-overview/?date={_day}&duration_minutes=60",
                 f"resources/00000000-0000-0000-0000-000000000101/availability/?date={_day}"]
staff_paths = ["admin/overview/", "admin/bookings/", "admin/bookings/?status=ALL"]


def get(path, bearer):
    return client.get("/api/v1/" + path, HTTP_AUTHORIZATION=f"Bearer {bearer}")


print(f"{'endpoint':<32} {'median':>8} {'max':>8} {'queries':>8}")
for path, bearer in [(p, token) for p in student_paths] + [(p, staff) for p in staff_paths]:
    times, counts = [], []
    for _ in range(20):
        reset_queries()
        started = time.perf_counter()
        response = get(path, bearer)
        times.append((time.perf_counter() - started) * 1000)
        counts.append(len(connection.queries))
        assert response.status_code == 200, (path, response.status_code)
    print(f"{path:<32} {statistics.median(times):7.1f}ms {max(times):7.1f}ms {statistics.median(counts):8.0f}")

started = time.perf_counter()
connection.close()
connection.ensure_connection()
print(f"\nnew PostgreSQL connection: {(time.perf_counter() - started) * 1000:.1f} ms "
      f"(paid per request only when CONN_MAX_AGE=0; now {connection.settings_dict.get('CONN_MAX_AGE')})")

profiler = cProfile.Profile()
profiler.enable()
for _ in range(10):
    for path in student_paths:
        get(path, token)
profiler.disable()
out = io.StringIO()
pstats.Stats(profiler, stream=out).sort_stats("cumulative").print_stats(30)
print("\nmixed student batch (60 requests), top functions by cumulative time:")
print("\n".join(line for line in out.getvalue().splitlines() if line.strip())[:6000])
