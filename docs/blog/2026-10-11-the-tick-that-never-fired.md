---
description: co rem's background job was installed, loaded and healthy by every check, and macOS never started it once. Two macOS versions each ignore a different launchd trigger, so the job now carries both.
tags: [REM, Scheduling]
---

# The tick that never fired

co rem keeps a notebook up to date in the background. Nothing clever does the
waking: one launchd job runs `co rem sync --scheduled` every five minutes, and
`sync` decides whether one of your saved times has come due. A tick with
nothing to do exits at once.

In September we chose that trigger by measuring. On macOS 26, a job using
`StartCalendarInterval` never fired in three experiments, while
`StartInterval` fired to the second every time. So the job ticks on an
interval, and the reason is written at the top of the file.

This week the notebook on a MacBook running macOS 14.1 had not been maintained
for a day. The job was installed, `launchctl` listed it, and the plist was
correct. `launchctl print` said `runs = 0`. Since 1.9.2b4, `co rem status` says
so as well: "macOS has not started it once".

We ran the same experiment again on this machine. A throwaway job that appends
the date to a file every 60 seconds ran zero times in four minutes, with or
without `ProcessType = Background`. A `launchctl kickstart` ran it at once, so
launchd could start it; the timer simply never went off. A second throwaway
job with a calendar entry for every minute ran at 07:51:05, 07:52:04 and
07:53:03. Every other interval job on that Mac told the same story: a
five-minute job had run 26 times in eight days.

So each trigger has been measured dead on one version of macOS, and alive on
the other. We could not find a rule that says which. The job now carries both:
the interval, and a calendar entry on every fifth minute. A test job with both
keys still ran once a minute, not twice, and a duplicate tick would cost
nothing anyway, since a tick that finds nothing due exits.

The reinstalled job on that MacBook ran at 07:55 and again at 08:00, its first
runs since it was installed.

The lesson is about where the September measurement was true. It was a
correct reading of one machine, written down as a fact about launchd. A
trigger is a promise the operating system makes, and two versions made
different ones.
