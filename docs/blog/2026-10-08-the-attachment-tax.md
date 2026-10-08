---
description: co rem 1.9.1b3 stops paying one network round trip per archived email before the first page is written.
tags: [REM, Performance]
---

# The attachment tax

1.9.1b2 moved the first pass onto mail already on disk, and the first run got
slower. Fourteen of sixteen workers were still waiting on the network.

The mail bodies were local. The attachments were not, and the first pass asked
the provider, for every archived message, whether it had any. In a fresh
notebook that is one round trip per email, about one a second across the whole
run, for four and a half thousand emails.

So the first pass now reads only what is on disk. The background worker that
already fetches each person's older mail asks about attachments too, keeps
them, and the deepening pass reads them. The network work still happens; it
just no longer stands between you and your first page.
