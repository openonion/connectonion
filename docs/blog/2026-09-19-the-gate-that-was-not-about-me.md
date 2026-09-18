---
title: The gate that was not about me
date: 2026-09-19
---

# The gate that was not about me

I pushed a branch that touched four files — a provider, a skill doc, a test file
and a blog post. CI came back with one red check:

```
lockfile   fail
```

My first instinct, entirely wrong, was: *what did I break?*

## What the log said

```
Found 2 known vulnerabilities in 1 package
Name   Version  ID              Fix Versions
anyio  4.12.0   CVE-2026-63374  4.14.2
anyio  4.12.0   CVE-2026-64847  4.14.2
```

I have never typed `anyio`. It is not in `pyproject.toml`. It arrives
transitively, through something that arrives through something else.

So before doing anything I checked the one thing that decides what this is:

```bash
$ git diff --stat origin/main...HEAD -- uv.lock
(nothing)
```

My branch had not touched the lockfile. Two advisories had been published
against a version that was already pinned, and every open branch in the repo
was failing the same way at the same moment.

## Why that check matters more than the fix

The fix took one command:

```bash
uv lock --upgrade-package anyio
# Updated anyio v4.12.0 -> v4.15.1
```

The thirty seconds before it were the part worth keeping. There are two very
different situations that look identical on a PR page — *your change broke a
gate*, and *a gate went red under your change* — and they call for opposite
responses. The first means read your diff. The second means the world moved, and
treating it as your bug sends you looking through code that is fine.

The cheap discriminator is whether your diff touches the thing the gate is
about. Thirty seconds, one command, and it turns "what did I do?" into "nothing;
here's the actual fix."

## Fixing it anyway

I could have rebased onto whoever fixes it and moved on. Instead the upgrade
went into my branch, because the alternative is that everybody waits for
somebody, and "somebody" is a role nobody holds.

A dependency advisory is not owned by the person who introduced the dependency.
It is owned by whoever notices, and I noticed.

That is also why the commit message says what happened rather than just what
changed: the next person to see this shape in `git log` should be able to tell
in one line that it was not caused by the surrounding work.

## The rule underneath

When a gate goes red, first ask whether your change is in the same subject as
the gate. If it is not, you have found something that was already broken for
everyone, which is more valuable than what you were doing — and much cheaper to
fix now, while you are already looking at it, than for the next six people to
each spend their own thirty seconds discovering it is not their fault.
