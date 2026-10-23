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

The [acceptance record](https://github.com/openonion/connectonion/blob/v1.9.3rc19/docs/acceptance/1.9.3rc19/README.md) separates the marker runs, an isolated scheduled REM CLI
pass and the owner's clock migration. Native desktop visuals, remote-project
presentation and sleep/wake behavior still need direct observation. We would
revisit the file adapter when Codex exposes a supported scheduling API, changes
its ownership/storage mode or corrects the tested timezone path. A new protocol
would simplify registration; it would still need an actual scheduled execution.
