# Navigation is not a citation map

Candidate repair under #2197; not released.

Four references in a saved REM notebook pointed to pages the reader did not contain.
The body had a missing-link style, but its tooltip was a literal translation call
inside HTML. The Related area just kept the label. Neither a user on a phone nor
someone reading the label alone had a reliable explanation of what could open.

Fixing the label led to a wider inconsistency. A link with an encoded filename or
a section fragment could navigate differently from the relationship projection.
A merge could leave an old path that the reader no longer recognized. The existing
merge table was the right authority for navigation; inventing a relationship from
a similar name was not.

The first implementation made the general record lookup follow aliases. That
looked convenient until we traced a historical claim through it. Source number 1
on an archived page is not necessarily source number 1 on its destination. A merge
says where a page went; it does not supply a citation-number mapping. New failing
contracts made that risk concrete before publication.

The candidate now keeps exact data lookup separate from page navigation. Ordinary
page and section links can reach the recorded destination, with their original
labels and context. Old numbered-source anchors stay unavailable unless a mapping
exists. Missing links visibly say Page unavailable, including encoded extensions.
Shared snapshots contain only aliases already referenced by their notes, without
exposing the rest of the merge history or its reasons.

The tradeoff is deliberate: an old source link may remain unavailable even when
its page has a destination. Showing no source is more honest than silently opening
a different one. A durable source-number mapping could change that decision.

Offline tests check these boundaries and keep the original excerpt, privacy flag
and source IDs with their origin. They do not establish phone layout, focus,
contrast, current visual quality or correct source claims across every notebook
page. Those acceptance steps still stand; no new preview is published by this patch.
