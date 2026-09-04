---
title: "A patch must move forward"
date: 2026-08-25
author: ConnectOnion Team
---

We were preparing 1.7 Stable when an ancestry audit found something backwards:
the public 1.6.12 maintenance release contained fixes that RC10 did not. The
newest test version was newer by number and older in several behaviours.

Merging the whole stable branch into the preview looked like the obvious fix.
It was also the dangerous one. A maintenance branch carries its own version,
channel metadata, release notes, and assumptions about an older architecture.
A blind merge can overwrite deliberate preview changes while making the graph
look reassuringly connected.

We instead reviewed every 1.6.12 change, forwarded the applicable product,
test, documentation, migration, and operational commits into 1.7 and 1.8, and
cut RC11. That repaired this release, but a one-time audit would allow the same
failure next month.

The release contract now gives every stable patch a durable forward-integration
ledger. Before a patch PR merges, it links a separate open issue labelled
`forward-port-required`. That issue names every active higher line and records
either the focused PR carrying each fix or a maintainer-reviewed reason the fix
does not apply. It closes only after those PRs merge and pass CI.

The second half of the rule is mechanical: while any such ledger is open, the
protected workflow refuses to publish a newer preview, RC, or next-minor Stable.
The patch itself may still ship quickly to users who need it. An immutable tag
that is already public may also be retried for recovery. What cannot happen is
moving the preview channel forward while knowingly leaving a stable fix behind.

This adds coordination work to every patch, but it puts that cost where it is
visible. We would revisit the mechanism if release lines can declare and verify
machine-readable patch equivalence directly. Until then, a linked issue, focused
PRs, and a hard release gate are simpler than discovering at Stable promotion
that the newest candidate forgot yesterday's repair.
