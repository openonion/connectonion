# Back on its own line

The line that tells a reader how to get back to the parent help page was added
to every `co` page yesterday. It sat on the same line as the examples, joined
with a bar. In a 96-column terminal the joined line wrapped, and it wrapped
in the worst place: `Back: co trust` at the end of one line and `--help` at
the start of the next. An agent copying the route would copy half of it.

The fix is one character in one function: the way back now starts its own
paragraph, so the examples can wrap however they need to without touching it.
Because the line is generated from the command tree rather than written into
each page, one change fixed all 290 pages that carry it.
