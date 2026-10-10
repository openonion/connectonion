---
description: co rem 1.9.2b1: an investigation that was only ever allowed to add, and what changed when it was allowed to delete.
tags: [REM, Writing]
---

# The page that could only grow

The 1.9.1 first run read a cofounder's mail in rounds and wrote him a page
over sixteen thousand characters long. Most of it was right. Then you reached the
Uncertainties section: sixteen sentences, each saying some outcome was "not
established". Reading it felt like reading an investigator's notebook rather
than their report.

The model was not padding. It was obeying. Every round was told to keep what
earlier rounds had established; the final round was told to keep every thread;
the edit prompt said to leave every supported line alone. Nothing anywhere said
it could take something out. So each round added its doubts, and none was ever
allowed to resolve one by deleting it.

The agent doing this work is a coding agent. On code it adds, changes and
deletes without being asked twice. So the beta tells it to treat the page the
same way: delete what newer mail supersedes, what the page says twice, and
doubts the evidence settles. The last pass is an editor's pass, with room for
five uncertainties that would change what you do next.

Good writing has always been mostly deletion. It turns out a model needs to be
told it is allowed to do it.
