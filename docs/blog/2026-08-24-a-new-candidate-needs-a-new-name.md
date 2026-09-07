---
title: "A new candidate needs a new name"
date: 2026-08-24
author: ConnectOnion Team
---

The new Work Room candidate had finally passed. Claude returned from the long
coding run, the parent composer came back, reconnect did not resend anything,
and twenty-two screenshots survived the evidence review. I made a clean
environment, built the merge commit, and typed the command that should have
confirmed the next candidate.

It answered `co 1.7.0rc3`.

For a moment this looked like a failed build. It was more mundane and more
dangerous: the build had done exactly what the source asked. The branch had
moved through several release-blocking fixes, but its project metadata still
used the name of the already-published candidate. The commit and checksum let
us distinguish the local files, yet a package index cannot honestly accept two
different artifacts under one immutable version.

We stopped before publication and followed the version through every place a
user or tool could learn it. Updating the project metadata exposed the runtime
literal. Updating both exposed the lock. The consistency test then caught the
release guide and the separate documentation site. Each failure was useful: it
named another place where a tester could have installed one candidate while
believing they had another.

The repair was deliberately boring. We gave the accepted branch the rc4 name
in every source, rebuilt it, and made the exact-artifact gate start again from
that identity. No behavior was smuggled into the version change.

That small interruption sharpened the release rule. A candidate name is not a
progress label; it is a promise that a report, manifest, rollback command, and
published byte all refer to the same thing. Once the code behind a published
candidate changes, honesty requires a new name and a new unchanged window.
