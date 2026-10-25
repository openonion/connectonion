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

This draft still needs the Codex-only Host execution path, source-scoped REM
preparation and the real device connector before its setup URL can promise a
complete workflow. Current Codex delegation is one-shot; current REM init does
more than create an empty notebook. Treating either as a completed service
would make the instructions shorter by making them false.
