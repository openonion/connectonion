---
description: co rem counted the same quota sixteen times when it wrote sixteen pages at once, and four workers wrote as fast as sixteen on a short queue.
tags: [REM, Performance]
---

# Sixteen readings of one meter

Every page co rem writes records the Codex weekly meter before it starts and
after it ends. The difference is what that page cost. That works for one page
at a time.

A first run writes sixteen pages at once. Each page's before and after covers
the other fifteen pages' spend too, and we added all sixteen differences up. On
the owner's notebook the meter moved about ten points over the first run. The
budget said 154. The weekly investigation budget is 35 points, so the
background round thought it had spent its week in an afternoon. On a 48-worker
run it was worse: the meter moved 3 and we counted 142.

The fix treats runs that overlap in time as one group. A group costs what the
meter moved from its first reading to its last. Replayed on the same records,
154 becomes 15.9 and 142 becomes 3. The gaps between groups stay out, because
that is the owner's own coding.

A run the meter cannot see, one that reads the same whole percent before and
after, is priced from its tokens. We had guessed a million fresh tokens a
point. Seven large runs measured twelve million at standard speed. Fast speed
bills twice.

Then we asked how many workers to run. Twelve people, the same notebook copied
fresh each time, at 4, 8, 12 and 16 workers. Nothing failed and nothing was
refused. The Codex logs showed no 429s at all. Pages came out the same length
with the same citations at every count.

The surprise was the clock. Four workers finished the twelve pages in 66
minutes, and sixteen took 65. One person needed six rounds of about nine
minutes each. However many workers we gave it, the run waited for that page.
A short queue measures its slowest page, not its workers.

What the workers change is the long queue. A model round took 430 seconds at
four workers and about 530 at eight to sixteen. Four times the workers for a
quarter more time per round works out at about 30 pages an hour at four and
about 62 at twelve or sixteen. At 48, in an earlier run, each round took 2.5
times as long and no more pages came out than at sixteen.

So the default stays at sixteen, and it is now one setting,
`limits.workers`, for both init and `co rem investigate CATEGORY`. There is no
backoff for rate limits. We looked for rate limits and found none.
