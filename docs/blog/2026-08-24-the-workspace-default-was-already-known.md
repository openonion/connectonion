---
title: "The workspace default was already known"
date: 2026-08-24
author: ConnectOnion Team
---

A hosted coding agent already has a workspace chosen by its operator. Requiring
the model to repeat that directory on every Claude Code call added no authority;
it only created another way for a valid delegation to fail.

Claude Code calls now default to the configured workspace when `cwd` is omitted.
Explicit subdirectories still work, and the existing containment checks still
reject missing paths, files, symlink escapes, and any directory outside that
workspace. The default removes accidental ceremony without widening access.
