# REM night clears the list — validation

Branch: `sprint8/night-clears-list`. HEAD and `origin/release/1.9.3rc60` both
started at `391186fbc9eef3355d6f66bbcb4fc50f78106d0f`; no commits were made.

## Red → green

- R1: all 12 initial regressions failed before implementation: 17-item nightly coverage, missing incoming/owner bodies, consent/fetch failure cards, owner verdict/task prompts, privacy and cap/status reporting. G1 passed all 12.
- R2/R3: independent AI review found hashed missing originals, unresolved secondary citations, noncompletion/clarification misclassified as handled, and clipped/misattributed task promises. All 8 new cases failed before fixes. G2 passed the resulting 20 cases.
- R4: a missing OAuth scope raised ValueError and aborted the round. The new regression failed before fixing the client-construction boundary; it now records a safe mailbox-configuration failure.
- R5: two sent-promise/clarification cases failed before the sent-body fix; the completed-response control passed. G3 passed all 30 targeted cases, including 7 further controls/integration checks (native fetch→submit/no-reply, writer-failure continuation, daily caps and unindexed Outlook headers).
- S1 identified an old test assuming the default was 10. It now explicitly configures a 10-draft cap, retaining its original cross-round enforcement assertion. S2 found a new test fixture whose filename lacked the `run_` prefix, so it was not a run log; the fixture is corrected. Neither test was disabled.

## Exact test commands and last lines

Every command below starts with this exact prefix:

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider
```

`REQUESTED` means these exact remaining arguments:

```sh
tests/unit/test_rem_today.py tests/unit/test_rem_proactive.py tests/unit/test_rem_daily*.py tests/unit/test_rem_next_submit.py tests/unit/test_rem_native*.py -n 6
```

The commands redirected stdout/stderr into `/tmp/rem-night-*.log`. The last
lines below are copied verbatim, including warnings and elapsed times.

| Run | Remaining command arguments | Exact last line |
| --- | --- | --- |
| R1 | `tests/unit/test_rem_proactive.py -k 'test_night_' -n 6` | `12 failed in 10.18s` |
| G1 | `tests/unit/test_rem_proactive.py -k 'test_night_' -n 6` | `12 passed in 13.05s` |
| S1 | `REQUESTED` | `1 failed, 513 passed, 1477 warnings in 78.30s (0:01:18)` |
| R2 | `tests/unit/test_rem_proactive.py -k 'test_night_hash or test_night_does_not' -n 6` | `6 failed in 17.80s` |
| R3 | `tests/unit/test_rem_proactive.py -k 'test_night_recovers or test_night_task_prompt' -n 6` | `2 failed in 6.62s` |
| G2 | `tests/unit/test_rem_proactive.py -k 'test_night_' -n 6` | `20 passed in 13.17s` |
| R4 | `tests/unit/test_rem_proactive.py -k 'test_night_missing_mail_scope' -n 6` | `1 failed in 6.42s` |
| S2 | `REQUESTED` | `1 failed, 527 passed, 1477 warnings in 77.01s (0:01:17)` |
| R5 | `tests/unit/test_rem_proactive.py -k 'test_night_sent_reply' -n 6` | `2 failed, 1 passed in 16.11s` |
| G3 | `tests/unit/test_rem_proactive.py -k 'test_night_' -n 6` | `30 passed in 13.57s` |

| S3 | `REQUESTED` | `532 passed, 1477 warnings in 93.49s (0:01:33)` |
| A1 | `tests/unit/test_rem_reader_model.py tests/unit/test_rem_reader_lazy.py tests/unit/test_rem_reader.py tests/unit/test_rem_store.py tests/unit/test_rem_mail_archive.py -n 6` | `396 passed in 40.29s` |

The requested suite passed all 532 tests; the adjacent reader/store/archive suite passed all 396.
The 1,477 warnings come from existing positional `maxsplit` uses in `page_review.py`, unchanged by this work.
`git diff --check` passed; HEAD still matches the base commit and reader.html has no diff.

## Changes by requirement

1. Coverage: `config.py:82` raises the default to 30; `night.py:145`, `daily.py:237` and `native_round.py:146` share Today ordering, deduplicated drafts and explicit cap outcomes. `native.py:223` records global budget stops.
2. Fetch: `night_mail.py:36` checks subscription consent before opening a client, retains originals and reports expected provider failures. `reader_model.py:158` resolves metadata-only hashed citations; `today.py:84` requires unresolved citations and missing owner bodies to be recovered before classification.
3. Outcomes: `night.py:31`, `night.py:81` and `night.py:92` distinguish sent promises, task prompts, quoted handled verdicts, prepared replies and no-reply decisions. `today.py:118` guards explicit noncompletion and clarification. `daily.py:254` records rejected model candidates and continues.
4. Status/snapshot: `rem_status.py:58` prints counts and every unprepared item; `reader.py:257` exposes local-only outcome rows and card attachments. `night.py:43` checks current evidence before projection.

## Independent review

An independent AI reviewer inspected code and the morning UI data contract with
an engineering/UI-founder perspective. It identified the four R2/R3 issues and
the sent-draft R5 issue; each was fixed and rechecked. Final review reported no
remaining material issue. This was not a human founder review or rendered-page
review. Natural-language verdicts remain heuristic and require owner confirmation.

## Limits and untouched surfaces

- No live mailbox reads, real model turns, scheduled overnight run, or writes to the owner's `~/.co` were performed. Mail/network boundaries were mocked; notebooks and archives were temporary fixtures.
- `reader.html` is unchanged. Morning approval UI and its batch action belong to the other engineer; no rendered desktop/mobile UI review was performed.
- No obligation-task dispatcher exists on this base. Task outcomes are ready prompts, not completed work or dispatched tasks.
- Explicit pre-existing draft caps are respected; changing the default does not rewrite the owner's saved configuration.
- Wiki/docs-site were not published. Main docs and CLI help are updated; carry the new contract into those independently managed documentation repositories when integrating the feature.
- The local `IMPLEMENTATION_PLAN.md` is ignored by this repository; it records this work locally. No commits, staging or version changes.

Snapshot contract: [night outcomes](../rem-night-outcomes.md).
