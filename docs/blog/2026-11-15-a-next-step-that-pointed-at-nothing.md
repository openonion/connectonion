# A next step that pointed at nothing

*2026-11-15*

Every `co` command ends with one `Next:` line, and an agent runs it without
reading anything else. That is the point of the line, and it is why a wrong
one costs more than a missing one.

We found a wrong one while checking a new source against a real account. We
ran `co rem sync --source` for that one source a second time, with nothing
new to read. It said "no change", which was right, and then:

```text
Full record      co rem logs run_3c96aaf8…
Next: co rem logs run_3c96aaf8…
```

Running that gave `Run not found`, with exit code 1. A person shrugs at that.
An agent that chains `sync` and then its `Next` stops on an error nothing had
gone wrong to cause.

The cause was a good change made earlier. A batch with nothing new runs no
model and changes no page, and its records used to fill `co rem logs` with
empty runs, so #1846 stopped keeping them. Plain `co rem sync` was fine: it
runs the whole daily round, which keeps a record of its own. But
`--source` and `--with` run a single batch, and that batch still hands back a record
with an id, though, and the command line built both its "Full record" row and
its `Next:` from that id without asking whether the run had been kept.
Nothing had told the reader of the record that the writer had stopped writing
it.

The fix asks the one question that matters: is `runs/<id>.json` there? If it
is not, the result says `record_kept: false`, the summary leaves out the
"Full record" row, and `Next:` becomes `co rem status`, which works on every
notebook. A run that was kept still points at its own log, as before.

By the time this reached review, `sync` and `collect` had been folded into one
path, so the fix landed there once. `collect` keeps its own next step (collect
again); it only stops printing the "Full record" row for a run that was never
written. Plain `co rem sync`, the daily round, turned out to have the same row:
its `Next:` is the list of runs, which always opens, but its summary named the
batch's own id when the round kept no run. It now asks the same question.

The test is written the way the fault showed up: a single-batch sync, a
collect and a daily round, each with and without a kept record, through the
real `co rem` command line. The
not-kept case fails on `main` and passes here; the kept case passes on both.
On a scratch notebook with nothing to read, the real `co rem sync` now ends
with `Next: co rem status`, and `co rem status` runs.

The lesson is small and easy to forget: when you stop writing a record, every
place that points at it has to learn that too.
