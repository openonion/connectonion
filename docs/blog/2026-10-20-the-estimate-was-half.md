---
description: The release check said 42 minutes and took 82. One dropped connection threw away 33 minutes of mapping. And three tries at making one university's page faster mostly measured the noise.
tags: [REM, Performance]
---

# The estimate was half

Before a release we ran a first init the way a new user would: a fresh
notebook from the owner's real mail and sessions, sixteen pages at a time.

The first attempt never reached a page. Thirty-three minutes into mapping,
Gmail dropped one connection with an SSL error, and init stopped and asked for
attention. Mapping lists a mailbox one week at a time, so a dropped week is now
asked again after two, four and eight seconds. A connection that stays down
still fails, and so does a sign-in error, on the first try.

The second attempt wrote all seventeen pages. It had announced about 42 minutes
and 50 million input tokens. It took 82 minutes and 102 million. The planning
rates were medians from a full run of 84 people. A run capped at ten people
takes the ten most active, and those are far heavier: 35 minutes and 6.3
million tokens each, not 11 minutes and 2.9 million. The estimate now prices
each kind's first pages at the release check's rates and the rest at the
full-run medians. For the release check it says 95 minutes and 100 million.

The last page to finish was a university's: 82 minutes, mostly five model turns
of ten to twenty minutes each. We tried to shorten it on copies of the same
notebook. Reading one part instead of three took 14 minutes but kept one
quote out of 29. Two parts, or a 180-day window instead of two years, took
37 and 45 minutes with 17 and 21 quotes. Then the unchanged page ran a second
time: 38 minutes and 13 quotes, against 54 minutes and 29 the first time. The
difference between two runs of the same page was bigger than anything the caps
changed. So we did not ship a cap. The estimate now expects that page to be
slow.

One more first-run cost was easy to move. A fresh notebook built its session
cache inside the owner's quick page, 336 seconds of it. Init now builds the
cache in the background while it maps, and mapping mostly waits on mail servers.
