---
description: co rem 1.9.1b2 writes the first pages from mail already on disk and fetches older mail in the background.
tags: [REM, Memory, Performance]
---

# Read what you have, fetch the rest

We doubled co rem's workers from ten to sixteen and the first run barely got
faster. Thirteen of the sixteen were waiting on the mailbox.

Every person's first investigation asked Gmail or Outlook for two years of
their mail before the model could read a word. Init had already saved the last
six months to disk; the first pass asked the provider anyway, for the whole
two years, one person at a time per mailbox slot.

1.9.1b2 splits the work the way a person would. Write the page from what is
already on the desk: the last six months. Meanwhile, someone goes to the
archive for the older boxes. When they come back, read the old letters and add
what they change.

So the first pass reads from disk and starts at once; four background workers
fetch each person's older mail into the same local archive; and the people who
turn out to have a longer history get a second pass that reads it, in rounds,
on top of the page already written. Nothing fetched is fetched twice.
