# REM Codex history acceptance — 2026-10-22

## Scope

Candidate 1.9.3rc13 archives internal REM Codex calls. It does not migrate
REM's trigger to native Scheduled. Existing launchd jobs and old conversations
are not modified by this patch or the isolated live trial.

## Live evidence

Local Codex CLI 0.163.0, configured ChatGPT Pro account, gpt-6-luna, read-only
sandbox and an invented memory word in a temporary workspace. Called the actual
Python adapter twice with the REM child flag, resuming the returned thread ID.
The second call retained the first call's context. Native `thread/list` with
`useStateDbOnly` excluded that ID from active results and included it in archived
results. No source mailbox or production notebook was read.

```json
{"adapter_first_exit": 0, "adapter_resume_exit": 0, "same_thread": true, "context_retained": true, "absent_from_active": true, "archived_trace_retained": true, "thread": "01a15f04-6376-7980-a058-9dbb8daf05fb"}
```

The initial trial caught that `thread/resume` refuses archived threads; the
adapter now calls `thread/unarchive` before REM resume. A listing without
`useStateDbOnly` exceeded the trial's 15-second deadline; the final check uses
the native state-database query, rather than scanning the owner's whole history.

## Independent AI review

Role: technology founder with marketing/UI experience; not a human founder.

- P1: archive failure could replace the result and lose its thread ID. Fixed by
  archiving inside the existing adapter error boundary. Recheck: injected archive
  failure returns its ID, prior message, usage and completed-turn status, with a
  visible error; client still closes.
- P2: ordinary automatic timeout retries can start a new thread. This predates
  the change; only explicit resume is promised here. Recheck: two actual adapter
  calls return the same ID and retain context after archive/unarchive.
- P2: cancellation/process death may leave active threads. Documented; no blanket
  guarantee or deletion of user history is claimed.

## Coverage limits

Protocol-level active/archived lists were checked. The native desktop sidebar,
remote project UI, device-off behavior and native Scheduled adoption were not
inspected or certified by this trial. Documentation rendering is checked
separately; this is not an all-pages UI pass.

## Local validation and release status

- 245 adapter/runner tests passed after the cleanup fix; 37 release checks and
  53 import/version checks passed against the prepared docs-site branch.
- Full suite: 16,964 passed, 329 skipped, 16 failed. Seven version-related failures
  were caused by changing the version while that suite was running; stopped
  editing and reran the affected import/version files (53 passed). The remaining
  nine failures reproduce on untouched main: six terminal-colour expectations
  under this environment and three Neonize imports that require `typing.Self`
  in the local Python 3.10 installation. None is presented as a passing check.
- Wheel/sdist build and exact-artifact twine checks passed.
- Docs-site lint: zero errors, 155 existing warnings; production build passed.
- Rendered local desktop `/cli/rem` at 1440×1000 and phone
  `/releases/1.9.3rc13` at 390×844. Preview scope and unchanged launchd schedule
  are explicit; these two screenshots are sample coverage only.
- Release blocked by dependency audit: Pillow 12.3.0 has eight reported
  vulnerabilities, fixed in 13.0.0; that version needs Python ≥3.11, whereas
  ConnectOnion supports 3.10. No security gate or compatibility requirement
  has been bypassed.
