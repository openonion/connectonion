---
title: "The last change is the name"
date: 2026-08-24
author: ConnectOnion Team
---

RC10 had already done the hard work. A clean public install had opened real
Codex and Claude Code Work Rooms, driven a browser download, compiled C, C++,
and Rust, stopped provider work, narrowed permissions, restarted the Host, and
reconnected without sending the prompt twice. The code had earned release.

But `pip install connectonion` still selected 1.6.12. That was correct. A
candidate can pass every test and still not be the version ordinary users
receive. The last release change was not another behavior fix; it was changing
the promise attached to those already-reviewed sources.

That distinction matters because “unchanged promotion” cannot mean identical
archive bytes. The version inside a Stable wheel must be `1.7.0`, its package
classifier must say Production/Stable, and the public docs must point normal
installs at it. Those metadata changes necessarily produce new archives. What
stays unchanged is the product source and its behavior.

The first local promotion check caught both sides of that boundary. It rejected
the old Beta classifier, then rejected the documentation site while it still
advertised 1.6.12. We changed the classifier, staged the docs channel beside
the package, and reran the release contract: 59 version, provenance, workflow,
history, and checklist tests passed. The 1.7.0 wheel and source archive built,
and `twine check` accepted both.

The release remains ordered. The stable React reader publishes first. O Chat
then consumes that public reader and completes its final visual declaration.
Only after that frontend head merges does this metadata commit receive the
`v1.7.0` tag. The protected workflow builds once, publishes through Trusted
Publishing, downloads what PyPI actually serves, and attaches those exact bytes
to the GitHub release. Documentation switches its Stable channel only after
the package exists.

This is slower than changing a dropdown to “latest,” but it gives every name a
referent. RC10 names the artifact that survived acceptance. 1.7.0 names the
same reviewed product source after the coordinated clients and public channels
are ready to make that promise to everyone.
