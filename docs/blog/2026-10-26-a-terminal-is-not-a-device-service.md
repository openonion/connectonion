# A terminal is not a device service

The first device setup asked a user to find a command, arrange a native bridge,
run a Host and prepare memory. Even after those steps, closing the terminal
could make the Mac disappear. The user wanted one URL to hand to Codex and a
computer that remained available afterward.

Adding more instructions would leave the same operational work with the user.
Launching a shell in the background would hide it without solving login,
crashes, duplicate processes or stopping the service. The chosen first slice
uses the operating system's user-service lifecycle while keeping foreground
project hosting available.

A saved configuration is not a running process, and a running process is not a
paired Watch. Initialization must report those facts separately. Repeating setup
should reuse a working service, preserve user edits and repair known omissions.
Removing a service should not remove the person's memory or recordings.

The candidate now adds an explicit global `co init --background`, an empty REM
preparation path and a Host adapter using the existing native Codex plugin.
There is no managed outer model call merely to delegate. The normal authenticated
Host owns session continuation and permissions; remote text cannot select a
different native thread or workspace. Codex login remains a separate preflight.

Readiness revealed two practical traps. Fresh projects share the configured
global identity, so loading a nonexistent local key failed even when the Host
was working; comparing only the global address could accept another process.
Readiness now checks the launchd PID's actual IPv4 listener and its local Host
endpoints. Discovering the listener also respects ports chosen through the
existing project environment, without reopening account files to guess.

An actual isolated lifecycle trial then caught an immediate stop/restart race:
launchd returned EIO while its previous job was retiring. A bounded retry for
that specific result handles the observed transition. Synthetic real services
were removed after the trial. Crash recovery and lifecycle observations do not
prove login recovery, real device pairing or an end-to-end memory workflow.

The real device connector, native bridge distribution and published setup URL
remain incomplete. The candidate must report that state, even with a healthy
Host and prepared REM directories. Shorter instructions are useful only when
the underlying workflow exists.
