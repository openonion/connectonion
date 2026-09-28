---
title: "The weekly job was right on time"
date: 2026-09-28
---

# The weekly job was right on time

We were trying to finish a release recovery when the Python test matrix failed
on every version. The failed assertion said a scheduler tick should run
nothing after `sync` was paused. Instead it ran `/weekly`.

That looked like a pause bug until we read the whole fixture. Alongside the
hourly `sync` entry, it defines a weekly entry for Monday 09:00 UTC. The test
chose `datetime.now()` as its tick time. We happened to run CI on a Monday
after 09:00. The scheduler did exactly what the fixture asked it to do; the
test had silently assumed the other entry would never be due.

We reproduced the failure locally, then gave this one test a fixed Thursday
time. It still proves the intended behavior: the paused entry does not run,
and resuming it lets the next tick run it. The independent weekly entry is no
longer an accidental part of the assertion.

A deterministic test clock is not just protection from flaky CI. It makes the
scenario explicit. If a test is about one schedule entry, its other entries
must have a defined relationship to the chosen time.
