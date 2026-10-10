# The date was in the map

Quinn's page said their last contact was September 16. A few inches lower,
the expanded memory said **Last contact — not found**. Both lines were produced
from the same snapshot. The first came from mail metadata collected while
mapping people; the second asked whether Quinn's written investigation had
found the fact. Quinn had not been investigated yet.

That distinction matters to someone deciding whether to trust a memory. The
date is useful, but the page must say where it came from. It now calls it
**Last contact in map** in the short view and marks the People table date
`· map`. The full note still says the fact is absent there, while pointing
back to the map date. If the map has no date either, the page shows the ordinary
unknown state.

The first browser test we wrote changed Quinn's date in JavaScript before
looking at the page. It passed while the untouched page still contradicted
itself: the short view had no date at all. The failing normal case made us
follow the map's date through the reader, rather than just change the missing
fact's words.

On a 375-pixel screen, the first design repeated the same date three times
and put the copyable investigation command below the first screen. We kept
one sourced date, moved the command up, and made its button large enough to
tap. The browser checks now open the untouched mapped page at desktop and
phone widths, inspect the expanded note and People row, remove the map date
to check the unknown state, and compare an investigated person whose facts
should keep their usual labels.

The map can tell you when a thread last appeared. It cannot pretend that a
person's story has been read. The interface needs to carry that difference
all the way to the next action.
