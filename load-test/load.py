# Sprint 3: load test, see README.md.
"""SmartLab stress test (Python standard library only). Run by stress-ec2.sh; can also be run by hand:

    python load.py --base http://127.0.0.1:18080 --out <folder>

Three phases against a temporary copy of the site (never the live database):
  daily  every account signed in, each person acts every 5-15 s (students browse, book and cancel;
         Admins and Managers check Today, the approval queue, Booking Records, reports and the audit log)
  peak   all students submit the same time slot in the same instant; afterwards at most one request may
         hold the slot (PENDING_APPROVAL or APPROVED) and the rest must be on the waitlist
  ramp   read-only users with 1-3 s think time, stepping up until the site clearly slows down

Every request is written to <out>/samples.csv; <out>/results.json has the phase windows and checks that
report.py turns into the summary. Outcome of a request:
  ok        2xx
  business  4xx with an error code from the booking rules (weekly limit, slot taken ...); expected, not a failure
  error     5xx, 401/403/404, malformed answers, timeouts and broken connections
"""
import argparse
import csv
import http.client
import json
import os
import random
import threading
import time
from datetime import date, datetime, time as dtime, timedelta, timezone
from urllib.parse import urlencode, urlsplit

try:
    from zoneinfo import ZoneInfo
    SYDNEY = ZoneInfo("Australia/Sydney")
except Exception:  # Windows Python without tzdata: Sydney summer time (AEDT), October to April
    SYDNEY = timezone(timedelta(hours=11))

STAFF_PASSWORD = "123"  # demo staff password from seed_users.sql (fake accounts in the temporary database)
GENERAL_INDUCTION = "00000000-0000-0000-0000-000000000001"
LAB_ROOM_1 = "00000000-0000-0000-0000-000000000101"
NOT_ERRORS = {400, 409, 422}  # rule violations come back as these, with an error code

samples = []  # (epoch seconds, phase, label, status, ms, outcome, code)
phase_now = ["setup"]


