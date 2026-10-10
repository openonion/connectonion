---
description: co rem 1.9.2b7: fourteen investigations failed in the same two minutes, and the cause was a command in another terminal that had nothing to do with them.
tags: [REM, Reliability]
---

# Fourteen failures in two minutes

A real first run of co rem wrote all 312 pages. It also recorded fourteen
failures, every one of them between 03:15:46 and 03:17:33 in the morning, all
saying the same thing: "The selected credential record changed during this
operation."

Nobody had changed an account. The retries all succeeded, so the run looked
healthy, and the log would have scrolled past if we had not been reading every
record. Fourteen threads failing together, inside two minutes, meant something
had happened to all of them at once.

What happened was a separate `co` command in another terminal. It read the same
Outlook sign-in, found its token expiring, and refreshed it. Microsoft hands
back a new refresh token every time you refresh, so the record on disk now held
a token none of the sixteen investigation threads had seen. Each of them, on its
next mail search, compared the record it remembered with the one on disk, could
not find an email address to prove it was still the same account, and refused
to go on.

The check was right to exist: a token for a different account written over the
record must stop a run. And the code already knew how to tell a rotation from a
replacement. It remembered every refresh it made, old token to new. But it
remembered them in memory, in one process. A refresh made anywhere else looked
exactly like a stranger.

Now each rotation is also written beside the env file, as a pair of digests,
never the tokens themselves. Any `co` process can follow the chain from the
token it holds to the one on disk. A different account still has no chain, and
is still refused.

A check that knows only what one process saw will someday be run by two.
