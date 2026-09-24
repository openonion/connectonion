# A scrollable code block still widened the whole notebook

The Wiki reader looked comfortable on a desktop. In a 375px Chrome viewport,
an ASCII diagram widened the page to 730px. The code block already had
`overflow-x: auto`. That rule could not help while its grid item refused to
shrink.

We isolated the inputs before changing the layout. A six-column table produced
a 590px page; a long unbroken identifier produced a 1399px page. These were
synthetic notes, with no private notebook content. Giving the main grid item
`min-width: 0`, containing table scrolling, and allowing inline tokens to wrap
kept all three pages at 375px. The diagrams retained their alignment. Measuring
the whole page had exposed a constraint that inspecting the code block alone
had missed.

The next defect was harder to see in a screenshot. Lines beginning with
`Sources:` and `Related:` disappeared from a code example and reappeared as
page metadata. The surrounding text still looked orderly. Extracting trailers
before rendering Markdown had treated literal examples as instructions about
the page. Tracking fence type and length fixed the top-level case, but a new
regression with a fence nested in a list still failed: the extractor recognized
only shallow indentation. Protecting those deeper fences made the exact-text
assertion pass, including blank lines.

That failure changed what we needed to check. A block could fit on the screen
and still show the wrong contents. The layout examples needed an assertion on
the page's total width; the code examples needed a comparison with the original
text. Running the same synthetic inputs again gave us both: a 375px page and
literal source lines still inside the code block. The reader remained a single
offline file, with no new Markdown dependency.

The lesson was to check each transformation against what it must preserve.
Layout may move a diagram into a scrolling region while keeping its characters
aligned. Metadata extraction must leave an example's words alone. Those checks
are now part of the reader's focused browser tests. They establish the behavior
of these fixtures in Chrome; the small Markdown parser and untested browsers
still leave boundaries to investigate.
