# Links that looked like links

The owner opened a person page in the reader, clicked a link, and nothing
happened. Then another. "Some links don't jump," they said, and the obvious
suspect was the pages. Seven hundred pages written by a model, linking to each
other by relative path, are bound to have broken ones.

So we counted. Of 861 page-to-page links in the owner's notebook, 855 pointed
at a file that exists. The six that didn't were all on organisation pages,
linking to people that `tidy` had since archived as services: Airbnb, Apple
Support, UNSW Alumni. That was real, but six links don't make someone say
"links don't work".

The rest of the answer was what the eye sees as a link. A good person page
ends nearly every line with `[2]` or `[7][8]`. On Jiexuan Deng's page there
are 58 of them. They are bracketed, numbered, and sit where a footnote mark
sits, and the reader drew them as plain text. Every one of them was a
click that went nowhere. The Sources list they point to was plain text too.
Its entries are written as `- [2] outlook:a8d321ddba85 — observed 2026-09-23`,
and the reader expected a different shape, so it showed the whole list as one
block. The broken links had a quieter version of the same problem. The reader
dropped the link and printed the bare name, so a page that was gone looked
like a link that wasn't working.

Now a citation is a link: `[2]` jumps to entry 2 under Sources, scrolls it
into view and highlights it. A link to a page that is no longer in the notebook
is drawn struck through, with a note saying so. `tidy`, which runs before every
sync, now unlinks any page it finds pointing into the archive, so the six on
the owner's notebook go at the next sync. A page folded into another is
relinked to where it went.

What is still not good is what the jump lands on. `outlook:a8d321ddba85` is a
truthful citation and a useless one. Making it say who wrote what, and when, is
the next change.
