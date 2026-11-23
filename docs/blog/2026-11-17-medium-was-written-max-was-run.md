# Medium was written, max was run

*2026-11-17*

The notebook's config file said `effort: medium`. We had read that line many
times. Over three real nights of `co rem catchup`, every one of 81 worker
turns ran at `max`.

Nothing was broken in the usual sense. The runner that starts a night's Codex
workers never passed an effort at all, so each worker took whatever the
owner's global Codex config said, and his said `max` because that is what he
wants when he codes. Three other places in the same package did pass it. The
setting existed, had a default, was documented, and reached the one path that
does almost all the work as nothing.

We found it by asking a different question. After each real night we now have
an agent read the trajectories: what each worker was shown, what it ran, how
long it sat. The first audits were about waste inside a turn, and they paid:
re-reads of the material went to zero, permission errors went from 17 to 0.
The fifth audit was asked where a Codex week had gone, 44% to 90% in six and
a half hours. It lined up the meter readings against the rollouts and
reported that the points formula was off by ten to ninety times, and, in one
line, the effort every turn context carried.

One complete night had cost about 28 points of a week. At that price the
feature runs three times and stops. We do not yet know what a night costs at
`medium`: the week was at its floor when the fix landed, so that number is
the first thing the next run measures.

The same audits found the night undoing itself. `co rem catchup` did not take
the lock the scheduled turn takes, so at 01:00 the scheduled turn handed out
the task a catchup worker was halfway through, discarded it, and the worker's
files vanished under it. A worker's timeout ended the whole night instead of
parking one page. A repair asked the worker to put back sources it had
dropped; it put back the list entries without the sentences that cited them,
and the runner removed them again as uncited, three times.

A setting is not in effect because it is written down. It is in effect when
the process that does the work was started with it, and the only way we know
to check that is to read what the process was actually given.
