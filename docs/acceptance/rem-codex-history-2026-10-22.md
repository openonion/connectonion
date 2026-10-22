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

## Final recheck

The actual-adapter trial was repeated from an isolated environment installed
from `connectonion-1.9.3rc13-py3-none-any.whl`, outside the source checkout.
The imported package reported 1.9.3rc13 from that environment's site-packages;
both calls succeeded, kept one thread ID and its invented context, and ended
with the trace present only in archived results.

The independent final AI review received the complete relevant adapter excerpt,
unit tests and wheel-trial output directly. It found no correctness blocker in
that narrow scope. A prior suspicion that `chunks` was uninitialized was
rejected against the full excerpt: it is initialized before `on_event` and the
try block. This does not certify native desktop UI or native scheduling.

The docs-site production build's article checks passed: 145 generated articles
and 169 feed/sitemap entries. The rendered journal was also opened at phone
width. All docs-site changes remain on a local preparation branch; no package,
release tag or production docs publication has been made.

## Release-floor and live-desktop recheck

The latest CI matrix exposed one shared failure: handoff still pinned rc12
while the candidate package reports rc13. The release floor now matches rc13;
all 75 handoff acceptance tests pass locally. An independent AI reviewer found
the narrow change correct and requires the CI matrix and published tag URL to
be checked again. No native UI was inspected in this review.

The local REM status still reports its enabled launchd job and a completed
06:00 scheduled slot. No migration has been performed. The running Codex main
process started October 3, whereas the inspected installed bundle is newer;
this does not establish the running scheduler's version or capability state.
The earlier live native probe produced no registration, run or result marker.
Opening the actual Automations page is the outstanding desktop check; isolated
native-code tests are not a substitute for a live scheduled execution.

PyPI was checked again: Pillow 13.0.0 requires Python >=3.11 and there is no
newer 12.x release than 12.3.0. The dependency audit remains unresolved.

## Security candidate update

The candidate now requires Python >=3.11, Pillow >=13.0.0, pypdf >=6.21.2 and
cryptography >=50.0.2. The former Intel-only cryptography <49 cap was removed
because it retained reported vulnerabilities. Local default-runtime lock-export pip-audit
2.10.1 reports `No known vulnerabilities found`, with no ignored advisories.
The first Python 3.11 focused run passed 309 tests (installer, file reading,
attachments, scrolling, REM runner, Codex adapter and version consistency).
That run preceded the final cryptography floor; the native Intel source build
and post-upgrade cryptographic tests are separate outstanding checks.

No native Schedule success is claimed and no migration has occurred. Security
release readiness must not imply that the native integration is finished.

Post-upgrade recheck: Intel macOS successfully compiled and installed
cryptography 50.0.2 with the existing Rust toolchain and Homebrew OpenSSL.
The final focused Python 3.11 suite passed 403 tests, including Chrome cookie
cryptography, encrypted handoff, dependency floors, installation, PDF/attachment
reading and REM. Wheel and sdist passed twine checks. A clean isolated uv tool
installation of the built wheel selected Python 3.14.7, installed its full
dependencies, and `co --version` reported 1.9.3rc13. This did not replace the
owner's installed co or its REM scheduler.

Independent AI release review inspected committed change 38c23b91. It found a
P1 stale Python 3.10 claim in the Windows FAQ; that FAQ now distinguishes stable
1.9.2 from preview rc13. The installation skill documentation also explains the
preview requirement. Recheck criterion: current installation guidance must not
suggest that rc13 supports Python 3.10. Review did not inspect native desktop UI.
Rendered local release notes were inspected at desktop width; security and
Python requirements are visible beside the opt-in installation commands.

The default-only audit did not cover the optional Synology extra. Its Paramiko
4.0.0 SHA-1 advisory is addressed by rc14; see
[expanded optional-dependency acceptance](rc14-optional-security-2026-10-22.md).
