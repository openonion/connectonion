# Native REM next/submit review

Role: independent AI reviewer acting as a technology founder with marketing and UI experience. This is a role-based review, not a claim of human founder participation.

The review exercised actual terminal flows on fictional notebooks under `/tmp`, and inspected the task/cursor implementation, documentation and shared stage code. No personal notebook was used.

## Findings and recheck criteria

| Priority | Problem and user impact | Improvement | Evidence and recheck criterion |
| --- | --- | --- | --- |
| P1 | Unrouted material exposed no output path and submit crashed. | Print the output notebook directory; accept one new page with shared maintenance checks. | `test_new_page_maintenance_has_an_output_directory_and_promotes`: prepare, write and submit a new page. |
| P1 | A malformed optional review could fail after page promotion and strand the cursor. | Prevalidate side outputs before promotion. | `test_bad_side_output_is_refused_before_canonical_promotion`: traversal is refused; canonical bytes stay identical; correcting the side output permits submission. |
| P1 | A pending task could be scrubbed or overlap manual sync. | Protect pending and active-round evidence; refuse sync before import/tidy. | `test_manual_sync_refuses_before_import_tidy_or_scrub`: every file remains intact. |
| P1 | Discarded tasks could consume evidence. | Preserve abandoned batch checkpoints and leave feedback retryable. | `test_discard_does_not_consume_feedback`: pending feedback remains in the plan. |
| P1 | Feedback acknowledgements could rewind a newer source checkpoint between tasks. | Check live progress before batch preparation and acknowledgement. | `test_newer_source_checkpoint_is_preserved_between_feedback_tasks`: newer checkpoint survives refusal and discard/reprepare. |
| P1 | Audit handoffs could exceed the daily cap or charge yesterday. | Gate each audit and give it a separately dated reservation. | `test_audit_handoff_respects_daily_cap_and_resumes_tomorrow`: today's audit consumes today's last call. Independently reproduced through the CLI. |
| P1 | Validation depended on more than the target page's hash. | Bind lookup pages, explicit material files, expanded original source IDs, prior citations, thread tails and routed inputs. | `test_changed_input_refuses_without_any_writes` and `test_modified_archived_original_refuses_even_when_task_material_is_intact`. |
| P1 | Audit output guards could leave the original candidate unguarded. | Validate both output files for size and symlinks. | `test_changed_original_candidate_cannot_become_a_symlink_during_audit`: refuse before promotion. |
| P1 | Process death after the atomic page write could lose task progress. | Keep a single-page promotion receipt and reconcile it without rerunning a model or replaying the phase. | `test_promotion_recovers_after_process_dies_before_task_acceptance`: page unchanged on recovery, task accepted and cursor advances. |
| P1 | Accepted project snapshot citations could lose their originals at cleanup. | Retain cited originals at the native atomic-write boundary. | Inspected `runner._write_page` and existing retained-source checks. A complete native project-to-cleanup browser flow remains unverified. |
| P2 | Ordinary pending checks parsed all historical task material. | Read the cursor's pending task only. | `test_pending_looks_up_only_the_cursor_task`: malformed historical JSON is never read. |
| P2 | A new round reset the translation allowance. | Count today's prior translation runs. | `test_translation_limit_uses_prior_rounds_from_today`. |
| P2 | Later rounds omitted held refused-material retries. | Share `daily.prepare_retry`, include due ledger rows and preserve their receipt rules. | `test_later_round_retries_held_refused_material`. |

## Coverage and limits

Actually inspected: `next --help`, `submit --help`, plain and JSON task output, valid/refused candidates, printed audit work, missing output, invalid usage JSON, midnight accounting, stale inputs, discard, newer source checkpoints, pending cleanup, new-page maintenance, logs and separate-process investigation continuation. Documentation and code were read.

The final focused independent recheck passed the then-current 20 native tests, and found no new confirmed crash or data-loss blocker within that coverage. The final retry-path recheck independently passed its new regression and closed the remaining retry parity finding.

Native specialist skill/inquiry/quote paths share existing stage preparation/checking, but have not each received a complete native end-to-end trial. No full live scheduled round, browser reader pages, mobile layout, or installed Codex Scheduled automation was tested. This is not an all-page or full-round pass.

## Final validation

The final native regression file passed 22 tests. The exact required full unit command finished with 4,739 passed and two failures in unchanged macOS process-inspection tests. The sandbox's `/usr/bin/pgrep` itself fails with `Cannot get process list`; no test was skipped, disabled or weakened to hide those failures. The final source passed Python compilation and `git diff --check`.

Commits could not be created because the worktree's Git index is outside the session's writable roots. No push was attempted.
