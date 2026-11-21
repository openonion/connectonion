---
description: Decision pages now check stored speaker evidence, and one empty slice yields to the next instead of ending the run.
tags: [REM, Decisions, Evidence]
draft: true
---

# A captured quote still needs a speaker

A decision page could copy its captured quotation perfectly and still have no
evidence that the owner said it. Matching the intermediate page proved continuity;
it did not prove authorship.

The abstract stage continues to read notebook pages. A local check at promotion
now looks up the cited original: typed session input or an archived mail body and
sender. It refuses another speaker's words and quotations contradicted by complete
originals. It does not ask the model to infer a speaker from tone.

There are limits. The original may be missing, its text truncated, or its citation
may identify a file or web page rather than a personal message. A mail sender did
not necessarily write the older thread quoted below their reply. Those pages use
the notebook's existing Uncertainties section to say `Speaker unverified.` Stored
owner input also cannot prove whether the person composed or pasted the text.

We considered trusting the capture, letting the abstract model investigate raw
sources, and refusing every unresolved speaker. The first repeats the attribution
gap. The second changes the stage's input boundary. The third discards unresolved
evidence even when the reader could use it with an explicit uncertainty. A local,
deterministic check keeps the boundary and makes its limits visible.

Refusal should not block unrelated work. One empty round now counts as a failed
slice and yields to the next. Two empty rounds in a row end that pass. Successful
slices after a failed gap are saved separately, so retrying the gap does not repeat
the later work. The existing three-failure rule still releases a repeatedly failing
slice with its reason recorded.

This is a draft design record. The implementation is checked with invented
fixtures; a real model run is still required before making release claims.
