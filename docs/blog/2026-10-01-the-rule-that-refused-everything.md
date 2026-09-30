# The rule that refused everything

In 1.9.0a5 we added a sensible rule: a page that comes back from an
investigation must not still say "Unknown — not investigated yet" in its
sections. The real-data run had found project pages that spent 900 thousand
tokens and left half their sections with that placeholder, reading as if nobody
had looked.

The same afternoon, the acceptance run on a copy of the owner's notebook ran
one night of maintenance. It spent 290 thousand tokens and changed zero pages.
Every page it touched was refused.

Maintenance is the pass that keeps pages current from new material. Most pages
in a notebook have never been investigated, so most pages still carry the
placeholder in their empty sections, by design: it tells the reader that nobody
has looked yet. Maintenance adds a line from a new mail and leaves the rest. The
new rule saw the placeholder still there and refused the page. The rule was
right about investigation and wrong about everything else, and the tests only
covered investigation.

The same run found the second bug that could not wait: one Gmail message whose
date had no timezone crashed the gather for `co rem investigate me`, so a new
user's first page could not be written at all.

Both are fixed in 1.9.0a6, which ships with nothing else so that it can ship
today. The placeholder rule now applies only to a page's own investigation. A
date with no timezone is read as UTC, and a mail whose date cannot be read is
skipped instead of ending the run.

The lesson: a rule is also a statement about every path it runs on. When you
add one, test it on the paths it was not written for, because those are the
paths it will quietly break.
