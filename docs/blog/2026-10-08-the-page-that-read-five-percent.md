---
description: co rem 1.9.1a2 reads a person's whole history in rounds, edits the page instead of rewriting it, and follows leads like a reporter.
tags: [REM, Memory, Agents, Product design]
---

# The page that read five percent

We asked a simple question of 63 real investigations: what did the model
actually read?

For the people who matter most, almost nothing. Given 2.3 million characters of
mail about one colleague, laid out in 143 files with an index, the model opened
four of them, read about five percent, and wrote a confident page. It searched
by subject line, not by lead. When it found a request, it wrote "unconfirmed"
rather than looking for the reply. And 49 of the 63 times it wrote the whole
page from scratch, so whatever it did not copy back was gone.

None of that is a model problem. It is what you get when you hand a summariser
a filing cabinet and one turn.

1.9.1a2 changes the shape of the work. The evidence is split, oldest first,
into parts that travel whole in the prompt, so every part is read. Each round
edits the page the last one left, instead of starting blank, and hands over a
list of open leads: a name to search, a reply to find, an attachment to read.
The last round reads the whole page and makes it one account, with a line per
thread saying how it ended.

On that same colleague the page went from 13 cited sources to 23, kept every
line the first pass had right, and found a handoff of four contacts the first
pass never saw. It cost about sixteen cents at API prices.

The Skill now says what we meant all along: work like an investigative
journalist. Start from what the page does not know. Every name is a lead.
Before you write "no reply", look for one.
