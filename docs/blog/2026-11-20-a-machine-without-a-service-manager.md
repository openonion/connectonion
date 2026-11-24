---
description: rc39 stopped at its own release gate. co init on a Linux machine with systemctl but no user session failed instead of skipping the background Host. Now it says the Host was skipped and finishes.
tags: [Host, Init, Linux, Release]
---

# A machine without a service manager

The rc39 release made `co init` start the background Host. That same release
then stopped at its own gate: the job that installs the built wheel and runs
`co init --yes` exited with 1.

The runner is a Linux machine. It has a `systemctl` binary, so `co init` chose a
systemd user unit. It has no systemd user session, though, so
`systemctl --user daemon-reload` could not reach anything, and `co init` called
that a failed start.

Containers, CI runners and SSH logins without linger are all like this. Having
the binary installed was never proof that a user service manager exists. Now
`co init` asks `systemctl --user` itself. When that does not answer, the machine
counts as having no background service, the same as an unsupported OS:
`co init` prints

    Background Host skipped: A background Host needs a systemd user session, and
    systemctl --user is not reachable here (a container, CI, or SSH without
    linger). Next: co host --serve, to run it in this terminal

and exits 0. A service manager that exists and then refuses to start the Host
still fails `co init`. That is a real problem on a machine that should be
running one.
