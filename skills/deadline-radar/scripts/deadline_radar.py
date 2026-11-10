#!/usr/bin/env python3
"""deadline-radar — track assignment deadlines, rank urgency, plan work, and
nudge when a deadline is close but its repository has gone quiet.

Standard library only (PyYAML is used if present, JSON otherwise), no
credentials required.  Original work for CSCI 599 Assignment 3.

Data file (YAML or JSON), default ``~/.deadline-radar/deadlines.json``
or ``$DEADLINE_RADAR_FILE``:

    {"deadlines": [
      {"id": "a3", "title": "CSCI 599 A3", "due": "2026-11-20T23:59:00-08:00",
       "course": "CSCI 599", "est_hours": 12, "done_hours": 3,
       "repo": "octocat/Hello-World", "done": false}
    ]}

Commands
    list   [--days N] [--json]            upcoming deadlines with urgency tier
    add    --title T --due ISO [--id ID] [--course C] [--est-hours H] [--repo owner/name]
    done   --id ID                         mark complete
    log    --id ID --hours H               record hours worked
    plan   [--days N] [--hours-per-day H]  spread remaining work over the days left
    check  [--days N]                      alerts: due soon, overdue, quiet repos
    demo                                   run against a temporary synthetic file
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # optional
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

VERSION = "1.0.0"
TIERS = [  # (name, max_hours_left)
    ("overdue", 0),
    ("due-24h", 24),
    ("due-3d", 72),
    ("due-7d", 168),
    ("later", math.inf),
]


def default_path() -> Path:
    env = os.environ.get("DEADLINE_RADAR_FILE") or os.environ.get("A3_DEADLINES_FILE")
    return Path(env) if env else Path.home() / ".deadline-radar" / "deadlines.json"


def load(path: Path) -> dict:
    if not path.exists():
        return {"deadlines": []}
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        if yaml is None:
            raise SystemExit("PyYAML not installed; use a .json data file")
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text or "{}")
    data.setdefault("deadlines", [])
    return data


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if path.suffix in (".yaml", ".yml") and yaml is not None:
        tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    else:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def parse_due(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("Z", "+00:00")
        if len(s) == 10:  # date only -> end of day local
            s += "T23:59:00"
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.astimezone()  # interpret naive times in the host's local zone
    return dt


def tier(hours_left: float) -> str:
    for name, limit in TIERS:
        if hours_left <= limit:
            return name
    return "later"


def enrich(d: dict, now: datetime) -> dict:
    due = parse_due(d["due"])
    hours_left = (due - now).total_seconds() / 3600
    est = float(d.get("est_hours") or 0)
    done = float(d.get("done_hours") or 0)
    remaining = max(0.0, est - done)
    days_left = max(hours_left / 24, 0.0)
    pace = round(remaining / max(days_left, 0.5), 1) if remaining else 0.0
    out = dict(d)
    out.update({
        "due_iso": due.isoformat(),
        "hours_left": round(hours_left, 1),
        "days_left": round(hours_left / 24, 1),
        "tier": tier(hours_left),
        "remaining_hours": remaining,
        "needed_hours_per_day": pace,
    })
    return out


def upcoming(data: dict, now: datetime, days: int) -> list[dict]:
    items = [enrich(d, now) for d in data["deadlines"] if not d.get("done")]
    items = [i for i in items if i["hours_left"] <= days * 24]
    items.sort(key=lambda i: i["hours_left"])
    return items


def repo_last_commit(repo: str, timeout: float = 8.0) -> dict:
    """Public GitHub API; token optional via GITHUB_TOKEN / A3_GITHUB_TOKEN."""
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/commits?per_page=1",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "deadline-radar"})
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("A3_GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            commits = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"ok": False, "error": type(exc).__name__}
    if not commits:
        return {"ok": True, "last_commit": None}
    when = commits[0]["commit"]["committer"]["date"]
    return {"ok": True, "last_commit": when, "sha": commits[0]["sha"][:7]}


def check(data: dict, now: datetime, days: int = 7, quiet_days: float = 2.0, fetch=repo_last_commit) -> list[dict]:
    alerts = []
    for i in upcoming(data, now, days):
        if i["tier"] == "overdue":
            alerts.append({"id": i.get("id"), "kind": "overdue", "message": f"{i['title']} is overdue by {abs(i['hours_left']):.0f}h"})
            continue
        if i["tier"] in ("due-24h", "due-3d"):
            msg = f"{i['title']} is due in {i['days_left']} days ({i['due_iso']})"
            if i["remaining_hours"]:
                msg += f"; ~{i['remaining_hours']:.0f}h of work left (~{i['needed_hours_per_day']}h/day)"
            alerts.append({"id": i.get("id"), "kind": i["tier"], "message": msg})
            repo = i.get("repo")
            if repo:
                info = fetch(repo)
                if info.get("ok") and info.get("last_commit"):
                    last = datetime.fromisoformat(info["last_commit"].replace("Z", "+00:00"))
                    idle = (now - last).total_seconds() / 86400
                    if idle >= quiet_days:
                        alerts.append({"id": i.get("id"), "kind": "repo-quiet",
                                       "message": f"{repo} has had no commits for {idle:.1f} days and {i['title']} is due in {i['days_left']} days — push your work in progress?"})
                elif not info.get("ok"):
                    alerts.append({"id": i.get("id"), "kind": "repo-unknown", "message": f"could not check {repo} ({info.get('error')})"})
    return alerts


def plan(data: dict, now: datetime, days: int = 7, hours_per_day: float = 4.0) -> list[dict]:
    """Greedy earliest-deadline-first schedule of remaining hours."""
    items = [i for i in upcoming(data, now, days) if i["remaining_hours"] > 0 and i["tier"] != "overdue"]
    schedule = []
    capacity = {}
    for i in items:
        need = i["remaining_hours"]
        day = 0
        due_day = max(0, int(i["hours_left"] // 24))
        while need > 0 and day <= due_day:
            free = hours_per_day - capacity.get(day, 0)
            if free > 0:
                take = min(free, need)
                capacity[day] = capacity.get(day, 0) + take
                schedule.append({"day": (now + timedelta(days=day)).date().isoformat(), "id": i.get("id"),
                                 "title": i["title"], "hours": round(take, 1)})
                need -= take
            day += 1
        if need > 0:
            schedule.append({"day": None, "id": i.get("id"), "title": i["title"], "hours": round(need, 1),
                             "warning": "does not fit before the deadline at this hours/day"})
    return schedule


def _print(obj, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
        return
    if isinstance(obj, list):
        if not obj:
            print("(nothing)")
        for row in obj:
            if "tier" in row:
                print(f"[{row['tier']:>8}] {row['title']} — due {row['due_iso']} ({row['days_left']}d)"
                      + (f", {row['remaining_hours']:.0f}h left" if row.get("remaining_hours") else ""))
            elif "message" in row:
                print(f"⚠ {row['message']}")
            else:
                print(f"{row.get('day') or 'UNSCHEDULED'}: {row['title']} {row['hours']}h" + (f"  ({row['warning']})" if row.get("warning") else ""))
    else:
        print(obj)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="deadline_radar", description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--days", type=int, default=14)
    p = sub.add_parser("add")
    p.add_argument("--title", required=True); p.add_argument("--due", required=True)
    p.add_argument("--id"); p.add_argument("--course"); p.add_argument("--est-hours", type=float)
    p.add_argument("--repo")
    p = sub.add_parser("done"); p.add_argument("--id", required=True)
    p = sub.add_parser("log"); p.add_argument("--id", required=True); p.add_argument("--hours", type=float, required=True)
    p = sub.add_parser("plan"); p.add_argument("--days", type=int, default=7); p.add_argument("--hours-per-day", type=float, default=4.0)
    p = sub.add_parser("check"); p.add_argument("--days", type=int, default=7); p.add_argument("--quiet-days", type=float, default=2.0)
    sub.add_parser("demo")
    a = ap.parse_args(argv)

    now = datetime.now(timezone.utc).astimezone()
    if a.cmd == "demo":
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "deadlines.json"
            save(f, {"deadlines": [
                {"id": "demo-a3", "title": "Demo assignment", "due": (now + timedelta(days=2)).isoformat(), "est_hours": 8, "done_hours": 2},
                {"id": "demo-quiz", "title": "Demo quiz", "due": (now + timedelta(hours=20)).isoformat()},
                {"id": "demo-paper", "title": "Demo paper", "due": (now + timedelta(days=6)).isoformat(), "est_hours": 10},
            ]})
            d = load(f)
            print("== list ==");  _print(upcoming(d, now, 14), a.json)
            print("== check =="); _print(check(d, now, fetch=lambda r: {"ok": False, "error": "demo"}), a.json)
            print("== plan ==");  _print(plan(d, now), a.json)
        return 0

    path = a.file or default_path()
    data = load(path)
    if a.cmd == "list":
        _print(upcoming(data, now, a.days), a.json)
    elif a.cmd == "add":
        did = a.id or "".join(ch for ch in a.title.lower().replace(" ", "-") if ch.isalnum() or ch == "-")[:40]
        parse_due(a.due)  # validate
        if any(d.get("id") == did for d in data["deadlines"]):
            print(f"id {did!r} already exists", file=sys.stderr); return 2
        data["deadlines"].append({k: v for k, v in {"id": did, "title": a.title, "due": a.due, "course": a.course,
                                                    "est_hours": a.est_hours, "repo": a.repo, "done": False}.items() if v is not None})
        save(path, data); print(f"added {did}")
    elif a.cmd in ("done", "log"):
        for d in data["deadlines"]:
            if d.get("id") == a.id:
                if a.cmd == "done":
                    d["done"] = True
                else:
                    d["done_hours"] = float(d.get("done_hours") or 0) + a.hours
                save(path, data); print(f"updated {a.id}"); break
        else:
            print(f"no deadline with id {a.id!r}", file=sys.stderr); return 2
    elif a.cmd == "plan":
        _print(plan(data, now, a.days, a.hours_per_day), a.json)
    elif a.cmd == "check":
        _print(check(data, now, a.days, a.quiet_days), a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
