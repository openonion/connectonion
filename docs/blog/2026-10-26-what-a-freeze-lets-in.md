---
title: What a freeze lets in
date: 2026-10-26
description: rc24 froze 1.9.3. The same afternoon, the first change came through the door, and it had to show it was a blocker.
---

We froze the 1.9.3 line at rc24 with a simple rule: after this, a change gets
in only if 1.9.3 cannot ship without it.

The first test of that rule came the same afternoon. A Lark listener reported
`listening`, kept a live log, and still let about half of the direct messages
to its bot disappear. Lark had been handing those events to another client
connected with the same app. The recovery that should have filled the gap
failed on its first conversation every minute, for weeks.

That passes the rule. A listener that loses people's messages and looks
healthy while it does so cannot be called stable. So rc25 is rc24 plus that
fix, and nothing else. Recovery now runs only at start and after a reconnect,
with a fixed budget of history calls. A conversation Lark rejects is skipped
instead of ending the run, and `co lark check` reports a message that went to
another client.

Everything else that arrived after rc24 waits for the next line. The freeze is
only worth something if the candidate we test is the release we ship.
