# A scrollable code block still widened the whole notebook

The Wiki reader looked comfortable on a desktop. In a 375px Chrome viewport,
its first screen was mostly categories, and an ASCII diagram widened the page
to 730px. The code block already had `overflow-x: auto`. That rule could not
help while its grid item refused to shrink.

We isolated the inputs before changing the layout. A six-column table produced
a 590px page; a long unbroken identifier produced a 1399px page. These were
synthetic notes, with no private notebook content. Giving the main grid item
`min-width: 0`, containing table scrolling, and allowing inline tokens to wrap
kept all three pages at 375px. The diagrams retained their alignment. A compact
category toggle brought the start of mobile content from about 675px to 164px.
The existing typography and colors stayed in place.

The more consequential defect appeared inside a code example. Lines beginning
with `Sources:` and `Related:` disappeared from the block and reappeared as
page metadata. Extracting trailers before rendering Markdown had treated
literal examples as instructions about the page. Tracking fence type and length
fixed the top-level case, but a new regression with a fence nested in a list
still failed: the extractor recognized only shallow indentation. Protecting
those deeper fences made the exact-text assertion pass, including blank lines.

The same browser tests now exercise nested lists, tilde fences, local table
and code scrolling, and keyboard navigation. Heading tests check the target's
position after navigation: the old renderer had scrolled to a section and then
immediately reset the page to the top. Cross-page links also needed to retain
the heading fragment. Search tests verify that opening a result clears the
query field and Back restores it.

Fourteen focused tests passed on the PR branch, including Chrome at 375, 768,
and 1440 pixels. The pages made no HTTP(S) requests. This keeps the reader a
single offline file without adding a Markdown dependency. The parser is still
a small subset, and these checks do not establish Safari, Firefox, or physical
phone support. The useful change is narrower: the formats covered by these
fixtures now remain readable and preserve the code the author actually wrote.
