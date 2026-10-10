# The map had worked

The ten-year REM map finished and found hundreds of people. Opening the reader
then took about a minute and a half. On a phone, its first screen said “No pass
yet” and “Ready when there is something new.” The count of mapped records and
the way to investigate one were below the fold. A reader could reasonably
think the long run had done nothing.

The notebook had 575 visible People. Scrolling their table to the final column
showed another problem: the sticky Name column grew from 170 to 200 pixels and
covered the start of “Last contact.” Our six-row browser fixture had passed
because its names never made the column grow. Thirty-eight more possible
contacts were held for review, but the page did not explain why they were
missing from the visible count.

One date discrepancy went below the interface. For a person with several mail
addresses, the mapped page used the latest contact from the whole group. The
saved map row kept the first address's dates. In the private reader, 21 mapped
people had a later page date than their map mail date. That also matters to a
first investigation that chooses how far back to read from the map's first
date. The row now stores the earliest and latest dates across the group.

The first screen now treats a finished map as an outcome: it names the mapped
records, says that no memory has been written, and offers People and the queue
preview as next steps. The People sheet explains the held count. On phones,
Name has a fixed 170-pixel width, so the last heading remains readable even
with 575 rows. A large invented roster test covers the scroll and both sort
directions.

The long opening wait came from testing every possible name against the prose
of every mapped-only stub. Those stubs have no investigated relationship
finding. The reader now keeps their explicit links but skips inferred prose
links until a page is written; name patterns are compiled once for the pages
that do need the scan. On the same private ten-year notebook, a cold render
fell from about 99 seconds in the released reader to 2.65 seconds in this
candidate. That is one-machine evidence, not a general speed guarantee.
A different notebook with many written notes still took about 40 seconds;
the gain is largest for the mapped-only first run.

The map is still only discovery. The older conversations have not yet been
read by a live model batch, and this reader change does not claim they are
useful findings. The next check is a fresh map to confirm the grouped dates,
then an actual person batch to compare source-backed memories and token cost.

After the next release, the reader recognized five existing People pages as
service or institutional senders. The old map still held 613 people pages:
570 browsable people, 38 possible contacts held for review, and those five
excluded senders. A follow-up reader change makes both exclusions visible
beside the People count, so the smaller roster does not look like lost data.
