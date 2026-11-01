# Sprint 3: load test report, see README.md.
"""Turn a stress run (load.py output + server-stats.log) into summary.md (Chinese) and chart.html (English, for slides).

    python report.py <out folder>
Pass mark (agreed with Loy 2026-10-29): 95% of requests under 1 s and under 1% errors; in the peak, at most
one request may hold the slot.
"""
import csv
import html
import json
import os
import sys

P95_LIMIT_MS = 1000
ERROR_LIMIT = 0.01


def pct(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, max(0, int(round(p / 100 * len(values))) - 1))]


def stats(rows, seconds):
    ms = [r["ms"] for r in rows]
    n = len(rows)
    errors = sum(1 for r in rows if r["outcome"] == "error")
    business = sum(1 for r in rows if r["outcome"] == "business")
    return {"requests": n, "rps": n / seconds if seconds else 0, "p50": pct(ms, 50), "p95": pct(ms, 95),
            "p99": pct(ms, 99), "max": max(ms) if ms else 0, "errors": errors, "business": business,
            "error_rate": errors / n if n else 0}


def passed(s):
    return s["requests"] > 0 and s["p95"] < P95_LIMIT_MS and s["error_rate"] < ERROR_LIMIT


def server_window(server, start, end):
    cpu = [v for t, v, _ in server["cpu"] if start <= t <= end]
    steal = [s for t, _, s in server["cpu"] if start <= t <= end]
    api = [v for t, name, v in server["containers"] if start <= t <= end and name.endswith("api-1")]
    db = [v for t, name, v in server["containers"] if start <= t <= end and name.endswith("db-1")]
    avg = lambda xs: sum(xs) / len(xs) if xs else None
    return {"cpu_avg": avg(cpu), "cpu_max": max(cpu) if cpu else None, "steal_max": max(steal) if steal else None,
            "api_cpu_max": max(api) if api else None, "db_cpu_max": max(db) if db else None}


def read_server(path):
    server = {"cpu": [], "containers": []}
    if not os.path.exists(path):
        return server
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.split()
            try:
                if len(parts) >= 18 and parts[1] == "V":
                    v = parts[2:]
                    server["cpu"].append((int(parts[0]), 100 - int(v[14]), int(v[16])))
                elif len(parts) >= 4 and parts[1] == "C" and "smartlab-stress" in parts[2]:
                    server["containers"].append((int(parts[0]), parts[2], float(parts[3].rstrip("%"))))
            except (ValueError, IndexError):
                continue
    return server


