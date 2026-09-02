---
title: "One project, one environment"
date: "2026-09-02"
description: "The identity walk already knew where a project ended. Dotenv loading needed to use it too."
---

Changing into `src/` should not change which account a project uses. Yet the
environment-loading audit found two different answers to where that project
was. Identity, auth, and status used the directory containing `.co/`. Package
startup read `.env` from the working directory instead.

A project key could disappear simply because a command ran one directory
lower. A global key filled the gap; if the subdirectory had its own `.env`,
that file won instead. The account-mismatch guard still protected managed
OpenOnion requests, but it could not make the environment itself consistent,
and third-party provider keys had the same directory-dependent selection.

The first regression used fake credentials in three places: the project,
its `src/` directory, and a temporary home. Importing the SDK from the project
selected the project value. Importing it from `src/` selected the nested value.
Running the CLI import repeated the failure. No service or real key was needed
to demonstrate the mismatch.

Changing package startup alone was not enough. The CLI loaded the working
directory again, and Gmail, Outlook, GDrive, and Synology each had their own
reload. Even when the project value was already present, those later reads
could introduce variables found only in the nested file. The patch removes the
redundant CLI-startup read and makes each integration use the existing project
root resolver.

That resolver is deliberately bounded: it stops at a Git repository or home
boundary, recognizes worktree `.git` files, and does not mistake `~/.co` for a
parent project. Creating another unbounded dotenv search would have restored
the same bug in a different form.

The ordering stays familiar: an explicitly supplied process variable wins,
then the project `.env`, then global `keys.env`. Outside a configured project,
the current directory's `.env` still works. The regression suite checks those
boundaries, nested projects, absent project files, and all four integration
reloads. It tests source selection, not the contents of anyone's credentials.

The lesson is small: a correct project boundary is useful only when every
loader uses it. A second definition of the project can undo the first without
ever raising an exception.

The stable release target is 1.7.3, after the 1.7.2 candidate was stopped before
publication to clarify global versus explicit-project initialization. It also includes the previously merged
canonical `oo` useful skill and dependency-lock security update. The environment
fix and its regressions are carried to the active 1.8 line separately; stable
version metadata does not travel with that forward-port. Publication is gated
on the reviewed tag's cross-platform tests and installed-artifact checks.
