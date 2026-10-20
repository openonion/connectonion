---
description: Every co rem page reopened 11,473 session files it had already decided not to read, and sixteen workers queued behind one interpreter to do it.
tags: [REM, Performance]
---

# Eleven thousand files we had already said no to

With sixteen workers, each page spent four to five minutes gathering its
sources before the model saw a word. With four workers it took under a minute.
Nothing was waiting on the network. We sampled every thread's stack every 50
milliseconds and looked at where the time went.

Most of it was Python doing the same work sixteen times. Every page read every
mapped project's notes in full, up to 400 documents a folder, looking for the
person's name. Every page parsed 1,209 saved mail headers and a 2 MB inventory.
Every model turn re-tidied 650 old task folders it had already tidied. All of
it is CPU work, and sixteen threads in one interpreter share one core for it.
With four workers the cost hid; with sixteen it was multiplied.

Each of those is now done once per run and kept until a file changes.

The bigger one was older. The session scan reads Codex and Claude Code
transcripts. It skips REM's own turns, because what REM asked a model is not
what the owner said. But "skip" meant "don't record anything", so the next scan
opened the file again to decide again. On this machine 11,473 of 15,000 Codex
rollouts were REM's own turns. A warm scan, with nothing new in it, took 80
seconds. Now a skipped file is recorded as skipped and never reopened: 6
seconds.

There was one trap, and a colleague working on deepening found it the same
day. A REM turn that is still running keeps growing. If its record is updated
every time it grows, the scan sees new progress on every pass and never
decides it is finished. One of their gathers looped for 27 minutes. A skipped
file's record is written once and left alone. Whether a session is read is
decided by its first line, and appending to the file never changes that.

Measured on a copy of the owner's notebook, with sixteen pages, the model turn
stubbed out, and old and new runs interleaved on a busy machine: a page's
gathering went from 339 seconds to 146–179, and the sixteen pages from 417–460
seconds to 215–252. At four workers it went from 79 to 51. The first scan
after upgrading still opens everything once, to record what it skips.
