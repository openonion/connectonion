# Two syncs, one notebook

*2026-11-04 · Names below are fictional.*

Mara's 18:00 notebook update was still doing page work at 18:57. When the
19:00 Codex slot fired, its update found a moment between the first run's
model turns, took the maintenance lock and started too.

Each page write held the lock. The two scheduled rounds could still overlap.
The newer round decided that Robin and Robin Hale were the same person,
merged their pages and archived one. The older round reached its own
same-person stage with that page still in its candidate pair. It stopped with
`Record not found`. The archive and alias survived, along with three pages
already written by the older round. These observations were recorded in
[issue #2754](https://github.com/openonion/connectonion/issues/2754#issuecomment-6627653819)
on 1.9.3rc37; this repair starts from 1.9.3rc39.

Scheduled admission now checks running records under the maintenance lock.
A live PID on this host means busy. The command says when that sync started
and leaves the new slot owed. Dead processes are abandoned before that check.
A small ownership record in `worker.json` spans the whole round, including
the spaces between stages and the CLI's depth work. It adds no model calls or
visible batches. The slot is served when the round returns an outcome.

The same-person stage also checks both original paths and the alias table
under the lock before reading the pair and before preparing a merge. If
either page has gone or already become an alias, it logs a skip and continues.
A model answer that arrived after the archive still has its usage counted.
A pair skipped before the model call spends no attempt.

We reproduced the boundary with temporary notebooks and fictional pages,
replacing `runner.run_task` rather than the merge code. The initial regression
set produced eight failures and three passes against the original code: live
PIDs admitted another run, and stale pairs lacked the required skip behavior.
The three dead-PID cases already passed. After the fix, that set passes.
Additional checks cover an owed slot retried after a stage gap and two ticks
reaching admission together. CLI inspection verifies a one-line busy response
and a single JSON result. These are local regression measurements; they do
not claim a live scheduled notebook trial or a deployed release.
