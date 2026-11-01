---
description: REM's native timer was saved, but Codex was closed. A small launchd job now opens the desktop at each saved time while Codex remains the only executor.
tags: [REM, Scheduling]
---

# The clock needed the app

The schedule said 17:00. Two days later, its next run still said 17:00 on
October 30. The task existed, its command was correct, and nothing had run.
Codex desktop had been closed since that afternoon.

An earlier observation supplied the missing piece: opening Codex at 14:48
had caused it to run a missed 06:00 slot. The native timer needed its desktop
process. Saving an automation could not keep that process available.

There was a second trap in the diagnosis. REM checked `codex-dev.db`, whose
index had stopped updating on October 28. The desktop was updating
`codex.db`. A status check could therefore read yesterday's registration
while appearing to confirm today's installation. REM now reads the desktop
index first, read-only, and falls back to the development index only when
the desktop database has no automations table. An empty current table stays
empty; a stale row cannot bring a removed task back.

The repair adds a small launchd job alongside the native task. At each saved
schedule time it asks macOS to open Codex in the background, without taking
focus. It never starts REM. Codex still owns execution, and the automation
still runs the same fixed `co rem ... sync --scheduled` command. Stopping
the native schedule also unloads and removes its wake job.

Running REM directly from a second timer would have bypassed the missing
app, but it would also have created another executor to coordinate. Opening
the app fixes the prerequisite that was actually missing. The computer must
still be awake for launchd to open the application.

Status now names the missed slot once the indexed next run is more than
30 minutes late, and says whether the wake job is loaded. The regression
tests reproduced the stale index and absent wake job before the fix. Their
replacement databases and launchctl fakes verify selection, registration,
stop, schedule changes and the 30-minute boundary without changing a real
Codex task. A live macOS firing remains a separate check.
