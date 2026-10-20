---
description: An owner's page spent a seven-minute synthesis turn on a page no round had changed. The turn is skipped now. In the runs after it, it seldom applied: the real waste was rounds that were thrown away.
tags: [REM, Performance]
---

# A round that changed nothing

A long page is read in rounds: one turn per part of the material, then a
synthesis turn that brings the rounds' additions together. In the release
check, the owner's full page ran four rounds. Two were refused for dropping
quotes, one answered NO CHANGE, and then a 415-second synthesis turn read an
unchanged page and changed nothing either.

That last turn has nothing to do when no earlier round changed the page, so it
is skipped now. We did not stop after the first round that adds nothing: parts
are read oldest first, and stopping early would skip the newest mail.

Then we measured it, and the measurement was humbling. In two new runs of the
owner's page and one of the university's, a round had changed something every
time, so the synthesis ran as before. Owner: 51 minutes before, 53 after, with
16 and 14 quotes. University: 52 minutes and 14 quotes, inside the 38 to 54
minutes and 13 to 29 quotes of the earlier runs.

The time goes somewhere else. In each owner run, two of the four rounds were
refused because the turn kept two of seven quotes, or none of five, and the
page was restored. Those turns cost ten to fifteen minutes each and left
nothing. That is where to look next.

The other change is plainer. Init builds the session cache on a background
thread while it maps. That thread is now joined when mapping ends, even when
mapping fails, so no init and no test leaves it running.
