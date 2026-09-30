# The cap that said nothing

The 1.9.0a1 acceptance run used a copy of the owner's real notebook, and
`co rem sync` refused to run. It printed "Daily runner-attempt limit reached"
and a `Next:` line pointing at the logs. The logs were empty. `sync --dry-run`,
the command you run to find out what a sync would do, did not mention the cap
at all, even though `status` showed 30 of 30. The refusal was right. The
problem was that the notebook said so in only one place.

The backfill had the opposite problem. `sync --all` skipped the cap on
purpose. The reasoning was that the cap guards against runaway background
runs, and a backfill is something the owner types. On the real notebook it
made 60 attempts against a cap of 30. It ran five batches over 37 minutes
with no output. When the owner pressed Ctrl-C, it exited 130 without saying
what had finished. Typing a command yourself is not the same as watching it
run.

The fix makes the cap visible wherever you might look:

- `sync --dry-run` reports how many runner attempts are left today and when
  the count resets. That is midnight in the notebook's own timezone, the same
  day `status` counts in.
- A refused run now writes a run record with outcome `refused` and its reason,
  so the logs it points to have something in them. The message gives the reset
  time and names `limits.runner_calls_per_day`, and its `Next:` is
  `co rem config`, where that setting lives.
- `sync --all` stays under the daily cap, like every other run, and prints one
  line per batch to stderr. Raising the config value is the only way to go
  past the cap. We did not add a flag for it.
- Ctrl-C during a backfill reports how many batches finished and says the
  interrupted batch will be read again next time.

One part of the report is still open. Investigations record
`runner_attempts: 0`, so their tokens do not count toward the cap. That is a
separate decision about what the daily cap is meant to limit, and this change
does not make it.
