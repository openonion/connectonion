---
title: The index kept the citations
date: 2026-10-26
description: When evidence is summarized into an index, the originals behind it still have to be reachable.
---

A REM project page came back from its audit with 31 missing citations before
any fact was checked. It looked as if the agent had cited sources that did
not exist. At least thirteen of them existed and could be resolved by hand.

The page had simply been too well researched. Its evidence overflowed one
turn, so the investigation folded the items into an index and let the agent
open the files itself. The agent did exactly that and cited what it read. But
the code that keeps cited originals, and the audit that checks them, only knew
how to look inside a different wrapper, one written when stage routing is on.
With routing off, the better-researched the page, the less of its evidence
survived.

The lesson was about blame as much as plumbing. Both wrappers now carry their
originals, and one function opens either kind. And when a citation's original
was handed over but nothing readable remains, the audit now says "unverified"
and counts it, instead of accusing the author of an unsupported claim. A
missing excerpt is our gap, not the writer's.

A regression forces the index path with invented sessions and fails on the old
code. This change is on the path to the next 1.9.3 release candidate.
