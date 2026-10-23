---
title: The browser must not replace its supervisor
date: 2026-10-23
description: Why an already running browser needs a different startup contract inside a supervised job.
---

A reimbursement worker was ready to move into its own browser runtime. Keeping
the existing finance task open was a requirement: restarting the shared browser
to load a fix would interrupt another task. A separate daemon, profile and
service looked like enough isolation.

The gap appeared between preflight and the next tool. Preflight could prove the
new daemon was alive, but the normal browser client starts a daemon when it
cannot connect. If the supervised process died a moment later, a short-lived
worker could silently become the parent of its replacement. Setting the
service to never restart did not control that client startup path.

The usual behavior is useful at a terminal. A person types a page command and
gets a browser. A managed job already has a process responsible for startup,
and needs disappearance to be visible. Those are two different contracts for
the same command.

The client now accepts an optional local daemon PID pin. A supervised worker
sets it to the daemon it has verified. The client checks the recorded live
owner before connecting and before sending a command. It carries that check
through the engine protocol probe, its reconnect and read keepalives. A missing
or replaced owner is an error, with no daemon startup or browser installation.
Ordinary unpinned commands keep their existing behavior.

Review found another path that mattered as much as navigation: close. A client
that cannot connect to a stuck browser can normally finish the close by stopping
its process tree. Re-reading the endpoint owner in that fallback could select a
replacement daemon. A pinned client refuses that fallback and never adopts a
new owner for cleanup. A tree already captured for the original daemon remains
subject to the existing close barrier; losing the owner during a failed request
returns an error for the supervisor to inspect.

The regression cases reproduce disappearance after preflight, replacement
during connect, a supplied connection, loss after the engine probe and owner
replacement during close. They require zero startup, provisioning and
replacement cleanup. The pin does not prove an account, secure an endpoint or
identify a paid session. Those checks still belong to the surrounding service.
It gives that service one narrower guarantee: losing its browser will not make
the next tool quietly create another one.

The real CLI trial kept the browser unopened. The correct pin listed zero
tabs; after that daemon exited, a navigation command failed. A new daemon on
the same private endpoint was left untouched by the old pin and answered its
own pin. Both trial processes then exited. This checks the process boundary
without claiming a paid browser session or production migration succeeded.
