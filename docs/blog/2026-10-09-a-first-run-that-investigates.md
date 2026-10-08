---
description: co rem 1.9.1: the first run stopped writing a summary of each person and started investigating them, the way a reporter builds a profile over several passes.
tags: [REM, Release]
---

# A first run that investigates

When 1.9.0 shipped, its first run did what it promised: it wrote a page for
everyone in your mail. Then we read the pages. Most people got three lines,
a role guessed from a signature and a last-contact date. Reading the trace
explained why. On a large page the model saw under a tenth of the evidence,
searched once, and rewrote the page from scratch each time it ran, throwing
away whatever the last pass had found.

That is how a hurried summariser works. A reporter writing a profile works
differently: read the oldest material first, note the open questions, go
looking for the answers, come back and add what was found without tearing up
the draft.

So 1.9.1 investigates. Evidence too big for one turn is read in rounds, oldest
first, and each round edits the page and hands its unanswered leads to the
next. A final pass keeps every thread and searches for how each one ended.
The first pass reads six months of mail, sixteen pages at a time; meanwhile a
background thread fetches two years, and everyone with older history gets a
second investigation on top of the page already written. At the end, init
draws the decisions and principles that the pages add up to.

On a real mailbox of 4,523 messages, that took 133 minutes and about twelve
dollars at API prices. Fifty-seven people were deepened with 1,261 older
messages and attachments. The pages are also easier to use: the contact
facts sit at the top, a cited mail opens as a message, and a cited PDF opens
from the page.

The lesson was the one every editor teaches: a profile is not written in one
sitting. It is reported, and the draft is never thrown away.
