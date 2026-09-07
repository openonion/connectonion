---
title: "The snapshot that arrived thirty-nine times"
date: 2026-08-24
author: ConnectOnion Team
---

Claude Code had finished. The stack compiled, the tests passed, and the Work
Room showed Completed. Then the parent agent asked to list the new project so it
could verify the result. The browser should have shown one small approval card.
Instead, the input disappeared and five minutes passed in silence.

The durable session told a different story from the screen. It contained the
model's verification call, its action summary, and the pending approval. The
agent was waiting honestly; the browser simply had not reached the question.
That distinction sent us away from provider permissions and toward the queue
between a committed tool transaction and its client.

Long-running coding tools publish activity while they work, but keep their
canonical state private until the transaction commits. Every activity entry had
also captured a complete session snapshot. When Claude returned, thirty-nine
trace entries committed in order—and each brought another, mostly superseded,
snapshot with it. In this run the newest snapshot was about 475 KB. The tiny
approval was standing behind roughly 17.7 MiB of old versions of the same
conversation.

The fix follows the meaning of an atomic commit. Every trace entry still
survives in order, because each describes something that happened. Session
snapshots are different: before the transaction becomes visible, a newer one
fully replaces the older one. The transaction now retains only the latest
snapshot and publishes it after its traces.

The lesson is not merely to send fewer bytes. Event history and state snapshots
have different identities. History accumulates; snapshots supersede. Treating
both as append-only can make a truthful approval look like a broken client—and
the longer and more useful the Work Room conversation becomes, the worse that
mistake gets.
