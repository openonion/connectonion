# A Work Room Has One Writer

A coding Work Room lives in three repositories. That makes it easy to mistake
three copies of a small JSON object for three owners of the product.

They are not. The provider adapter in ConnectOnion is the only writer of live
state. It decides which activity terms are safe to surface, keeps native
commands and paths out of the presentation envelope, and assigns the revision
that says whether an update is newer than the one already on screen.

The React package is deliberately less ambitious. It validates that envelope,
normalizes it into client state, and refuses malformed or stale authority. It
does not infer a successful command, invent a thumbnail, or turn a missing
revision into an approval. O Chat is less ambitious again: it renders the
bounded state, gives the reader a focused Work Room, and sends a Stop or
approval decision back with the identifiers that Core supplied.

That division matters most when a run is long. A provider may report activity,
show a real workspace image, pause for an approval, and then finish. If each
reader tried to reconstruct those transitions from a transcript, the card
could show stale evidence or offer authority for the wrong invocation. A UI
that looks helpful but permits the wrong action is worse than an incomplete
one.

The practical rule is: one writer, independently defensive readers. The Core
event module now names the React normalizer and O Chat Work Room that consume
its bounded contract; the corresponding frontend headers point back to this
authority. A future change to safe vocabulary, artifact limits, revision
semantics, Stop acknowledgement, or approval identity therefore has an
explicit route through all three layers.

The evidence is intentionally cross-layer. Core unit tests validate the event
shape and revision behavior. React tests validate normalization. O Chat's
production-browser acceptance run drives an eight-step native coding task,
checks the focused card and Work Room at phone width, and verifies approval and
scoped Stop behavior. A thumbnail is accepted only when the provider supplied
real native image evidence; an absent image leaves the progress view honest.

This is not an abstraction for its own sake. It is the smallest boundary that
lets a long-running agent remain visible without making the browser a second
agent runtime.
