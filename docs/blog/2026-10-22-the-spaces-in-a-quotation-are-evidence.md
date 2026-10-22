# The spaces in a quotation are evidence

Candidate under #2635; not released.

A quotation promises more than a similar-looking character sequence. REM's
comparison removed every space before checking a quote against its cited source.
That made “now here” and “nowhere” look identical. Normalizing a wrapped mail
should not change where its words begin and end.

The first repair tried strict word edges as well. Real saved evidence exposed
why that was insufficient. Two valid quotations sat next to headings or forwarded
mail headers that an older provider rendering had concatenated. A strict matcher
called them wrong. Guessing separators from capitalization would hide that
uncertainty with another transformation.

The candidate separates two judgments. Changed word separation is a literal
mismatch. An intact literal fragment with ambiguous outer word edges is an
unresolved source question. It carries the exact cited source identity and a
bounded piece of retained rendering into the source audit. The original may show
a negation or condition the fragment omits; it may also have lost a boundary
while becoming text. Neither case justifies treating character matching as
verification.

The unresolved state survives without an auditor. It also survives a global
PASS: that response has no per-quote evidence resolving the boundary. Existing
insufficient-audit policy keeps the candidate inspectable without describing its
factual quality as passed. No valid quote is erased solely because an old
rendering lost a separator.

The full regression exposed two session-summary failures: those callers still
removed spaces before invoking the new matcher. Both now use spacing-preserving
comparison against retained native typed-user input, where whole-word boundaries
can be checked directly. Summary creation and saved-summary display both validate
the quote and its message time; raw attachments stay intact.

A read-only inventory found 122 cited quotations across 49 pages in a 587-page
notebook. Sixty-three had complete available originals for this check; 59 did
not. The final candidate retained the two legacy-layout cases as unresolved
warnings. Two other literal mismatches were already flagged by the prior rule;
they are not newly discovered successes of this patch. Every page hash remained
unchanged. This does not establish every quote's semantic fidelity, model
behavior or current native reader quality.
