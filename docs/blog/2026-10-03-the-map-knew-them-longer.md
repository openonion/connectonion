# The map knew them longer

A ten-year REM map found 613 people in the owner's mail. The earlier two-year
map had found 382. At first, this looked like a discovery win: 231 more people
could be found without downloading ten years of message bodies or spending a
model call.

Then we checked what would happen after discovery. The map held the date of
each person's first message, but a first investigation still read a fixed two
years. A person last active recently could appear in the queue while the
earlier part of the relationship stayed outside the evidence the writer could
search. The map could know about a history that the memory did not read.

We considered giving every first investigation ten years. That would make a
short relationship pay the same search cost as an old one. Instead, the first
read now reaches back to that person's first mapped message, with two years as
the minimum. Updates still read only mail since the last investigation. The
queue and cost preview show the longest planned window, and init warns when
some reads exceed two years. This changes the input available to the existing
investigation, not its prompt or its page format.

In the private ten-year map, 269 people had first mapped mail older than two
years; 251 of the queued full investigations would use a longer window. Both
mailboxes completed their metadata listings, with two capped seven-day windows
split and no uncaught capped windows or map errors. The run observed 21,655
messages and completed in 1,268 seconds. A focused test covers an older first
message and the resulting queue window; the existing people and first-run
tests passed.

Those numbers establish discovery and planned scope, not memory quality. The
model has not yet read those older conversations in a live batch, so its time
and token cost are still unknown. Longer evidence can make a page more useful,
but it can also make the batch expensive. We will compare the preview with an
actual resumable run, inspect the cited findings, and revisit the window rule
if the additional history does not improve the pages enough to justify its
cost.
