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
some reads exceed two years. A single-page `co rem investigate <person>` call
now uses the same first window when the caller does not specify `--days`.

In the private ten-year map, 269 people had first mapped mail older than two
years; 251 of the queued full investigations would use a longer window. Both
mailboxes completed their metadata listings, with two capped seven-day windows
split and no uncaught capped windows or map errors. The run observed 21,655
messages and completed in 1,268 seconds. A focused test covers an older first
message and the resulting queue window; the existing people and first-run
tests passed.

Those numbers establish discovery and planned scope, not memory quality. One
live single-person read exposed the difference: the direct page command still
used a fixed two-year window, missing earlier person-linked mail that the map
had seen. Its model turn used 530,231 input tokens, 472,576 cached input tokens,
and 8,714 output tokens. An independent AI role-based founder/UI review opened
all seven cited originals and found three material attribution problems: a
company mailing became a personal relationship origin, a group recipient
became a company presenter, and composite claims cited messages that did not
support every clause. These are private-source findings; no names or messages
are reproduced here.

The first-contact date was also being extracted automatically from the oldest
mail in the requested window. That date could be a company mailing or simply
later than mail already known to the map. We stopped treating it as an
automatic fact, told the writer about earlier mapped metadata, and tightened
the page's attribution rules.

Three further reads of a private copy used the mapped 793-day window. The
second recovered the earlier direct exchange but still inferred event
attendance from a request to join a lineup and a group thank-you. The third
kept to the supported one-pager handoff, yet called an incoming question a
debt despite unknown replies outside retained mail. We made the next action
conditional and stopped the reader from treating a generic "no reply found
here" as a debt owed by the other person. The fourth rendered `Open` rather
than `You owe` at desktop and phone widths.

The fourth page still attached two real details to the wrong originals: a
calendar-invite question appeared in the next cited email, and a website form
was present in an earlier signature rather than the cited latest one. Correct
facts elsewhere in a source bundle do not make a nearby citation accurate.
The broader batch remains a draft while claim-to-source accuracy is measured
and corrected. A longer window supplies evidence; it does not certify the
memory written from it.

A two-person parallel trial then selected two previously uninvestigated people
whose mapped history required 870- and 857-day reads. Both started within a
second, gathered 326 matched mail bodies and 51 attachments in total, and
finished in 4 minutes 49 seconds. Their turns used 1,807,430 input tokens
(1,598,976 cached) and 33,032 output tokens; both pages passed the structural
validator. The first source audit found one page describing messages as a day
apart even though both fall on the same Sydney date. That is a different
quality gate from throughput, and the draft cannot use a successful batch
exit as evidence that its relationship timeline is correct.
