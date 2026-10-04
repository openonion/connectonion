---
description: The source link worked, but four of five written REM pages hid part of it below a phone's first screen. A small layout change moved evidence beside the claim it supports.
tags: [REM, Design, Evidence]
---

# The source link was one scroll too late

The sources were there. On a laptop, we could open every displayed numbered
source on three written REM pages. On a phone, the links also worked. But in a
375×812 review, the `View sources` action on four of five written page types
started partly or wholly below the first screen. A reader looking at a claim
could easily miss the path to its evidence.

It was tempting to call this a small spacing problem. The link already had a
44-pixel touch area, and scrolling one finger-width made it available. Yet
the moment matters: the page introduces a person, project, or skill with a
useful lead. That is when a reader may want to check why the page says it.
Putting the link after the whole lead card meant the answer arrived too late.

We tried moving the action into the dark lead card, just after its statement
and before any longer context. That brought four of the five source actions
fully into the phone viewport. The Owner page remained a few pixels short:
its open-thread preview above the lead needed the space. Shrinking the lead
text would have made the claim harder to judge. Instead we tightened the
small-screen gaps around the back link, header, and lead card, keeping their
content and the permanently visible Full memory section.

In the protected five-page recheck, the Owner source action landed at
y≈754–798 on a 375×812 phone. The other four ended between y≈694 and y≈760.
Each action was 44 pixels high, navigated to the Sources section, and caused
no horizontal overflow or page error. The same five pages were opened again
at 1440×900. This is a sampled layout result, not a review of every notebook
page or a fresh audit of each claim.

A source link can be technically present and still arrive after the reader's
decision point. For evidence-backed pages, the first useful claim and its
verification path should travel together. The [preview notes](/releases/1.9.0a35)
record the exact scope and recheck limits.
