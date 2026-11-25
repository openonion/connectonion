# REM scheduled turns: bounded waiting and visible failures

Scheduled `co rem next --scheduled` now waits at most 600 seconds for the
maintenance lock, shared across the thread queue and file-lock polling. At the
ceiling it exits with `MAINTENANCE_BUSY`, the recorded holder PID and its command
from `ps`. Manual `next` keeps its existing contention behavior. The REM skill
and automation prompt use the same two sentences, independently reviewed from
an AI engineer perspective: wait on the original command, then report the busy
message verbatim and end the turn without retrying. Other prompt rules remain.

`codex_exec` passes `CO_REM_TURN_ID` to its child environment; maintenance owners
record it for `next` and `submit`. At a new turn's start, cleanup requires a
held maintenance lock, a finished receipt for the owner's turn, PPID 1, and a
`rem next`/`rem submit` command. Cleanup records the terminated PID, command and
old turn ID in the new receipt. Existing deadline descendant termination stays.

Status and the reader's Today header now expose a single warning derived from
the existing receipts: two failed/timed-out turns, or a last message reporting
that work could not start. This includes a normally completed Codex turn whose
last message is `MAINTENANCE_BUSY`. The warning retains the receipt's reason,
says a retry happened after repeated failed turns, or gives a neutral next
action for a startup block. Healthy completed turns remove the warning.

Terminal `co rem start` and `co rem init` print their access summary and undo
block and proceed. Init still prints its estimate; it no longer asks whether
to build. Recorded consent now retains its summary values so later changes
print a field-by-field diff. Older fingerprint-only consent gets one full
summary because its previous values cannot be reconstructed. Noninteractive
first consent still uses `--yes`; JSON output stays parseable.

## Red-first checks

- Busy ceiling and prompt tests failed on the original retry instruction and
  generic busy error. The deadline test spends 400 seconds in the thread queue
  and permits only 200 seconds of file-lock polling.
- Turn ownership and orphan tests failed without the inherited turn ID and
  cleanup. Cases cover finished vs running receipts, PPID 1 vs a living parent,
  unrelated commands, and stale metadata with a free lock.
- Receipt warning tests failed when no warning existed. Cases cover repeated
  failures, English/Chinese startup blocks, completed busy turns, successful
  recovery and an active turn.
- Terminal tests failed at the old consent and estimate prompts. Cases cover
  summary plus undo, unchanged consent, consent diffs, and JSON estimates.

## Independent review, 2026-11-07

An AI reviewer adopted a technology-founder perspective with marketing and UI
experience; this was not a human founder review. Inspected actual rendered
synthetic empty Today states: retry at 1280×900, blocked at 390×844 in light and
dark themes, and healthy at 390×844. The final mobile DOM had width and
scrollWidth 390; failure was the first header child, and healthy had no warning.
Screenshots are in `/private/tmp/rem-scheduler-review/`.

| Priority | Problem and user impact | Evidence and improvement | Recheck |
| --- | --- | --- | --- |
| P1, fixed | Normal Codex exit hid a lock-blocked turn | Recognize the emitted `MAINTENANCE_BUSY` line in last messages | Completed busy receipts show PID/command in status and Today |
| P1, fixed | Stale owner metadata could authorize cleanup after lock release | Probe the actual lock before evaluating the old process | Free-lock stale-owner test never signals a PID |
| P1, fixed | Every startup failure prescribed an authorization fix | Use neutral recovery wording; keep the original reason | Lock failure never invents an auth cause |
| P2, fixed | Repeated terminal runs could omit summary and undo | Report unchanged consent for terminal CLI calls | Previously consented init prints both and never prompts |
| P2, deferred | “一个安静的早晨” below the failure can feel reassuring about stale data | Preserve title semantics within the requested one-line warning scope | Failure remains first and visible, never inside collapsed details |

No significant issue remained within this scope after recheck. Coverage does
not include populated notebook interactions, every reader page, an actual OS
orphan cleanup, or a live scheduler due-to-completed round. The sandbox denies
`ps`, so process-enumeration trial results cannot be claimed as passing here.

## Validation

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -k "exec or schedule or init or start or first_run or status or next_submit" -n 6
```

Final result: **2103 passed, 11 failed, 3 skipped**. All new regression cases
passed. Failures are two browser process/close tests, two real detached-child
deadline tests (`ps` denied), six handoff tests (explicit sandbox restriction),
and the existing host/watcher test (repository-local state permissions).
An untouched HEAD archive reproduced the ten process/browser/handoff failures;
the host test passed its assertion there but failed the existing guard against
writing `.co/logs` into the repository. These are not an all-green suite.
Full logs: `/private/tmp/rem-scheduler-unit-final.log` and
`/private/tmp/rem-scheduler-baseline-final.log`.

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/e2e/cli -k rem
```

Result: **353 passed, 314 skipped, 554 deselected**. Browser suites are opt-in
and were skipped; the synthetic rendered reviews above are separate evidence.
Log: `/private/tmp/rem-scheduler-e2e.log`. A final help-only contract recheck
covers the corrected startup/estimate wording after this run: **137 passed**.
After the reviewer's final `--start` description correction, the page-output
and no-prompt contract recheck also passed: **42 passed, 95 deselected**.
Logs: `/private/tmp/rem-scheduler-help.log` and
`/private/tmp/rem-scheduler-help-final.log`. `git diff --check` passed.
