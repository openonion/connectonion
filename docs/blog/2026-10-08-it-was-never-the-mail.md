---
description: Profiling co rem's slow first run found the time was spent re-reading coding sessions, not mail. 1.9.1b4 reads them once.
tags: [REM, Performance]
---

# It was never the mail

Three betas today chased a slow first run by fixing mail. More workers. A pool
per mailbox. Six months from disk, two years in the background. Attachments
out of the way. Each helped a little, and people pages still sat at
"gathering sources".

Then we profiled one person instead of guessing. 363 seconds; the mail took
about ten. The other 350 went to reading every local coding-session transcript
again and hashing it, to make sure no earlier conversation had been rewritten.
A sensible check, done once per person, one person at a time behind a lock,
with sixteen workers waiting their turn.

1.9.1b4 does the check once per run and shares the answer. The lesson is the
older one: measure where the time goes before deciding where it goes.
