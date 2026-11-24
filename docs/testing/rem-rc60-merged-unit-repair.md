# rc60 merged unit repair — 2026-11-08

Branch `release/1.9.3rc60`, starting HEAD `0d05b8c3`. No commits, live provider calls, real sends, or changes to the operator's `~/.co`. All new identities, account paths and tokens are fictional fixtures.

## Decisions for the ten supplied failures

| Failure | Decision and evidence |
| --- | --- |
| `tests/unit/test_rem_collection_failure.py:82`, `test_mail_collection_failure_is_not_lost_before_record_creation[error3]` | Code regression. A typed credential exception does not make its message safe. Unknown `expired` remains `ProviderCredentialError`, preserving this assertion unchanged. Fix: `service._collection_failure`. |
| `tests/unit/test_rem_collection_failure.py:381`, `test_only_safe_failure_prefix_reaches_records_and_status[credential-Bearer ya29.fixture-token]` | Code regression. Raw provider text was copied into records. Original assertion unchanged; only the class name survives this unknown code. |
| Same test, `[credential-Authorization Bearer eyJ.fixture-token]` | Same code regression and unchanged assertion. |
| Same test, `[credential-client_secret=GOCSPX-fixture-token]` | Same code regression and unchanged assertion. |
| Same test, `[credential-key sk-live-fixture-token]` | Same code regression and unchanged assertion. |
| `tests/unit/test_rem_codex_schedule.py:412`, `test_private_file_pins_interpreter_root_model_and_archival` | Legitimate F model-default change. Assert `gpt-6.1-sol`, retaining interpreter, root, local execution, archival and private-mode checks. |
| `tests/unit/test_rem_files.py:37`, `test_inspection_does_not_initialize` | Legitimate F model-default change. Assert `gpt-6.1-sol`, retaining proof that inspection creates no notebook. |
| `tests/unit/test_rem_first_run.py:475`, `test_runner_ok_investigates_me_once_with_inits_window` | Legitimate F model-default change. Assert displayed work model `gpt-6.1-sol`; retain quick/full owner investigation, five-day window and next-action checks. |
| `tests/unit/test_rem_proactive.py:1270`, `test_approve_release_uses_existing_send_path_once_and_checks_slots` | Code integration defect in clock injection. `from .service import now` retained an earlier fixture replacement; approval and release could disagree on the hold deadline. Use dynamic `service.now()` consistently. Original one-send, slot, and repeated-release assertions unchanged. |
| `tests/unit/test_rem_proactive.py:1383`, `test_held_local_reply_never_sends_old_words_against_a_new_version` | Same clock integration defect caused release to return no due item. Original version-safety assertion unchanged: changed version stops delivery, leaves new words intact, sends nothing. |

The work/summary model split is explicit in `connectonion/rem/config.py:40`: work uses `gpt-6.1-sol`; standalone summaries use `gpt-6-luna`. No default was rolled back.

Importing `now` does not freeze production wall time: the original function still calls `datetime.now()` on each invocation. The reproduced mismatch retained a replaced test clock. The code fix establishes one shared clock seam; it does not change approval deduplication, durable claims before IO, or current-version checks.

## Security boundary and recovery

`service._collection_failure` records recognized credential codes and generated recovery commands, and builds human sentences from a fixed code table. Unknown codes and other exceptions retain only their class name. It never reads the exception message or exception recovery text. The existing known credential classifications remain useful, including the four requested recovery codes.

Recovery commands derive from trusted local environment selection and preserve an explicit `--env-file`, including paths containing spaces. Structured diagnostics survive subsequent reads after that selection changes. Saved commands must match the fixed recovery operation, optionally with one absolute selected-file argument. Legacy message suffixes are never trusted.

Source-read state, run logs, status and worker health reconstruct safe messages. Full saved failure objects are rebuilt, so rejected raw `code`/`next_command` fields do not leak through nested JSON. Log readers apply the same boundary, covering both live and offline reader snapshots. Existing legacy files are not rewritten during inspection.

Three additional HTTP tests in `test_rem_collection_failure.py` now expect `HttpError` alone, as required by the new class-only policy for non-credential failures. Continuation, source rotation, checkpoint preservation and reporting assertions remain intact. Existing legacy HTTP prefix redaction coverage remains.

