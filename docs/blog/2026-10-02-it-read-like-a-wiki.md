# It read like a wiki

For a month co rem was judged by what it wrote: facts found, citations that
resolved, tokens spent. Then the owner opened the reader, the page you get from
`co rem open`, and said what a person says: it reads like a wiki, and it looks
generic. People should open like a CRM. Facts should be cards you can scan. "I
can't find Ody's phone number at a glance."

We asked for an expert critique before touching anything, and it was blunt.
The home was a table of contents, with organisations in alphabetical order, so
the first thing you saw was a domain beginning with "a". On a person page, the
one thread you owed sat two screens down, under eight contact fields. A phone
number that was not found did not say so; the row simply was not there. People
was a feed twenty-eight thousand pixels tall. Citation runs like
[141][142][143][144][145] sat in the prose like noise.

Every one of those was true and none of them was about colour. They were
about order: the page answered "what is this" when the reader came back to
ask "what do I owe, and to whom".

So the redesign starts from that question. The home opens on the night, what
the notebook read and rewrote while you slept, and then on what is waiting on
you, oldest first. People is a sheet you can sort by last contact or filter to
"yours to answer". A person page opens on one line of balance, "You owe Mara
the signed addendum — 9 days", then the facts as a panel where a missing phone
says "not found". The typography, the two themes and the terminal layout came
after, and were easier, because the content already knew what it was for.

The lesson: a tool that writes for you is judged at the moment you read, and
the first question a returning reader asks is the one to put first.

The first public preview of this redesign is 1.9.0a10. The a9 tag was held by
the stable-patch forward-port gate; by the time that work reached main, the
page writer could also produce the cited Facts and Insight the reader was
designed to show. The runner now loads each stage Skill once, leaving the
page-specific rules as additions instead of repeating the whole Skill.
