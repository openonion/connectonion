---
title: "The tool finished but the turn did not"
date: 2026-08-24
author: ConnectOnion Team
---

Our release gate watched Claude Code finish a real project, return control to
the parent Agent, and then disappear behind a model request that never returned.
The files were correct. The provider Work Room had a completed result. The
outer composer still could not come back because the parent turn had no
terminal outcome.

We already handled a nearby failure: a model that returned an empty answer
after successful tool work received one constrained recovery request. This was
different. The model call itself remained in flight, so the empty-answer logic
never ran.

Native provider work now starts a bounded settlement phase. Every later parent
model call in that phase has a hard limit. The first timeout abandons only that
call and asks once for a concise answer grounded in the committed tool results.
If the retry also times out, the turn ends with an explicit error. A late model
response cannot enter history or claim success after the turn has settled.

The distinction matters for remote coding clients. A provider finishing its
work is not the same as the parent turn finishing. Once a long-running child
returns, the parent still owes the user one bounded outcome: continue, ask,
complete, or fail. "Still thinking" forever is not a fifth outcome.
