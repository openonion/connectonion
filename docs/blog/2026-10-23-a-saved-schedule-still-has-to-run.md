---
title: A saved schedule still has to run
date: 2026-10-23
tags: [Codex, Scheduling, Testing]
---

# A saved schedule still has to run

The owner opened recent Codex projects and found REM maintenance among the work
he wanted to return to. Archiving internal conversations made that list quieter,
but left another question: why should REM maintain a separate clock when Codex
already has Scheduled? He wanted the next preview to use the native timer, and
he wanted it tested on the actual computer before another release.

The first file experiment looked like a dead end. A valid local automation file
was present, yet a short observation window found no execution. The public CLI
and App Server source did not expose schedule management, and the desktop tool
rejected a process outside its trusted ancestry. Repeating those facts would not
answer whether the native file loader could actually work.

We traced the installed desktop implementation and tested its loader separately.
It could adopt a legacy automation file and build its own index without a direct
database insertion. The remaining question belonged to the running desktop.
After controlled restarts, the native scheduler entered a pending startup while
plugin reconciliation continued. Disk pressure also affected the trial. Once
initialization settled, three real scheduled turns executed an isolated Python
marker and the desktop archived all three conversations. The first marker landed
at 17:46:51 Sydney time; subsequent warm runs completed without that long startup.
These observations establish a working route, without claiming a controlled
measurement of which recovery step caused each earlier delay.

That result changes the implementation. On a Mac with Codex desktop installed,
a Codex notebook now registers a private native task, waits for the desktop to
adopt its paused definition, then replaces the old clock. A running old batch or
failed registration keeps the existing timer. The native prompt invokes the
same pinned REM CLI, so source consent, quotas, checkpoints and locks stay in
REM. Completed wrapper and child conversations are archived; their IDs remain
available for investigation.

Time calculations exposed another trap. The tested desktop misinterpreted
explicit timezone rules. Its local wall-clock path worked, including a selected
set of hour/minute pairs. The preview therefore uses native scheduling when the
saved timezone matches the computer and retains launchd for other timezones,
other runners and headless Macs. That fallback is visible. It avoids publishing
a general timezone claim that the actual native implementation contradicted.

Status now distinguishes a definition from native registration and a trigger
from REM completion. It can report an unopened app, a late native clock and a
failed REM pass. Cold initialization is allowed to finish; a few minutes without
a marker no longer becomes a claim that the whole route is impossible.

The [acceptance record](https://github.com/openonion/connectonion/blob/v1.9.3rc21/docs/acceptance/1.9.3rc21/README.md) separates the marker runs, an isolated scheduled REM CLI
pass and the owner's clock migration. Native desktop visuals, remote-project
presentation and sleep/wake behavior still need direct observation. We would
revisit the file adapter when Codex exposes a supported scheduling API, changes
its ownership/storage mode or corrects the tested timezone path. A new protocol
would simplify registration; it would still need an actual scheduled execution.

## Follow-up, 24 October: an acknowledgement belongs to one request

The next day's check brought the same question back. This time the owner asked
us to use the normal installed desktop, keeping its existing login and profile.
The test task appeared in the native index as ACTIVE, with its next run two
minutes away. Six minutes passed without a run record or marker. A normal
desktop restart and another trial produced the same result. The existing REM
task also had an overdue next-run timestamp. Yesterday's executions were still
real; they could not certify the desktop's state today.

Looking at that gap exposed a smaller promise we could actually repair. The
installer waited for PAUSED to be adopted, wrote ACTIVE, then returned. Stop
wrote PAUSED and marked the worker disabled before the desktop had acknowledged
it. Native adoption had taken tens of seconds in the live trial, leaving time
for those local claims to get ahead of the timer.

An independent AI role review found a further complication. If another start
changed the definition back to ACTIVE during a pause wait, a check against the
latest file could accept that ACTIVE record as success. The operation needed an
answer to its own request. The patch now compares the requested definition and
version with the independently observed index, and a concurrent edit ends the
wait with an error. Status also discovers a native task when a first activation
timed out before REM could save its worker record. That delayed activation must
not turn into a reassuring “Stopped” message.

The new account storage path makes the distinction harder to ignore. A migrated
task can keep running after its old file and ID disappear. We can identify a
known legacy association and stop the file adapter from recreating it. We have
not proved that an external client can create or pause the account-owned task:
the native enrollment read responded, but accepting enrollment returned 404.
Tool metadata exposed a creation function without making it callable in the
tested runtime.

A later OS-state check found the Mac locked, but that flag predated a successful
earlier run. The control continued on the same normal installation without
unlocking. Opening `codex://automations` at 09:09:20 UTC was followed by native
execution, a marker and automatic archiving. The overdue production REM task
also began and its full scheduled pass completed with successful command exits.
The installed desktop starts its scheduler capability disabled; the primary
renderer publishes it from a visible-content phase. This control is consistent
with that gate without proving every cause of the earlier missed windows.

The adapter had skipped opening a desktop that was already running. The candidate
now delivers Scheduled after native adoption. An early URL alone still failed
in a cold-launch control. A guarded retry with the post-adoption delivery passed
after restarting only the normal desktop, keeping the same profile and managed
server. It requested 20:35 Sydney, was indexed for 20:36:33, started at 20:36:34
and auto-archived after its marker appeared. Pause was independently confirmed
before removing the owned definition. Those times prove execution, not exact
requested-minute scheduling. The production task stayed ACTIVE across that
restart and its old launchd job remained absent.

Independent review then caught a migration during Scheduled delivery that could
remove the old clock before the file adapter noticed the change. The corrected
handover rechecks the same registration immediately before teardown. Private
fixtures verify that migration and concurrent definition/index changes preserve
the previous clock; they do not establish live account-mode support.

These changes are [under review](https://github.com/openonion/connectonion/pull/2674),
with 262 scheduling/service/CLI command tests and 123 help-contract checks passing.
They have not been released. Native execution, archiving, pause and initialization
after a normal desktop restart now have receipts. Account-managed registration,
exact timing, full server/machine restart recovery and actual native desktop UI
remain unverified. A one-command initialization should remove file editing and
repeated setup work; it still owes the user an accurate distinction between a
saved request, an acknowledged timer and work that really ran.