def fmt(x, digits=0, unit=""):
    return "—" if x is None else f"{x:.{digits}f}{unit}"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out = sys.argv[1]
    result = json.load(open(os.path.join(out, "results.json"), encoding="utf-8"))
    rows = []
    with open(os.path.join(out, "samples.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["at"], r["ms"] = float(r["at"]), float(r["ms"])
            rows.append(r)
    server = read_server(os.path.join(out, "server-stats.log"))
    phases = result["phases"]

    daily_rows = [r for r in rows if r["phase"] == "daily"]
    daily = stats(daily_rows, phases["daily"][1] - phases["daily"][0])
    daily_server = server_window(server, *phases["daily"])
    peak_rows = [r for r in rows if r["phase"] == "peak"]
    peak = stats(peak_rows, result["peak"]["wall_seconds"])
    peak_server = server_window(server, *phases["peak"])
    labels = sorted({r["label"] for r in daily_rows})
    per_label = {label: stats([r for r in daily_rows if r["label"] == label], 1) for label in labels}
    ramp = []
    for step in result["ramp"]:
        s = stats([r for r in rows if r["phase"] == f"ramp-{step['users']}"], step["end"] - step["start"])
        s.update(users=step["users"], server=server_window(server, step["start"], step["end"]))
        ramp.append(s)
    capacity = max((s["users"] for s in ramp if passed(s)), default=None)
    codes = {}
    for r in rows:
        if r["outcome"] != "ok":
            key = (r["outcome"], r["status"], r["code"] or "-")
            codes[key] = codes.get(key, 0) + 1

    pk = result["peak"]
    people = result["people"]
    ok = lambda b: "通过" if b else "**不通过**"
    checked = pk.get("check_status") == 200 and pk["saved"] > 0
    peak_check = (ok(pk["no_double_booking"]) if checked
                  else "**未能检查**（请求或检查本身超时；超时的请求服务器可能仍在处理）")
    data_line = "—"
    setup = os.path.join(out, "setup.txt")
    if os.path.exists(setup):
        data_line = next((l.split("（", 1)[-1].rstrip("）\n") for l in open(setup, encoding="utf-8") if "测试数据已导入" in l), "—")
    folder = out.rstrip("/\\").replace("\\", "/").rsplit("/", 1)[-1]
    history = "带一学期历史数据（fill.sql）" if "-history" in folder else "不带历史数据"
    lines = [
        f"# 压力测试结果（{result['today']}）", "",
        f"对象：EC2 上的临时测试副本（t3.small，与线上同一台机器，独立数据库，邮件关闭），经 SSH 隧道 `{result['base']}`。",
        f"人数：{people['students']} 名学生、{people['admins']} 名 Admin、{people['managers']} 名 Manager。"
        f"通过标准：95% 请求 < {P95_LIMIT_MS} ms，出错 < {ERROR_LIMIT:.0%}；高峰时同一时段最多一个预约占用。",
        f"数据：{history}；开始时 {data_line}。", "",
        "## 结论", "",
        f"| 场景 | 请求数 | 每秒 | 中位数 | p95 | p99 | 最慢 | 出错 | 结果 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        f"| 日常（{result['daily_seconds']} 秒） | {daily['requests']} | {daily['rps']:.1f} | {daily['p50']:.0f} ms | {daily['p95']:.0f} ms | "
        f"{daily['p99']:.0f} ms | {daily['max']:.0f} ms | {daily['errors']}（{daily['error_rate']:.2%}） | {ok(passed(daily))} |",
        f"| 高峰（{people['students']} 人同一秒预约） | {peak['requests']} | — | {peak['p50']:.0f} ms | {peak['p95']:.0f} ms | "
        f"{peak['p99']:.0f} ms | {peak['max']:.0f} ms | {peak['errors']}（{peak['error_rate']:.2%}） | {ok(passed(peak))} |", "",
        f"- 高峰：{peak['requests']} 条请求在 {pk['wall_seconds']} 秒内全部返回；之后查到数据库里保存了 {pk['saved']} 条，状态 {pk['saved_by_status']}；"
        f"占用这个时段的 {pk['holding']} 条 → 重复预约检查{peak_check}。返回码 {pk['answers']}（0 = 30 秒超时）。",
        f"- 逐步加人：在标准内能撑住的最多 **{capacity if capacity else '低于第一档'}** 个同时在线的只读用户（每人每 1–3 秒一次操作）。",
        f"- 服务器 CPU（2 核合计）：日常平均 {fmt(daily_server['cpu_avg'], 0, '%')}、最高 {fmt(daily_server['cpu_max'], 0, '%')}；"
        f"高峰最高 {fmt(peak_server['cpu_max'], 0, '%')}；api 容器最高 {fmt(daily_server['api_cpu_max'], 0, '%')}（日常）/"
        f"{fmt(peak_server['api_cpu_max'], 0, '%')}（高峰），按单核算，200% 为满；steal 最高 {fmt(daily_server['steal_max'], 0, '%')}。", "",
        "## 逐步加人", "",
        "| 同时在线 | 请求数 | 每秒 | 中位数 | p95 | 出错 | 服务器 CPU 平均/最高 | api 容器最高 | 结果 |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for s in ramp:
        sv = s["server"]
        lines.append(f"| {s['users']} | {s['requests']} | {s['rps']:.1f} | {s['p50']:.0f} ms | {s['p95']:.0f} ms | "
                     f"{s['errors']}（{s['error_rate']:.2%}） | {fmt(sv['cpu_avg'], 0, '%')} / {fmt(sv['cpu_max'], 0, '%')} | "
                     f"{fmt(sv['api_cpu_max'], 0, '%')} | {ok(passed(s))} |")
    lines += ["", "## 日常场景各接口", "", "| 接口 | 次数 | 中位数 | p95 | 最慢 | 规则拒绝 | 出错 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for label in sorted(labels, key=lambda l: -per_label[l]["p95"]):
        s = per_label[label]
        lines.append(f"| {label} | {s['requests']} | {s['p50']:.0f} ms | {s['p95']:.0f} ms | {s['max']:.0f} ms | {s['business']} | {s['errors']} |")
    lines += ["", "## 非 2xx 返回", "", "| 类别 | HTTP | 代码 | 次数 |", "| --- | ---: | --- | ---: |"]
    for (outcome, status, code), n in sorted(codes.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {'规则拒绝' if outcome == 'business' else '出错'} | {status} | {code} | {n} |")
    with open(os.path.join(out, "summary.md"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")

    write_chart(out, result, daily, peak, ramp, capacity, checked)
    print("\n".join(lines[:16]))


def write_chart(out, result, daily, peak, ramp, capacity, checked):
    """One slide: the two scenarios against the pass mark, and p95 / throughput per ramp step."""
    W, H, left, top, bottom = 640, 260, 60, 20, 40
    steps = ramp or [{"users": 0, "p95": 0, "rps": 0}]
    top_ms = max([P95_LIMIT_MS * 1.5] + [s["p95"] for s in steps]) * 1.1
    bw = (W - left - 20) / len(steps)
    bars = []
    for i, s in enumerate(steps):
        h = (H - top - bottom) * s["p95"] / top_ms
        x = left + i * bw + bw * 0.2
        color = "#1D9E75" if s["p95"] < P95_LIMIT_MS and s.get("error_rate", 0) < ERROR_LIMIT else "#D85A30"
        bars.append(f'<rect x="{x:.0f}" y="{H - bottom - h:.0f}" width="{bw * 0.6:.0f}" height="{h:.0f}" rx="3" fill="{color}"/>'
                    f'<text x="{x + bw * 0.3:.0f}" y="{H - bottom - h - 6:.0f}" text-anchor="middle" class="v">{s["p95"]:.0f} ms</text>'
                    f'<text x="{x + bw * 0.3:.0f}" y="{H - bottom + 16:.0f}" text-anchor="middle" class="a">{s["users"]} users</text>'
                    f'<text x="{x + bw * 0.3:.0f}" y="{H - bottom + 32:.0f}" text-anchor="middle" class="a">{s["rps"]:.0f} req/s</text>')
    limit_y = H - bottom - (H - top - bottom) * P95_LIMIT_MS / top_ms
    svg = (f'<svg viewBox="0 0 {W} {H + 10}" role="img" aria-label="p95 response time per ramp step">'
           f'<line x1="{left}" y1="{limit_y:.0f}" x2="{W - 20}" y2="{limit_y:.0f}" stroke="#A32D2D" stroke-dasharray="5 4"/>'
           f'<text x="{left - 6}" y="{limit_y + 4:.0f}" text-anchor="end" class="a">1 s</text>'
           f'<line x1="{left}" y1="{H - bottom}" x2="{W - 20}" y2="{H - bottom}" stroke="currentColor" stroke-opacity=".3"/>'
           + "".join(bars) + "</svg>")
    pk = result["peak"]
    people = result["people"]
    verdict = lambda s: "Pass" if passed(s) else "Fail"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SmartLab stress test</title><style>
:root{{--bg:#fff;--fg:#1f1e1c;--muted:#6b6a65;--line:#e4e2da}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1f1e1c;--fg:#f1efe8;--muted:#b4b2a9;--line:#444441}}}}
body{{margin:0;padding:24px 16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:760px;margin:0 auto}} h1{{font-size:22px;font-weight:500;margin:0 0 4px}} p{{color:var(--muted);margin:0 0 16px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:16px 0 24px}}
.card{{border:1px solid var(--line);border-radius:12px;padding:12px 14px}} .card b{{display:block;font-size:22px;font-weight:500}}
.card span{{color:var(--muted);font-size:13px}} svg{{width:100%;height:auto;color:var(--fg)}} .v{{font-size:12px;fill:var(--fg)}} .a{{font-size:11px;fill:var(--muted)}}
h2{{font-size:16px;font-weight:500;margin:8px 0}}</style></head><body><main>
<h1>Stress test: {people['students']} students, {people['admins']} admins, {people['managers']} managers</h1>
<p>AWS EC2 t3.small (2 vCPU, 2 GB), Docker Compose, 3 gunicorn workers · {html.escape(result['today'])} · pass mark: 95% of requests under 1 s, under 1% errors</p>
<div class="cards">
<div class="card"><span>Everyday use · {result['daily_seconds']} s</span><b>p95 {daily['p95']:.0f} ms</b><span>{daily['requests']} requests · {daily['error_rate']:.2%} errors · {verdict(daily)}</span></div>
<div class="card"><span>Peak · {people['students']} bookings in the same second</span><b>p95 {peak['p95']:.0f} ms</b><span>{peak['error_rate']:.2%} errors · {verdict(peak)}</span></div>
<div class="card"><span>Same slot, same instant</span><b>{f"{pk['holding']} holds the slot" if checked else 'Not checked'}</b><span>{(f"{pk['saved'] - pk['holding']} waitlisted · " + ('no double booking' if pk['no_double_booking'] else 'DOUBLE BOOKING')) if checked else 'requests timed out'}</span></div>
<div class="card"><span>Most users within the pass mark</span><b>{capacity if capacity else '—'}</b><span>read-only users, one action every 1–3 s</span></div>
</div>
<h2>p95 response time as users increase</h2>{svg}
</main></body></html>"""
    with open(os.path.join(out, "chart.html"), "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    main()
