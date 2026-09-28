# The wall that updates itself, and the sentence that does not

Two days ago the README got the website's logo wall, and we were pleased
with one decision in particular. The README does not hold a copy of the
wall. It shows `https://www.connectonion.com/connections.svg`, which the site
draws from the same list as its hero. Add a connection to that list and the
README picture changes by itself. We had just watched a CLI banner go stale
because it lived where nobody looked, and a second copy of the wall would
have gone the same way.

Then two connections shipped in the same week. `co onenote` gives an agent
your OneNote notebooks: list the sections, read a page as text, write a new
page. `co search` and `co fetch` give it the web from bash, the same two
tools `co ai` carries. Both are in 1.8.9. Neither was on the wall. The wall
could not know about them, because the only thing that updates it is someone
remembering to edit the list. "Updates itself" was only ever true for the
drawing.

Adding them was the easy part. Both fill a row that had five tiles out of
six, so the image stays the same height. There were two smaller surprises.

The first was the OneNote mark. Every other brand on the wall comes from an
open icon set, most of them from Simple Icons, and Simple Icons has
withdrawn its Microsoft product marks. The OneNote entry is still in the
data but hidden. Microsoft's own multicolour icon falls under Microsoft's
brand rules, and those rules are not written for a wall of monochrome chips.
The wall already had an answer, because the Outlook and Teams tiles never
used Microsoft's own artwork. They use Phosphor's glyphs in the brand colour.
OneNote now does the same, with Material Design Icons' rendition (Apache-2.0)
in OneNote purple, and the source and licence are written next to the path in
`marks.ts`. That way the next person does not have to find all this out
again.

The second surprise was in this repository, and it is why this post exists.
The README's `<img>` has alt text, and the alt text lists every connection
in words: "Gmail, Outlook, Google Calendar, Meet and Teams; WhatsApp,
Telegram…". It is the only version of the wall a screen reader hears, and
the only one a crawler or an agent reading the raw Markdown gets. The picture
at the other end of the URL was about to say 43 connections. The sentence
still said 41, and nothing would ever have made it change. It was the same
kind of second copy we had avoided, sitting inside the tag that pointed away
from it.

So the fix is one line. The alt text now names OneNote with the other
Microsoft and Google services and web search at the end of the browser
group, in the same order as the picture. The rule we take from it is
narrower than "never duplicate". A generated image removes the copy you can
see. The copies you cannot see are still yours to keep up to date: alt text,
the page's meta description, the one-liner in `llms.txt`. When a connection
lands, the list in `facts.ts` is the first edit. The alt text in this README
is the second.
