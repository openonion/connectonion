---
title: "Headless does not mean unconfigured"
date: 2026-08-25
author: ConnectOnion Team
---

A launchd job upgraded from 1.6 to the 1.7 release candidate and stopped on its
first action. The command was `co browser status`, already covered by the
operator's standing `Bash(co *)` permission, but Auto classified every command
outside its small verification list as requiring a live approval. With stdin
closed there was no dialog, so the safe failure became a complete outage for
deliberately unattended agents.

Allowing every historical config match would have restored the job by weakening
the newer boundary. In particular, the shipped `Bash(co *)` pattern is much
broader than its old “safe CLI” description: taken literally, it can include
deployment, email, account, and payment actions. Treating that wildcard as an
unlimited unattended grant would turn compatibility into escalation.

Headless Auto now distinguishes “nobody is present” from “nobody configured
this.” An operator-authored command rule can satisfy an ordinary command that
would otherwise ask. The shipped broad `co` compatibility rule is accepted only
for `co status` and `co browser ...`, which restores the existing cron/browser
workflow. Publication and deployment keep their stronger policy verdict, while
other framework effects such as email remain denied unless the operator writes
a narrower, deliberate rule or chooses bounded Full access for the whole task.

Regression coverage runs the exact no-IO approval path for one command and a
command chain. It also proves the same broad rule cannot silently authorize
`co deploy`, `co publish`, or `co email send`. The surrounding parser,
configuration, approval, and Auto-policy suites pass together.

This preserves a security tradeoff: a sufficiently narrow operator permission
is authority, even without a person online. We would revisit the mechanism when
permissions carry first-class effect classes instead of deriving intent from
command text and legacy patterns.