New regressions cover all four requested codes, Gmail/Outlook, default/scoped account selection, token-bearing messages, hostile exception recovery text, every notebook file (including binary state), captured stdout/stderr/logging, status, logs, snapshot data and rendered snapshot HTML. Legacy regressions cover a recognized code followed by a secret and poisoned structured recovery fields. A clock-change regression proves the exact ten-minute boundary and one send across repeated releases.

## Verification

New credential/legacy regressions were observed failing before implementation: `9 failed, 51 deselected in 11.76s`. The clock regression also failed before implementation: `1 failed in 1.92s`.

Final six-module focused run: `648 passed, 1 skipped in 11.22s`. Additional daily-round checks: `35 passed in 2.59s`. The skip names host process enumeration unavailable inside the sandbox. Logs: `/tmp/rc60-scoped-recovery-final.txt`.

An independent AI reviewer checked security, recovery clarity, clock injection, send/version guards and the work/summary model split. Its two findings (lost selected-account scope, raw nested saved fields) were fixed and independently rechecked; no remaining concrete issue was found. This was source/fixture review, not a human founder review or rendered desktop/mobile inspection. No layout changes or live sends were reviewed.

The first requested complete invocation, without terminal/toolchain normalization, cleared all ten original failures but ended:

```text
109 failed, 18336 passed, 20 skipped, 2948 warnings, 1 error in 188.03s (0:03:08)
```

The sandbox has broader failures than the two anticipated cleanup cases: handoff explicitly refuses Codex sandbox execution, process inspection and host cleanup are denied, `TERM=dumb` changes terminal styling, and an Outlook draft-listing I/O failure also reproduces alone. No sandbox guards, unrelated production code or test assertions were weakened. Representative evidence: `/tmp/rc60-environment-failures.txt`.

Both specifically anticipated cleanup cases reproduce `PermissionError: [Errno 1] Operation not permitted: 'ps'` in `codex_exec._terminate_descendants`:

- `tests/unit/test_rem_exec_schedule.py:239`, `test_exec_deadline_kills_detached_grandchild[False]`
- `tests/unit/test_rem_exec_schedule.py:239`, `test_exec_deadline_kills_detached_grandchild[True]`

Final complete run uses the repository's previously documented toolchain/terminal normalization, preserves sandbox guards, and captures unfiltered evidence before the requested grep:

```bash
export PATH="/Library/Developer/CommandLineTools/usr/bin:$PATH"
export TERM=xterm-256color
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 8 --dist=worksteal 2>&1 | tee /tmp/rc60-merged-unit-final.log | grep -E "^FAILED|passed|failed"
```

Final exact last line:

```text
105 failed, 18349 passed, 20 skipped, 2948 warnings, 1 error in 250.47s (0:04:10)
```

All ten supplied failures are absent. The only remaining REM failures are the two `ps`-denied cleanup parameters above. Remaining failures by file:

| File | Failures | Evidence/classification |
| --- | ---: | --- |
| `test_handoff_accept.py`, `test_handoff_pickup.py`, `test_handoff_sealing.py` | 58 + 25 + 8 | Handoff's explicit refusal to launch from the Codex sandbox; guard preserved. |
| `test_rem_exec_schedule.py` | 2 | `ps` denied; both detached-grandchild cleanup parameters. |
| `test_close_ends_what_it_owns.py` | 4 | Browser/process cleanup and inspection; also one teardown error for a lingering `wait` thread. |
| `test_browser_reads_start_nothing_and_give_up.py` | 1 | Forced browser close returned no answer instead of confirmation. |
| `test_one_host.py` | 3 | Host stop/start checks; captured `PermissionError`. |
| `test_server_commands.py` | 3 | Static SSH paths target `/Users/changxing/.co/ssh`; writes denied by read-only protection. No writes were permitted. |
| `test_outlook_commands.py` | 1 | Draft listing reports Microsoft connection/local I/O failure; reproduces alone. Outside the requested REM repair. |

This is not a green full suite or release certification. Full failure details are in `/tmp/rc60-merged-unit-final.log`; no sandbox restrictions were bypassed. `git diff --check` passes, and HEAD remains `0d05b8c3`.
