# A quiet thread is not a closed thread

Candidate repair for #2464 and #2207, related #2143. Not released.

The morning brief already knows about deadlines and has a separate place for
old conversations. The boundary between them was wrong: an item older than
60 days could leave the active count precisely when its deadline became due or
overdue. A future deadline prevented that quiet classification; crossing the
date removed that protection. The heading then called the remaining overdue
items “due soon.” These are reproducible source and fixture failures, not a
claim that every old note describes a current obligation.

The repair keeps recorded explicit deadlines visible and counts overdue items
separately. It retains the older-thread disclosure for undated requests, with
an explanation that their dates do not prove resolution. Automatically closing
them would make a short screen look clean by losing uncertainty. Putting every
old request in the primary queue would bury current work. Keeping the original
items inspectable, while protecting dated commitments from age-only demotion,
is the chosen middle ground.

The writer had a related contradiction. Its person synthesis prompt said asks
close only on matching replies, but also instructed it to move threads quiet
for 60 days to History. The candidate removes that age-only closure rule. An
unanswered request is not an agreed debt, and an old meeting date does not
establish that preparation or follow-up was delivered.

Aligning Python counts with the reader also exposed a calendar boundary: written
English deadlines worked in the reader but not the census. Both now recognize
the same valid written dates and reject impossible ones. Omitted years still use
the existing snapshot-year inference; this patch does not prove the intended
year or verify the current status of an old ask.

A read-only scan of 587 current visible pages found no old explicit-deadline
candidate matching this failure. It left every page hash unchanged. The repair's
failure and correction are demonstrated by invented dated cases and an offline
runner-dispatch contract. A real first run, resolved-versus-unresolved source
review and native desktop/phone interaction acceptance remain separate work.
