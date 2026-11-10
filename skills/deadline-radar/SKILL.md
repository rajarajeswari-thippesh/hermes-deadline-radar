---
name: deadline-radar
description: Track assignment/project deadlines, rank urgency, plan the remaining work hours, and warn when a deadline is near but its GitHub repo has gone quiet.
version: 1.0.0
author: CSCI 599 A3 student
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [productivity, deadlines, planning, students]
    related_skills: []
---

# Deadline Radar

Keeps a small deadlines file and answers "what's due?", "can I fit it all?", and "am I falling
behind?". Standard-library Python, no API keys (a GitHub token is optional for higher rate limits).

## When to Use
- The user mentions a due date, assignment, submission, or "what do I have this week".
- Planning: "how many hours a day do I need?", "make me a work plan".
- Proactive checks (cron): deadlines inside 3 days, overdue items, quiet repositories.

## Quick Reference
Run the bundled script (data file defaults to `~/.deadline-radar/deadlines.json`; override with
`--file` or `DEADLINE_RADAR_FILE`):

| Task | Command |
|---|---|
| try it with synthetic data | `python3 ${HERMES_SKILL_DIR}/scripts/deadline_radar.py demo` |
| list next 14 days | `python3 ${HERMES_SKILL_DIR}/scripts/deadline_radar.py list --days 14` |
| add | `python3 ${HERMES_SKILL_DIR}/scripts/deadline_radar.py add --title "CSCI 599 A3" --due 2026-11-20T23:59:00-08:00 --est-hours 12 --repo owner/name` |
| log work | `python3 ${HERMES_SKILL_DIR}/scripts/deadline_radar.py log --id csci-599-a3 --hours 2` |
| mark done | `python3 ${HERMES_SKILL_DIR}/scripts/deadline_radar.py done --id csci-599-a3` |
| work plan | `python3 ${HERMES_SKILL_DIR}/scripts/deadline_radar.py plan --days 7 --hours-per-day 4` |
| alerts | `python3 ${HERMES_SKILL_DIR}/scripts/deadline_radar.py check --days 7` |

Add `--json` before the sub-command for machine-readable output.

If tools named `a3_deadlines_list`, `a3_deadlines_add`, `a3_deadlines_update` and `a3_deadlines_plan`
are available (the author's assistant exposes the same logic as tools and has no shell), use those
instead of the script.

## Procedure
1. **Adding:** confirm title and due date/time with timezone; ask for an hour estimate if the user
   wants planning. Use a public `owner/repo` only if the user gives one.
2. **Listing:** group by tier — overdue, due-24h, due-3d, due-7d, later — soonest first, with days
   left and remaining hours.
3. **Planning:** run `plan`; present it per day; if anything prints "does not fit", say so and suggest
   raising hours/day or renegotiating.
4. **Checking:** run `check`; turn each alert into one sentence with a next step. `repo-quiet` means
   no commits for ≥2 days while the deadline is ≤3 days away — suggest pushing work in progress.

## Pitfalls
- Date-only `--due` values mean 23:59 local time.
- The repo check uses the public GitHub API (60 requests/hour without a token).
- Never store secrets or private notes in the deadlines file.

## Verification
`list` shows the new item with the expected tier; `check` output matches the tiers.
