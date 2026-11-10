# Hermes skill tap — deadline-radar

Public Hermes skill tap for the CSCI 599 Assignment 3 custom skill.

```
skills/
└── deadline-radar/
    ├── SKILL.md
    └── scripts/deadline_radar.py
```

## Install on a fresh Hermes

```bash
hermes skills tap add rajarajeswari-thippesh/hermes-deadline-radar
hermes skills search deadline
hermes skills install rajarajeswari-thippesh/hermes-deadline-radar/deadline-radar
hermes chat --toolsets skills,terminal -q "Use the deadline-radar skill to run its demo and summarize the alerts"
```

Pinned version: `version: 1.0.0` in `SKILL.md`, git tag `v1.0.0` (commit hash recorded in the
assignment README).

## Test it without Hermes

```bash
python3 skills/deadline-radar/scripts/deadline_radar.py demo
```

License: MIT. No credentials, personal data, or machine-specific paths are included.