class Client:
    """One person: one keep-alive connection, like one browser tab."""

    def __init__(self, base, timeout):
        parts = urlsplit(base)
        self.host, self.port, self.timeout = parts.hostname, parts.port or 80, timeout
        self.conn = None
        self.token = None

    def call(self, label, method, path, body=None, record=True):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        started = time.perf_counter()
        status, data, code = 0, None, ""
        try:
            if self.conn is None:
                self.conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
            self.conn.request(method, "/api/v1/" + path, body=payload, headers=headers)
            response = self.conn.getresponse()
            raw = response.read()
            status = response.status
            if raw:
                try:
                    data = json.loads(raw)
                except ValueError:
                    data = None
            if response.getheader("Connection", "").lower() == "close":
                self.close()
        except (OSError, http.client.HTTPException) as exc:
            self.close()
            code = type(exc).__name__
        ms = (time.perf_counter() - started) * 1000
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            code = data["error"].get("code", "")
        if 200 <= status < 300:
            outcome = "ok"
        elif status in NOT_ERRORS and code:
            outcome = "business"
        else:
            outcome = "error"
        if record:
            samples.append((time.time(), phase_now[0], label, status, round(ms, 1), outcome, code))
        return status, data

    def close(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except OSError:
                pass
        self.conn = None


def results(data):
    return data.get("results", []) if isinstance(data, dict) else []


# ---- what people do ------------------------------------------------------------------------------------------

class World:
    """Shared facts: resources a student may book and the date ranges for each phase."""

    def __init__(self, resources, today):
        self.bookable = [r["id"] for r in resources
                         if r.get("required_qualification_id") in (None, GENERAL_INDUCTION) and r.get("active", True)]
        self.today = today
        self.peak_day = today + timedelta(days=30)
        # The daily phase books only before the peak day's week, so the weekly limit (3) leaves the peak week free.
        last = self.peak_day - timedelta(days=self.peak_day.weekday() + 1)
        self.daily_days = [today + timedelta(days=d) for d in range(8, 31) if today + timedelta(days=d) <= last]


def slot(day, hour, minutes=60):
    start = datetime.combine(day, dtime(hour, 0), SYDNEY)
    return start.isoformat(), (start + timedelta(minutes=minutes)).isoformat()


def student_home(c, w):
    c.call("GET dashboard", "GET", "dashboard/")
    c.call("GET resources", "GET", "resources/")
    c.call("GET requirements", "GET", "qualification-requirements/")
    c.call("GET announcements", "GET", "announcements/")


def student_browse(c, w):
    day = random.choice(w.daily_days or [w.peak_day])
    c.call("GET resources", "GET", "resources/")
    c.call("GET day-overview", "GET", "resources/day-overview/?" + urlencode({"date": day.isoformat()}))
    c.call("GET availability", "GET", f"resources/{random.choice(w.bookable)}/availability/?"
           + urlencode({"date": day.isoformat(), "duration_minutes": 60}))


def student_my_bookings(c, w):
    c.call("GET bookings", "GET", "bookings/")
    c.call("GET notifications", "GET", "notifications/")


def student_book(c, w, mine):
    if not w.daily_days:
        return
    start, end = slot(random.choice(w.daily_days), random.randint(8, 18))
    status, data = c.call("POST booking", "POST", "bookings/", {
        "resource_id": random.choice(w.bookable), "start": start, "end": end, "purpose": "stress test"})
    if status in (200, 201) and isinstance(data, dict):
        mine.append(data["id"])


def student_cancel(c, w, mine):
    if mine:
        c.call("POST cancel", "POST", f"bookings/{mine.pop(random.randrange(len(mine)))}/cancel/", {})
    else:
        student_my_bookings(c, w)


def staff_today(c, w):
    c.call("GET admin overview", "GET", "admin/overview/")
    c.call("GET resources", "GET", "resources/")
    c.call("GET announcements", "GET", "announcements/")


def staff_approve(c, w):
    status, data = c.call("GET approval queue", "GET", "admin/bookings/")
    queue = results(data)
    if queue:
        target = random.choice(queue[:20])
        c.call("POST approve", "POST", f"admin/bookings/{target['id']}/review/", {"decision": "APPROVED", "reason": ""})


def staff_records(c, w):
    c.call("GET booking records", "GET", "admin/bookings/?status=ALL")


def staff_report(c, w):
    first = w.today - timedelta(days=30)
    c.call("GET usage report", "GET", "admin/reports/usage/?"
           + urlencode({"first_date": first.isoformat(), "last_date": w.today.isoformat()}))


def staff_audit(c, w):
    c.call("GET audit", "GET", "admin/audit/")


def manager_users(c, w):
    c.call("GET users", "GET", "admin/users/")


STUDENT_ACTIONS = [(student_home, 30), (student_browse, 30), (student_my_bookings, 15), ("book", 20), ("cancel", 5)]
ADMIN_ACTIONS = [(staff_today, 35), (staff_approve, 25), (staff_records, 20), (staff_report, 10), (staff_audit, 10)]
MANAGER_ACTIONS = ADMIN_ACTIONS + [(manager_users, 10)]


def pick(actions):
    return random.choices([a for a, _ in actions], weights=[w for _, w in actions])[0]


# ---- phases --------------------------------------------------------------------------------------------------

def sign_in(base, timeout, role, zid):
    c = Client(base, timeout)
    if role == "STUDENT":
        status, data = c.call("POST student sign-in", "POST", "auth/demo-login/", {"zid": zid})
    else:
        status, data = c.call("POST staff sign-in", "POST", "auth/staff-sign-in/", {"zid": zid, "password": STAFF_PASSWORD})
    if status != 200:
        raise SystemExit(f"sign-in failed for {zid}: HTTP {status} {data}")
    c.token = data["access_token"]
    return c


def run_threads(targets):
    threads = [threading.Thread(target=t, daemon=True) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def daily(people, w, seconds):
    deadline = time.time() + seconds
    booked = {}

    def person(role, c):
        mine = booked.setdefault(id(c), [])
        actions = {"STUDENT": STUDENT_ACTIONS, "ADMIN": ADMIN_ACTIONS, "MANAGER": MANAGER_ACTIONS}[role]
        time.sleep(random.uniform(0, 15))  # people do not all start at the same second
        while time.time() < deadline:
            action = pick(actions)
            if action == "book":
                student_book(c, w, mine)
            elif action == "cancel":
                student_cancel(c, w, mine)
            else:
                action(c, w)
            time.sleep(random.uniform(5, 15))

    run_threads([lambda r=role, c=c: person(r, c) for role, c in people])


def peak(students, admin, w):
    """All students press Submit for Lab Room 1, peak day 15:00-16:00, at the same moment."""
    start, end = slot(w.peak_day, 15)
    barrier = threading.Barrier(len(students))
    answers = []

    def press(c):
        barrier.wait()
        status, data = c.call("POST booking (same slot)", "POST", "bookings/",
                              {"resource_id": LAB_ROOM_1, "start": start, "end": end, "purpose": "stress peak"})
        answers.append((status, data.get("status") if isinstance(data, dict) else None))

    began = time.time()
    run_threads([lambda c=c: press(c) for c in students])
    wall = time.time() - began
    status, data = admin.call("GET peak check", "GET", "admin/bookings/?" + urlencode({
        "status": "ALL", "resource_id": LAB_ROOM_1}), record=False)
    rows = [b for b in results(data) if b.get("purpose") == "stress peak"]
    by_status = {}
    for b in rows:
        by_status[b["status"]] = by_status.get(b["status"], 0) + 1
    holding = by_status.get("PENDING_APPROVAL", 0) + by_status.get("APPROVED", 0)
    answer_counts = {}
    for code, booking_status in answers:
        key = f"{code} {booking_status or ''}".strip()
        answer_counts[key] = answer_counts.get(key, 0) + 1
    return {"slot": [start, end], "wall_seconds": round(wall, 2), "answers": answer_counts,
            "saved_by_status": by_status, "holding": holding, "saved": len(rows),
            "no_double_booking": holding <= 1, "check_status": status}


def ramp(students, w, steps, seconds, out_steps):
    for users in steps:
        phase_now[0] = f"ramp-{users}"
        deadline = time.time() + seconds
        base_clients = [students[i % len(students)] for i in range(users)]

        def reader(template):
            c = Client(f"http://{template.host}:{template.port}", template.timeout)
            c.token = template.token
            time.sleep(random.uniform(0, 3))
            while time.time() < deadline:
                random.choice([student_home, student_browse, student_my_bookings])(c, w)
                time.sleep(random.uniform(1, 3))
            c.close()

        began = time.time()
        run_threads([lambda t=t: reader(t) for t in base_clients])
        mine = [s for s in samples if s[1] == phase_now[0]]
        errors = sum(1 for s in mine if s[5] == "error")
        ms = sorted(s[4] for s in mine)
        p95 = ms[int(len(ms) * 0.95) - 1] if ms else 0
        out_steps.append({"users": users, "start": began, "end": time.time(), "requests": len(mine)})
        print(f"[stress] ramp {users} users: {len(mine)} requests, p95 {p95:.0f} ms, errors {errors}", flush=True)
        if mine and (p95 > 5000 or errors / len(mine) > 0.05):
            print("[stress] ramp stopped: p95 over 5 s or errors over 5%", flush=True)
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:18080")
    ap.add_argument("--out", required=True)
    ap.add_argument("--students", type=int, default=200)
    ap.add_argument("--admins", type=int, default=10)
    ap.add_argument("--managers", type=int, default=2)
    ap.add_argument("--daily-seconds", type=int, default=300)
    ap.add_argument("--ramp", default="10,25,50,100,200,300,400")
    ap.add_argument("--ramp-seconds", type=int, default=60)
    ap.add_argument("--timeout", type=float, default=30)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    random.seed(9900)

    student_zids = [f"z5{n:06d}" for n in range(1, args.students + 1)]
    admin_zids = (["z9000001"] + [f"z91{n:05d}" for n in range(1, 10)])[:args.admins]
    manager_zids = ["z9000002", "z9200001"][:args.managers]
    t0 = time.time()
    students, failed = [], []
    lock = threading.Lock()

    def student_in(zid):
        try:
            c = sign_in(args.base, args.timeout, "STUDENT", zid)
        except SystemExit as exc:  # a thread cannot stop the script; report after the batch
            failed.append(str(exc))
            return
        with lock:
            students.append(c)

    for i in range(0, len(student_zids), 20):  # sign in 20 at a time, like a lecture arriving
        run_threads([lambda z=z: student_in(z) for z in student_zids[i:i + 20]])
        if failed:
            raise SystemExit(f"{len(failed)} student sign-ins failed; first: {failed[0]}")
    students.sort(key=lambda c: c.token)
    admins = [sign_in(args.base, args.timeout, "ADMIN", z) for z in admin_zids]
    managers = [sign_in(args.base, args.timeout, "MANAGER", z) for z in manager_zids]
    print(f"[stress] signed in {len(students)} students, {len(admins)} admins, {len(managers)} managers "
          f"in {time.time() - t0:.0f} s", flush=True)

    _, data = admins[0].call("GET resources", "GET", "resources/", record=False)
    w = World(results(data), datetime.now(SYDNEY).date())
    if not w.bookable:
        raise SystemExit("no resource a student with the general induction can book")
    phases = {}

    phase_now[0] = "daily"
    began = time.time()
    print(f"[stress] daily: {len(students) + len(admins) + len(managers)} people for {args.daily_seconds} s", flush=True)
    daily([("STUDENT", c) for c in students] + [("ADMIN", c) for c in admins] + [("MANAGER", c) for c in managers],
          w, args.daily_seconds)
    phases["daily"] = [began, time.time()]

    phase_now[0] = "peak"
    began = time.time()
    print(f"[stress] peak: {len(students)} students submit the same slot at once", flush=True)
    peak_result = peak(students, admins[0], w)
    phases["peak"] = [began, time.time()]
    print(f"[stress] peak: answers {peak_result['answers']}; holding the slot {peak_result['holding']}", flush=True)

    ramp_steps = []
    ramp(students, w, [int(n) for n in args.ramp.split(",") if n], args.ramp_seconds, ramp_steps)

    for c in students + admins + managers:
        c.close()
    with open(os.path.join(args.out, "samples.csv"), "w", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["at", "phase", "label", "status", "ms", "outcome", "code"])
        out.writerows(samples)
    with open(os.path.join(args.out, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"base": args.base, "people": {"students": len(students), "admins": len(admins), "managers": len(managers)},
                   "daily_seconds": args.daily_seconds, "phases": phases, "peak": peak_result, "ramp": ramp_steps,
                   "today": w.today.isoformat(), "bookable_resources": len(w.bookable)}, f, indent=2)
    print(f"[stress] wrote {len(samples)} samples to {args.out}", flush=True)


if __name__ == "__main__":
    main()
