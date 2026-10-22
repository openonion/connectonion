# A correction was not a completed page

Candidate implementation; not published in rc8.

A source audit left us with a simple question: if a reader corrects a REM page,
what proves that the page actually considered the correction? Saving the assertion
was easy to observe. Consuming it was less clear. The ordinary maintenance path
could decide a page had already read its material, even though the reader's new
correction arrived after that decision.

We reproduced that boundary with synthetic records. Yesterday's no-change cooldown
could hide today's correction. Another test answered a question about two pages;
one accepted the input, the other refused it. A batch-level consumed flag could not
describe those two outcomes. Giving every page the entire packet also meant one
person's correction could enter another person's turn.

The repair follows the original event and each declared target. Only accepted
processing finishes a target, including a turn that has read the assertion and
accepts no change. Refusal and budget deferral leave it pending. The packet stays
raw and specific to the page; compressing a view does not manufacture another event.

Independent review found a less visible trap: the daily retry could succeed without
writing the new receipt. The next sync would pay again. Sharing acceptance between
the two paths closed that gap. Recovery needed another distinction. A prepared
write is not a saved page. After interruption, both the saved postimage and the
retained feedback revision must match before the native runner's turn is acknowledged.

Old history sets a limit. If a consumed compressed summary has been overwritten,
we cannot reliably recover its membership. Those records now wait with an explicit
reason rather than becoming either invented successes or automatic replays. That
leaves reconciliation work, but makes the uncertainty visible.

These are source and synthetic execution checks. They do not show that a model made
a useful correction to a real page, that every claim is true, or that REM's reader
has reached its design acceptance line. A processing receipt answers a narrower
question: which version of which input reached an accepted turn on this page?
