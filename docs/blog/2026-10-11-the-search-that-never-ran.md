---
description: co rem 1.9.2b6: the second pass was supposed to go deeper, and the logs said it did. Reading one run showed where the depth went.
tags: [REM, Investigation]
---

# The search that never ran

The question was simple: when the notebook investigates a person a second
time, does the page get deeper? The run logs said yes. Four rounds, fifteen
minutes, seven million tokens, page changed. By every number we track, Nina's
page had been worked on.

Then we read the run's own report, round by round. Round one did real work:
it found she had been the user's manager for a stretch of casual work, and
later coached a pitch. Round two asked Outlook five questions about the
threads it could not close, and Outlook refused all five. Round three got
nineteen search results and reported that every one was a newsletter or a
digest. Round four was the editing round, the one that is supposed to turn
the accumulated notes into one account. It answered NO CHANGE, because, it
said, no new evidence had arrived.

So two of the four rounds, and most of the fifteen minutes, produced nothing,
and the page kept nine lines that say what is not known in places where a
reader expects to be told what is.

Each failure was small. Outlook wraps a search in quotes, so the model's own
quotes around a phrase broke the query. A search for plain words finds the
same words in every mailing list that ever used them. And an editing turn
that is told "nothing new is supplied" will read that as "nothing to do."

The fixes are the same size. The quotes were fixed in 1.9.2b4, the same
day, by another branch reading a different run: Outlook now escapes them.
This beta does the other two. A search answer is kept only if it comes from
someone the notebook knows, a mapped person or the owner. And
the editing round is no longer asked whether anything changed: after the
final round, code counts the hedged lines outside Uncertainties and, if there
are any, hands the model the list and asks for each one to be rewritten,
moved or deleted. The run record keeps the count before and after, so the
next person who reads a log can see whether the editing happened, not only
that a round with that name ran.

The lesson we keep relearning is that a stage that ran is not a stage that
worked. Rounds, searches and edits all leave a trace; what matters is whether
the trace shows the page getting better, and that has to be measured by code
on the page itself, not inferred from the fact that the model took its turn.
