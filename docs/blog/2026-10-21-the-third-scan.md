---
description: A fresh map read every coding session three times. The slowest of the three opened 2,561 sessions it could never use, and asked the disk about .git 517,000 times.
tags: [REM, Performance]
---

# The third scan

A fresh init reads the owner's coding sessions three times. The session import
writes a page for each conversation. The session cache keeps the owner's typed
messages for investigations. And the project filing step puts each typed
message under the project it was about. That one ran for thirteen to eighteen
minutes of a 40-to-50-minute map, and we had blamed it on something else.

Profiled on its own, it spent its time in two places. It read 2,561 exec and
subagent sessions in full. Their user slot is a program's prompt, so not one of
their lines could ever be the owner's words. And for every path a session's
tool calls named, it walked up the folders asking each one for a .git. 37,742
paths share a few hundred folders, and that came to 517,000 stat calls.

Now an exec or subagent session is set aside after its first line, as the other
two readers already did. Each folder is asked about .git once. On the same copy,
with the same 6,241 messages filed under the same 40 projects: 617 seconds
before, 256 after, and 227,000 stat calls instead of 517,000.

The three readers still each read the files. Merging them is the larger job:
they keep different windows and skip different sessions, for reasons that are
each right for their own page.
