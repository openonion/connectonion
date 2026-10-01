# The same refusal every night

1.9.0a6 added a limit: a page that grows past 20,000 characters is refused. A
daily update had pushed one project page from 13 thousand characters to 25, and
pages that size stop being something a person reads.

The acceptance run the next day found the limit working exactly as written,
and costing money every night. The owner's connectonion page was already 24.6
thousand. Each sync, the round picked it up, sent the model the same new
messages, received a page that was still over the limit, refused it, and moved
on. The next sync did the same. About 260 thousand tokens a night, for a page
that could not change.

Two things were missing. The model was never told the limit: it was asked to
update the page and then judged by a number it had not seen. And the refusal
was not remembered: nothing stopped the round from asking the same question
with the same material and getting the same answer.

1.9.0a7 does both. The prompt now states the page's current size and the limit,
so the model can fold old history instead of adding to it. A refused page waits
until there are messages newer than the ones that produced the refusal.

The lesson: a check that refuses work has two jobs, saying no, and making sure
the same no is not paid for again. Tell the worker the rule before the work, and
remember what you already refused.
