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

## Review fixes

Review: `review-morning-message.md` (findings 1–9 plus the PM rewrite of the
text). Fix commit `1badf1415`; this section is the next commit. Every command
ran with a fresh `HOME=$(mktemp -d)`; no real message was sent and the default
channel stays `none`. Red first: the rewritten `tests/unit/test_rem_morning.py`
run against `7432607c7` gave `20 failed, 14 passed in 3.28s`; after the fix,
`34 passed`.

- 1 (blocking) Investigations: read `.state/investigations/index.json` as
  `rem/problems.py` writes it at night-investigations `35b0a770b` — one object
  keyed by problem key, full receipt per value, `state` + `updated_at` bumped by
  every `save()`, no `items`, no `explained_at`. Count `state` in `explained`,
  `needs_owner`, `fix_proposed` with `updated_at` in the window. The fixture
  `investigations()` builds receipts field-for-field like `reserve()` + `save()`.
  Contract recorded in `docs/rem-night-outcomes.md`. Fixed.
- 2 (blocking) Due only 06:00–11:00 local; after 11:00 the date is recorded
  `missed` and nothing is sent (tested at 17:00 and 21:00). Fixed.
- 3 Window is the previous non-missed note's `checked_at` (else 22:00 the
  evening before) through now, start exclusive, end inclusive; tested with work
  at 07:00 yesterday and 07:30 today, and across a missed day. Fixed.
- 4 The broad `except` is gone: a preview error claims nothing,
  `scheduled_check` reports it (`unavailable`), and the next tick sends. Fixed.
- 5 Titles/phrases with `@`, paths, `.md` records or long hex IDs are dropped;
  `Re: Fernhill pilot` now survives; each line is built from the row's own kind
  and words (`gist`, else `subject`). New test goes through the real
  `approvals.outcomes` (only `today.queue` and `drafts.listing` faked): a draft
  whose title fell back to `ops@fernhill.example` reads "Reply as you (Re:
  Fernhill pilot) — send my draft?". Fixed.
- 6 Zero counts and the empty decision block are left out. Fixed.
- 7 Dry-run's first line says what a real run would do: `would send now via
  telegram`, `already sent 06:02`, `not due until 06:00`, `outside the morning
  window (06:00–11:00): nothing will be sent today`, `channel none: nothing will
  be sent`, `quiet: nothing to send`. Fixed.
- 8 `today_link()` (and so `host_online`) runs before `maintenance_lock`; a
  test fails if it is called while the lock is held. Fixed.
- 9 Doctor reports only the latest entry, and only if `failed`/`sending`;
  `morning.json` is pruned to 14 days on every write; the help page no longer
  embeds this machine's sender status (doctor already lists it); a morning with
  nothing new and the same pending outcome IDs as the previous note is `quiet`.
  Fixed.
- PM rewrite: line 1 non-zero counts only ("sent for you" vs "drafted, waiting",
  never both for one draft; tasks finished; problems explained); up to two
  one-clause decisions, "还有 N 件在 Today" beyond that; last line opens Today.
  The zh/en full-night output below is byte-identical to the PM's targets.
  `handled` rows (no PM template) read "<who>——不用再回了，标为已处理？" /
  "<who> — no reply needed; mark it done?".
- Test cwd: the teardown errors from a `/private/tmp` or mktemp cwd were the
  suite-wide stray-project guard (`project_root()` falls back to the cwd), not
  morning-specific — `test_rem_config.py` errors the same way from there. The
  morning tests now `chdir` into their own tmp dir and pass from any cwd.

### Dry-run, fictional notebook

Real `co rem morning --dry-run` through CliRunner; Mara Quill and Fernhill;
clock, decision rows and Today link pinned; script at
`/private/tmp/claude-501/-Users-changxing-projects/269dbb10-e59d-4c67-b07d-a6631da6d076/scratchpad/sprint11/morning-fix/dryrun.py`. "Full" has one REM-sent reply,
one more draft waiting, one finished task, one explained problem and two
decisions; "quiet" is an empty notebook; "outside" is the full notebook at 17:00.

```text
--- zh: full night, 06:00
would send now via telegram
昨夜：替你发出 1 封回复，另拟好 1 封待你看；跑完 1 项任务，查清 1 个问题。
2 件要你拍板：
· 以你的名义回 Mara Quill（Fernhill 试点何时开始）——用我拟的稿？
· Fernhill 计划——花一次 Codex 运行去做，还是先放着？
打开 Today：co rem open
--- zh: quiet night, 06:00
quiet: nothing to send
--- zh: outside the window, 17:00
outside the morning window (06:00–11:00): nothing will be sent today
昨夜：替你发出 1 封回复，另拟好 1 封待你看；跑完 1 项任务，查清 1 个问题。
2 件要你拍板：
· 以你的名义回 Mara Quill（Fernhill 试点何时开始）——用我拟的稿？
· Fernhill 计划——花一次 Codex 运行去做，还是先放着？
打开 Today：co rem open
--- en: full night, 06:00
would send now via telegram
Overnight: 1 reply sent for you, 1 more drafted for you to check; 1 task finished, 1 problem explained.
2 decisions:
· Reply to Mara Quill as you (when the Fernhill pilot starts) — send my draft?
· Fernhill plan — spend one Codex run on it, or leave it?
Open Today: co rem open
--- en: quiet night, 06:00
quiet: nothing to send
--- en: outside the window, 17:00
outside the morning window (06:00–11:00): nothing will be sent today
Overnight: 1 reply sent for you, 1 more drafted for you to check; 1 task finished, 1 problem explained.
2 decisions:
· Reply to Mara Quill as you (when the Fernhill pilot starts) — send my draft?
· Fernhill plan — spend one Codex run on it, or leave it?
Open Today: co rem open
```

Outside the window the would-be message is still printed as a preview; the
first line is what decides, and a real run records `missed` and sends nothing.

### CLI audit

`co audit co rem morning` after the help change, fresh HOME, this worktree's
`.venv/bin` first on PATH, no `--review`. Verbatim:

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

### Unit suite

From `/private/tmp`, fresh HOME, `trap - HUP` (the tool shell ignores SIGHUP):

```sh
cd /private/tmp
env -u FORCE_COLOR uv run --directory /private/tmp/rem-sprint11/morning-message --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 6 --dist=worksteal
```

With no provider key in the environment (fix head `1badf1415`):

```text
18 failed, 18817 passed, 19 skipped, 2944 warnings in 303.59s (0:05:03)
```

All 18 are `MissingAmbientAPIKey` (17 directly, one through an `Agent(...)`
subprocess) in eight host/agent files; none is a REM or morning test. The same
18 node IDs, run on `origin/sprint11/proactive` (`938f153c8`) with no key:
`18 failed in 7.53s`, the identical set.

With `OPENONION_API_KEY=fictional-rem-unit-key` (offline seams only; network
isolation stays on; no real credential read), verbatim:

```text
18835 passed, 19 skipped, 2944 warnings in 442.16s (0:07:22)
```

Nothing was pushed and no real message was sent.
