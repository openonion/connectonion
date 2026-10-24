# Native REM initialization follow-up — 2026-10-24

Status: **registration and pause verified; timed execution failed**. No new
preview is published from this follow-up. The changes under review improve
registration lifecycle checks; they do not establish support for the newer
account-managed registration path.

## Normal desktop trial

The owner requested the existing normal installation, without an isolated app
profile. The trial used Codex desktop **26.924.22138** on Intel macOS, the normal
Codex home, and managed App Server **0.164.0**. The desktop installation, login,
production task definitions and REM notebook configuration were not replaced.
One normal desktop restart was performed, retaining that installation/profile.

One new, owned test task was reused for two scheduled trials. It was first
registered PAUSED and independently read from the desktop's index, then enabled
for a time two minutes ahead. Its only command created a marker in the trial
directory. Both trials observed ACTIVE and a native next-run timestamp, but no
run record and no marker during the six-minute observation window. The second
trial followed the normal desktop restart. Both ended with a PAUSED definition;
the final native index independently confirmed PAUSED, with no next run.

The existing production REM task also had an overdue next-run timestamp and no
trigger recorded that day. Its configuration was not changed. These results
do not invalidate the earlier rc21 clock/CLI execution receipts, but they do
prevent treating those earlier successes as proof that today's desktop is
running its timer.

The running App Server reports `in_app_local_automation` enabled and stable.
Consequently, an enabled setting and a registered ACTIVE task are insufficient
readiness checks. The exact reason this desktop did not advance its timer is
still unresolved. Actual Scheduled UI and its access/migration prompts were
not inspected: the available computer tool had no native surface, and macOS
denied assistive access. No permission or native feature gate was bypassed.

A subsequent OS-state check reported the console screen locked. The inspected
desktop defers publication of local automation capability until
`first_content_visible`. Visibility is therefore an unresolved test condition;
this observation does not establish the cause of both failed windows. An
unlocked, visible-main-window comparison on the same installation is pending.

## Account-managed registration

The official newer **26.1021.31345** desktop package was inspected locally. Its
implementation can migrate local definitions to account-managed registration,
replace IDs, and remove the old TOML. The local executor still runs on the
computer. That implementation is not a public CLI scheduling contract.

Runtime `app/read` exposed Automations metadata including `create_local` and
`update_local`. The app was absent from the installed runtime, and an owned
thread could not invoke those tools. A desktop-owned queued message likewise
did not create the requested paused test task. Queue delivery is not proof of
registration.

Using Codex-managed authentication in memory and matching workspace routing,
the native service returned `not_enrolled` for an owned trial installation.
Submitting the desktop's enrollment acceptance request returned HTTP 404,
including when tested with the installed desktop's request contract. Task
creation was not reached. No token was printed or written into a receipt.
The account's eligibility and the reason for the 404 remain unverified.

The public Codex protocol inspected at commit
`970111f6cb62cc02fe36a82ea7d71b37a2889c97` has no scheduling CRUD request.
The earlier automation protocol proposals are closed, unmerged drafts. Neither
those drafts nor the retained TOML parser establish a future compatibility
promise or a removal date.

## Changes under review

- Open the normal installed desktop when initialization needs it.
- Require independent ACTIVE adoption before reporting installation success.
- Require independent PAUSED adoption before disabling the REM worker or
  loading a replacement launchd clock. Existing native model turns may finish.
- Distinguish the requested status from an observed ACTIVE timer, including
  when an older stopped worker record disagrees with the native index.
- Discover a known migrated task through its legacy association. Refuse to
  recreate its old file or mutate it through the legacy adapter. A cached
  account PAUSED state is not authoritative confirmation of a server pause.

The migration tests use private database fixtures. They are not a claim of a
live account migration, account task creation, or account pause succeeding.

Final local regression: **257 passed, 3 existing deprecation warnings** across
native scheduling, launchd scheduling, REM service and CLI tests. These include
a concurrent activation during pause, delayed first activation without a worker
record, and pending reactivation behind a previously stopped worker. Twelve
provider/intent/observed-state combinations also prevent a false Stopped state.

## Creation and support decision

Keep the existing `init` → background-start hook. Use the local-file adapter
only while that is the desktop's actual registration mode. For account storage,
the supported direction is creation through a callable native Automations tool
in the signed-in desktop context, retaining its canonical ID for later reads,
updates and pauses. This route still needs an end-to-end proof on an eligible
account; metadata visibility alone does not qualify it.

Initialization should not force a migration of unrelated tasks or ask the user
to edit configuration files. Required desktop consent must remain a normal
native product action. An unavailable native registration path must be reported
accurately rather than silently creating another timer.

Release acceptance still requires actual timed execution, final CLI exit,
archiving, repeat initialization, update, pause, and restart/sync persistence.
Automatic archiving in a newly created account-managed task is also unverified.

References:

- [Official scheduled tasks guidance](https://learn.chatgpt.com/docs/automations?surface=app)
- [Official App Server guidance](https://learn.chatgpt.com/docs/app-server)
- [Public protocol registry](https://github.com/openai/codex/blob/970111f6cb62cc02fe36a82ea7d71b37a2889c97/codex-rs/app-server-protocol/src/protocol/common.rs)
- [Unmerged automation protocol proposal](https://github.com/openai/codex/pull/28613)

## Review coverage

Independent AI role reviews identified the lifecycle gaps before the patch.
The final independent AI review found no remaining P0/P1 in the corrected code
scope and independently checked those twelve combinations and the confirmed
PAUSED control. Actual guide screenshots covered desktop compatibility expanded
and phone expanded/collapsed states. This was not a human founder review, a
native desktop UI review, or an all-page pass. Lower guide sections, copy/link
actions, the page-review disclosure's expanded state, remote-project history,
account creation and post-migration persistence/archiving remain unverified.
