# One email is one observation

A Person page can know something useful without knowing a pattern. In one
review, REM had a user-written reply in its sources but left `How the user
writes to them` Unknown. That was cautious about style and cadence, yet it
hid a concrete clue: what the user actually said to this person. A dated,
cited example could show the clue without claiming that this is how the user
usually writes.

We changed the page instructions to make that distinction. One message gives
one observed note. Several can support a pattern. Cadence needs repeated
dates. Sparse mail cannot settle every open obligation or prove the next
contact. The latest date in the checked messages is only the latest contact
we observed there.

The small test was less reassuring than the first result. We ran the same
invented two-email case repeatedly. Every version kept the one-off note and
left cadence Unknown, but some also said that a pilot required delivery,
that the user was a contractual counterparty, or that a thank-you accepted an
agreement. Those statements sounded plausible beside clickable citations.
Opening the two originals showed that they were not there. An independent
role-based AI founder and UI review caught these claims on the actual desktop
and phone reader. The pre-promotion source audit, still in a separate draft,
also passed one of those faulty pages before we added more exact checks.

We tried the existing summary mode on the same tiny case. One agent run used
625,093 total model tokens, much of it in repeated tool reads. Three summary
runs used about 37,000–41,000 each. That reduction matters for a first run,
but two summary pages made new source mistakes. A shorter run is not a better
memory if it changes what the evidence means. We also found a direct prompt
conflict: summary mode told every page to list source IDs without dates, while
Person pages require dated sources. The summary instruction now defers to the
page's own source format.

This change remains a draft. The one-off example is useful, and the source
format conflict is fixed, but the repeated trial did not establish reliable
Person claims. The next release check is concrete: compare each consequential
sentence with the original next to its citation, confirm the source audit
rejects the known false claims, and then measure a new, bounded real sample.
Only then should the page be presented as a trustworthy memory rather than a
well-formatted guess.
