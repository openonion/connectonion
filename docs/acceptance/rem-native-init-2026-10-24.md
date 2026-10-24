# Native REM initialization follow-up — 2026-10-24

Status: **normal-profile native execution, auto-archiving and pause verified after opening Scheduled**. No new
preview is published from this follow-up. The changes under review improve
registration lifecycle checks; they do not establish support for the newer
account-managed registration path.

## Normal desktop trial

The owner requested the existing normal installation, without an isolated app
profile. The trial used Codex desktop **26.924.22138** on Intel macOS, the normal
Codex home, and managed App Server **0.164.0**. The desktop installation, login,
production task definitions and REM notebook configuration were not replaced.
Normal desktop restart controls retained that installation/profile.

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
readiness checks. The initial failure was narrowed by the subsequent wake control below. Actual Scheduled UI and its access/migration prompts were
not inspected: the available computer tool had no native surface, and macOS
denied assistive access. No permission or native feature gate was bypassed.

A subsequent OS-state check reported the console screen locked. The inspected
desktop has both a renderer-ready fallback for starting its timer and a
visible-content phase around capability publication. Visibility is therefore
an unresolved test condition, rather than an established single startup gate
or the cause of both failed windows. The lock flag predates a successful earlier run and is not treated as a prerequisite or a proven cause. The same normal-profile control continued without unlocking the OS.

## Scheduled wake control

At 09:00 UTC the existing managed App Server accepted initialization and reported
version 0.164.0. `automation/list` returned an unknown-method error, consistent
with the freshly fetched public protocol registry (blob
`3a777cdc3d24b43356efc575bba9b2f236ef0de0`). A new owned task was adopted PAUSED,
then ACTIVE with a 09:07 UTC future slot. It had no run before the control.

At **09:09:20 UTC**, `/usr/bin/open -a /Applications/Codex.app codex://automations`
opened the existing normal app's Scheduled entry point. The owned native task
started at **09:09:41**, created its marker and was **auto-archived by 09:09:50**.
Its pause was independently acknowledged before its test definition was removed.
The overdue production REM task also started at 09:09:21; its task definition
and notebook configuration were not edited. Its full CLI completion remained
under observation when this section was written.

Installed desktop code initializes its scheduler capability to false and requires
that capability before its tick advances work. The primary renderer publishes
`automations.local` from a component mounted at `first_content_visible`.
The control is consistent with that gate; it does not isolate every possible
startup cause. The REM adapter had skipped opening the app whenever its process
was already running. The candidate now opens Scheduled explicitly instead.
A second timed trial used the patched install lifecycle without an extra manual
UI action. It requested 20:17 Sydney, indexed its next run at 20:18:31, started at
20:18:42 and auto-archived after its marker was created. Pause was independently
confirmed and the owned definition removed. This proves execution, not exact
requested-minute timing. The production scheduled pass completed, and the native
wrapper was auto-archived with its command execution items reporting exit 0.
The first cold-launch control, with only an early deep-link, failed to execute
and was independently paused. This led to a startup-order fix: launch if needed,
stage and confirm native adoption, then deliver Scheduled again before changing
clock ownership. The guarded retry stopped only the normal desktop while native
runs were idle, retained its installation/profile and the managed server, and
used the patched install lifecycle. It requested 20:35 Sydney, indexed 20:36:33,
started 20:36:34, created its marker and auto-archived by 20:37:11. Pause and owned
definition removal were confirmed. The existing production task remained ACTIVE
across the restart and no launchd job was installed or loaded for that notebook.
Account-managed-mode acceptance remains separate.

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

- Open the normal installed desktop directly at `codex://automations`, including when its process is already running.
- Require independent ACTIVE adoption before reporting installation success.
- Require independent PAUSED adoption before disabling the REM worker or
  loading a replacement launchd clock. Existing native model turns may finish.
- Distinguish the requested status from an observed ACTIVE timer, including
  when an older stopped worker record disagrees with the native index.
- Discover a known migrated task through its legacy association. Refuse to
  recreate its old file or mutate it through the legacy adapter. A cached
  account PAUSED state is not authoritative confirmation of a server pause.
- Recheck the same native registration after opening Scheduled and before
  removing the previous clock. A migration or definition/index change during
  that open aborts the handover and preserves the old clock.

The migration tests use private database fixtures. They are not a claim of a
live account migration, account task creation, or account pause succeeding.

Latest local regression: **262 passed, 3 existing deprecation warnings** across
native scheduling, launchd scheduling, REM service and CLI command tests;
**123 help-contract tests passed** separately. These include
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

Local-file execution, production CLI completion, archiving, pause and a normal
desktop restart followed by automatic initialization have live receipts. Exact
requested-minute timing and live account-managed creation/update/pause/migration
remain unverified; those results must not be inferred from the legacy controls.
Automatic archiving in a newly created account-managed task is also unverified.

References:

- [Official scheduled tasks guidance](https://learn.chatgpt.com/docs/automations?surface=app)
- [Official App Server guidance](https://learn.chatgpt.com/docs/app-server)
- [Public protocol registry](https://github.com/openai/codex/blob/970111f6cb62cc02fe36a82ea7d71b37a2889c97/codex-rs/app-server-protocol/src/protocol/common.rs)
- [Unmerged automation protocol proposal](https://github.com/openai/codex/pull/28613)

## Review coverage

Independent AI role reviews identified the lifecycle gaps before the patch.
The post-adoption review found a P1: migration during Scheduled delivery could
remove the legacy clock before file-storage eligibility was checked again.
Its private-fixture regression failed before the fix. The final independent AI
recheck verified that migration, definition and index changes abort before
teardown, that ACTIVE updates remain ACTIVE, and that normal PAUSED handover
still succeeds. No remaining P0/P1 was found in that added guard. Earlier
reviews checked the twelve state combinations and the confirmed PAUSED control.
Actual guide screenshots covered desktop compatibility expanded
and phone expanded/collapsed states. This was not a human founder review, a
native desktop UI review, or an all-page pass. Lower guide sections, copy/link
actions, the page-review disclosure's expanded state, remote-project history,
account creation and post-migration persistence/archiving remain unverified.
