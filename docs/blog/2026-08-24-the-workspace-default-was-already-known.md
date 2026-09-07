---
title: "The workspace default was already known"
date: 2026-08-24
author: ConnectOnion Team
---

The release candidate had finally crossed the awkward part of our Work Room
test. A user had selected Auto, the outer approval boundary recognized the
managed delegation, and the live agent chose Claude Code for a real project.
Then nothing started.

The trace ended with a surprisingly ordinary Python error: `cwd` was missing.
The model had supplied the task, but it had not repeated the directory that the
operator had already assigned to this Work Room. We had treated a known piece
of host configuration as though it were a decision the model needed to make on
every call. A valid delegation died at the doorway.

That failure changed the question. Instead of asking how to make the model more
reliable at copying `cwd`, we asked who actually owns the workspace. The answer
was already in the plugin: the operator configures it when the hosted coding
agent is created.

Claude Code now starts from that configured workspace when `cwd` is omitted.
An explicit subdirectory still goes through the same resolution and containment
checks; missing paths, files, symlink escapes, and directories outside the
workspace still fail closed. The lesson was small but useful: do not ask a model
to restate authority that the system already owns. Give it a safe default and
keep the boundary in code.
