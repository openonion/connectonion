# Obligation task dispatcher validation

Branch: `sprint9/task-dispatch`, based on `0d05b8c3` (rc60).
No commits, real Codex task, owner-notebook writes or message sends were made.
All execution tests use temporary fictional Mara/Fern notebooks and a fake Codex.

## Red to green

- Initial `tests/unit/test_rem_tasks.py`: **9 failed**. Native cleanup deleted
  `do-mara/result.md`; dispatcher tests could not import the missing module.
- The fake executable records argv, writes a result/last message and exits zero,
  one, or sleeps past its deadline. Zero without a result is also tested.
- Initial Chrome task-card regression: **4 failed**, absent deliverable card.
- Independent review added red regressions for pre-handler stop, dead-worker
  status, Host launch timeout, orphan Codex cleanup and completed-task approvals.
- Final focused dispatcher/config/reader/Host/CLI checks: **80 passed**.
- Reader and Today JavaScript harnesses include the new renderer; the Host clock
  test now checks public task CLI dispatch instead of the former agent-session
  path. Final reader/Today/Host regression run: **391 passed**.
- `co audit co rem task --json`: four reachable pages, every rule **4/4**,
  no findings. Help was written before implementation.

## Independent AI role review

A separate agent reviewed principal-engineer correctness and the experience from
an AI technology-founder perspective. This was not a real human founder review.
It inspected Today's expanded completed Mara card at 1440 and 390 pixels, in
light and dark themes, and exercised queued → refreshed → completed on local
HTTP at 390 pixels. This does not claim all-page coverage.

| Priority | Issue and impact | Fix and recheck |
| --- | --- | --- |
| P1 | Stop before worker signal-handler installation could leave Starting forever. | Reconcile the dead worker; immediate stop regression passes. |
| P1 | A crashed worker could leave Codex alive while reporting stopped. | Retain and verify Codex identity, kill its group; orphan regression passes. |
| P2 | Host CLI timeout left an approval dispatching forever. | Expected launch failures become durable approval errors; timeout regression passes. |
| P2 | Completed work still appeared in Approve all. | Exclude tasks with receipts; completed approval regression and browser count check pass. |
| P2 | Today lacked a way to fetch task progress or reconcile a crashed worker. | Owner-authenticated refresh calls task status, persists reconciliation, then reloads; endpoint/reconciliation checks pass. |

The four rendered completed states fit the viewport; paths wrap and the copy
reply action is visible. The reviewer found no remaining concrete issue in this
scope after the refresh endpoint correction.

## Full suite and browser commands

The full suite uses a terminal type that supports the existing forced-color
checks (`TERM=xterm-256color`). Its command is unchanged:

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 8 --dist=worksteal 2>&1 | grep -E "^FAILED|passed|failed"
CO_REM_BROWSER_TEST=1 uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/e2e/cli/test_rem_reader_design_browser.py -k task
```

Final Chrome command output:

```text
4 passed, 302 deselected in 68.55s (0:01:08)
```

The untouched rc60 worktree reproduced eight failures (provider error messages
and three expectations of the old work-model default): `8 failed, 47 passed`.
It also reproduced the two held-reply tests when approvals was imported before
the test clock was installed: `2 failed`. Those failures concern an existing
`from service import now` binding and occur without dispatcher changes. The
isolated baseline worktree was removed after checking it.

Full-unit command final failure lines (verbatim):

```text
FAILED tests/unit/test_rem_codex_schedule.py::test_private_file_pins_interpreter_root_model_and_archival
FAILED tests/unit/test_rem_collection_failure.py::test_mail_collection_failure_is_not_lost_before_record_creation[error3]
FAILED tests/unit/test_rem_collection_failure.py::test_only_safe_failure_prefix_reaches_records_and_status[credential-Bearer ya29.fixture-token]
FAILED tests/unit/test_rem_collection_failure.py::test_only_safe_failure_prefix_reaches_records_and_status[credential-Authorization Bearer eyJ.fixture-token]
FAILED tests/unit/test_rem_collection_failure.py::test_only_safe_failure_prefix_reaches_records_and_status[credential-client_secret=GOCSPX-fixture-token]
FAILED tests/unit/test_rem_collection_failure.py::test_only_safe_failure_prefix_reaches_records_and_status[credential-key sk-live-fixture-token]
FAILED tests/unit/test_rem_files.py::test_inspection_does_not_initialize - As...
FAILED tests/unit/test_rem_first_run.py::test_runner_ok_investigates_me_once_with_inits_window
FAILED tests/unit/test_rem_proactive.py::test_approve_release_uses_existing_send_path_once_and_checks_slots
FAILED tests/unit/test_rem_proactive.py::test_held_local_reply_never_sends_old_words_against_a_new_version
FAILED tests/unit/test_one_host.py::test_stopping_co_host_stops_agent_py[SIGHUP]
11 failed, 18494 passed, 19 skipped, 2948 warnings in 238.63s (0:03:58)
```

The remaining Host SIGHUP shutdown failure reproduced both in isolation on this
branch (`1 failed in 11.49s`) and in a fresh untouched rc60 worktree
(`1 failed in 13.03s`). That temporary worktree was also removed. All eleven
full-suite failures are therefore reproduced on the unchanged base; none of the
new dispatcher, task-card, CLI lifecycle or refresh checks is failing.
