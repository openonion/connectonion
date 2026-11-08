# REM morning message — sprint 11

Worktree: `/private/tmp/rem-sprint11/morning-message`; branch
`sprint11/morning-message`, based on `938f153c8`. No push or real message send.
Every shell invocation used a fresh `HOME=$(mktemp -d)`. Tests additionally
isolate HOME per test; transports were replaced through existing sender seams.
No real `~/.co` or SSH material was accessed.

## Commits and changed files

- `c3dba6296` — Add one quiet morning message from REM's overnight receipts.
- `b5b7418a5` — Preserve pending tasks when notification settings change.
- `HEAD` (this report-only commit) — Record REM morning-message validation results.

| File | Purpose |
| --- | --- |
| `connectonion/rem/morning.py` | Deterministic zh/en projection, receipt counts, explicit destination, existing sender paths, date claim and doctor checks. |
| `connectonion/rem/config.py` | Default `notify.channel: none`, explicit `notify.target`, validation and backward-compatible defaults. |
| `connectonion/rem/native.py` | Scheduled next checks the morning without a model; notification settings do not invalidate prepared tasks. |
| `connectonion/rem/daily.py` | Existing scheduled daily rounds also perform the morning check. |
| `connectonion/cli/commands/rem_commands.py` | Register morning and doctor checks; exact dry-run output. |
| `connectonion/cli/commands/rem_help.md` | Model-first skill text, options, setup, next step and personal-content email guidance. |
| `connectonion/cli/commands/rem_help.py` | Read-only sender configuration discovery in morning help. |
| `tests/unit/test_rem_morning.py` | Fictional receipts, sender fakes, date claims, quiet mornings, late checks and round safety. |
| `docs/cli/rem.md` | Command and notification configuration usage. |
| `docs/rem-night-outcomes.md` | Marker statuses, source fields, investigation compatibility contract and overnight window. |
| `docs/testing/rem-morning-message-results.md` | This evidence report. |

## Red-first evidence

Initial new tests, before implementation: `2 failed, 6 errors in 8.88s`.
Errors were the absent `connectonion.rem.morning` module; the configuration test
failed with `KeyError: 'notify'`. The empty morning behavior also did not exist.

The first implementation exposed an omitted command-order entry:
`ValueError: 'morning' is not in list`; fixed the registration list.
Fake chat senders initially returned Mock objects, which existing inbox receipt
serialization correctly rejected; fixtures now return fictional string receipts.

Independent-review regressions were also red before their fixes:
`2 failed in 13.95s`: a sent draft counted `0` instead of `1` prepared draft;
a 10:00 investigation counted `1` instead of `0` overnight explanations.
Existing draft receipts now preserve the first count; the window ends at 06:00.

Focused command, configuration and help checks: `42 passed in 4.58s`.
Independent reviewer rerun: `20 passed in 3.14s`.

## Fictional dry-run previews

Captured with CliRunner calling the real `morning --dry-run` command, using the
fictional unit fixture: Mara Quill, Fernhill, one deduplicated prepared draft,
one REM-held reply sent, one completed task, and one explained investigation.
Clock, Today-link availability and current actionable titles use fixture seams;
no sender is invoked. The channel label is outside the three-line sent message.

Chinese:

```text
Channel: telegram
昨夜：备好 1 封草稿，已发 1 封回复，派出 1 项任务、完成 1 项，讲清 1 项调查。
2 件等你点一下：Mara Quill、Fernhill
打开 Today：co rem open
```

English:

```text
Channel: telegram
Overnight: 1 draft prepared, 1 reply sent, 1 task dispatched, 1 finished, 1 investigation explained.
2 need one click: Mara Quill, Fernhill
Open Today: co rem open
```

## Independent experience review

A separate AI reviewer used a marketing/UI technology-founder perspective,
inspecting morning help and fictional zh/en dry-run states. This was a CLI-only
review; no rendered browser pages or desktop/mobile reader states were reviewed,
and it is not a human founder review or an all-page pass.

Significant findings and rechecks:

- Sent drafts disappeared from the current night projection, understating work.
  Recheck: retained sent draft receipt still counts once; regression passed.
- A late invocation included daytime work as overnight work. Recheck: 10:00
  explanation excluded from a 16:00 check; regression passed.
- Notification preparation/lock errors could interrupt rounds. Recheck: malformed
  investigation date is recorded as failed; a busy notification still reaches
  the round; regressions passed.
- Configured sender instructions omitted the destination. Recheck: next command
  now sets the owner's target before enabling the selected channel.

Second review round: singular wording is fixed and doctor flags an enabled
channel whose sender or destination is missing. Both new tests were first red
(`2 failed, 20 deselected in 16.89s`), then passed. The reviewer found no new
safety issues; final focused morning recheck: `22 passed in 3.43s`.

## CLI audit

Ran `co audit co rem morning` with fresh HOME and this worktree’s `.venv/bin`
first on PATH. No `--review` model call was requested. Verbatim result:

```text
co rem morning: 1 pages
  prints           1/1
  hangs            1/1
  writes           1/1
  usage            1/1
  example          1/1
  self_example     1/1
  flags            1/1
  private          1/1
  params           1/1
  look             1/1
✓ fit for an agent harness
Next: co audit co rem morning --review
```

## Full unit suite

Started from `/private/tmp` with a fresh HOME. `--directory` explicitly selects
this worktree so the requested relative `tests/unit` suite resolves correctly:

```sh
export HOME=$(mktemp -d)
export OPENONION_API_KEY=fictional-rem-unit-key
trap - HUP
cd /private/tmp
env -u FORCE_COLOR uv run --directory /private/tmp/rem-sprint11/morning-message --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 6 --dist=worksteal
```


First full run, before the compatibility fix and explicit offline test setup:

```text
31 failed, 18781 passed, 19 skipped, 2884 warnings in 414.74s (0:06:54)
```

Twelve failures were notification-config compatibility regressions in existing
`test_rem_next_submit.py` legacy digest cases. Fixed by recognizing old hashes
with and without notify while preserving semantic input equality; targeted
recheck: `15 passed, 251 deselected, 60 warnings in 27.27s`.

Eighteen unrelated existing Agent-constructor tests required an ambient API key
that the isolated HOME intentionally lacks. Explicitly exporting a fictional
unit key exercises their existing offline seams; no real credential is read and
network isolation remains enabled. Their focused recheck passed; the only
remaining failure there was SIGHUP. Inspection showed the tool shell inherited
`SIGHUP=SIG_IGN` (1). `trap - HUP` restores the normal default (0), allowing the
existing process-stop test to exercise actual stop behavior. Neither tests nor
unrelated host product code was changed or disabled for these environment cases.
The final full run uses those two explicit environment corrections above.

Second-round existing native-task and host-stop regression suite (with explicit
offline environment setup):

```text
303 passed, 1498 warnings in 177.85s (0:02:57)
```

Final full-suite summary, verbatim (final implementation `b5b7418a5`):

```text
18814 passed, 19 skipped, 2944 warnings in 361.89s (0:06:01)
```

The second CLI audit again passed every check; its output matches the audit
block above. Both implementation commits and this results commit are local;
nothing was pushed.
