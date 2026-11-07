# Approve the morning

Today opens with **Approve all N** / **批准全部 N 项**. The sheet lists prepared
replies (recipient, subject, first line), already-handled threads, and tasks.
Rows start checked. Replies with marked owner slots start unchecked and disabled;
reviewing and saving a filled reply enables its row. Confirmation shows each
item's own result. Successful rows are frozen; failed rows remain reviewable.

Static snapshots disable the header action and show `co rem open`. They have no
active Undo. Labelled private replies use the reader's existing reveal behavior.
Mailbox thread links are quiet secondary actions.

## Host contract

The authenticated loopback reader posts `/rem/approve` with `ids` from
`approval_outcomes` and optional edited `bodies`, keyed by outcome id. The same
endpoint accepts `action: "undo"` with held reply ids. Invalid/stale items and
expected provider failures return individual errors. Existing cookie, loopback,
Host-header and JSON gates apply.

`approvals.outcomes` adapts the branch's prepared drafts and Today classifications.
There was no separate explicit night-outcome payload on this branch. The sheet
uses common fields, and `approvals.ACTIONS` holds the outcome handlers. Today
ranking and the person metrics are unchanged.

The outbox is the notebook's operational `approvals.json` state. Reply ids include
the prepared source version; repeated requests do not send again. Outlook uses
the existing reply scheduling path and keeps its message id for cancellation.
Gmail and chat remain local until the Host's minute clock releases them after the
10-minute deadline. If the Host is stopped, local delivery waits for its return.
Tasks enter the existing Host session input path without holding the notebook
lock or blocking subsequent clock ticks. Handled threads use the existing done
state and grouped keys.

Scheduling is claimed durably before provider IO. Ambiguous errors do not retry
a send automatically. They remain visible after reload with an instruction to
check the provider before sending again. Local delivery rechecks the source
version; Undo never overwrites a newer draft. Held replies reject the older
send, redraft, provider-edit, prepare and discard controls until cancelled.

## Independent AI review

The reviewer used a technology founder role with marketing and UI experience.
This was an AI review, not participation by a human founder.

| Priority | User impact / evidence | Improvement and recheck |
| --- | --- | --- |
| P1 | Task turns could block Undo through the notebook lock. | Claim outside agent execution; a dispatch regression obtains the notebook lock from another thread. |
| P1 | An accepted Outlook request followed by a timeout could duplicate a send. | Persist scheduling first; repeated approval after requests/httpx timeouts invokes the client once. |
| P1 | Older draft controls could replace a held reply. | Guard those paths; parameterized tests reject each mutation while held. |
| P1 | Undo could overwrite a newer draft or local delivery could use old words with a new source. | Check versions on restore/delivery; stale-version regressions retain the newer reply. |
| P1 | A failed cancellation could leave no working retry. | Retain failed holds and countdown; Node behavior test cancels successfully on retry. |
| P1 | A restored CTA could open an empty sheet after Undo. | Resolve outcomes at click time; reopening regression uses the restored row. |
| P2 | Edits could misrepresent an in-flight or already-held body. | Freeze request controls and successful editors; Node regressions inspect disabled states. |
| P2 | Private content and failed delivery could lose their presentation state. | Preserve privacy wrappers and durable status copy; behavior tests inspect both. |
| P2 | A file snapshot could offer active Undo. | Suppress live Undo in static files; behavior regression checks no bar or request. |

Coverage: backend and actual reader function behavior, including selection,
slots, mixed results, editing, cancellation retry, reopened sheets, static
controls, privacy wrappers and error copy. Browser cases were added for 390 px
and desktop, in light/dark themes. **Rendered pages were not inspected:** installed
Chrome aborts in this sandbox (`SIGABRT` / `EPERM`), and the existing browser
access service is unavailable. Typography, spacing, viewport fit and actual
modal/focus interaction still require the opt-in suite in a browser-capable
session. No all-page or visual pass is claimed.

## Red-first evidence

All new regressions use fictional people and mocked mail/chat clients; no real
mail was sent. Focused failing logs are retained in `/tmp` for this session:

- `/tmp/rem-red.log`: eight failures before batch approval / secondary-action fixes.
- `/tmp/rem-review-red.log`: seven failures for lock ownership, held mutation guards and stale Undo.
- `/tmp/rem-timeout-red.log`: durable timeout/privacy regression failed before the claim fix.
- `/tmp/rem-stale-red.log`: old reply delivery against a newer source failed before the version check.
- `/tmp/rem-ui-red.log`: two sheet/Undo regressions failed against the previous UI functions, then the fixed source was restored.
- `/tmp/rem-filled-slot-red.log`: a filled reply retained its blocked metadata before the fix; approved receipts now clear it.
- `/tmp/rem-final-review-red.log`: four failures for restored CTA, request freeze, snapshot Undo and httpx timeout handling.

The required unit command, required opt-in browser command and adjacent checks
are recorded in the task's final response with their exact final output lines.
No commit was created, and the owner's `~/.co` notebook was not used as a test target.

Final validation (2026-11-08):

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_proactive_http.py tests/unit/test_rem_reader.py tests/unit/test_rem_today.py -n 6
```

Exact last line: `532 passed in 55.10s`

```sh
CO_REM_BROWSER_TEST=1 uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/e2e/cli/test_rem_reader_design_browser.py tests/e2e/cli/test_rem_reader_browser.py tests/e2e/cli/test_rem_open_snapshot_browser.py -n 4
```

Exact last line: `18 failed, 2 skipped, 307 errors in 331.29s (0:05:31)`.
All 325 runnable cases stopped at `BrowserType.launch` with `TargetClosedError`;
none reached a rendered page. Complete output: `/tmp/rem-browser-final.log`.

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_outlook.py tests/unit/test_rem_reader_threads.py tests/unit/test_rem_live_reader.py tests/unit/test_rem_reader_lazy.py tests/unit/test_schedule.py -n 6
```

Exact last line: `159 passed in 20.31s`

`git diff --check` and syntax checking the complete embedded reader JavaScript
also passed. The final independent code recheck found no remaining significant
issue in the reviewed changes; its rendered-coverage gap remains open.
