# A notebook can have memories while its updates are off

The reader opened a notebook with written memories on the first screen. Its
compact status still said “Not started.” The command behind that status was
accurate about one thing: the owner had not authorized a background schedule.
But next to three memory cards, “Not started” sounded like the memories
were missing. A status line can contradict the page it sits on even when its
underlying service state is technically correct.

We considered changing the service's state everywhere. That would also alter
`co rem status` and other clients that use the same consent state, although
their wording is about setup rather than an already open notebook. Instead,
the reader now translates that state when it has records. Its rail, phone
status and Maintenance section say “Background updates off” and keep
`co rem start` as the next action. A truly empty notebook retains “Not
started.” This is a display decision; it neither starts a schedule nor
changes the saved pages.

An independent AI founder/UI role review opened a private written notebook
(810 records, 227 written), a mapped-only notebook (948 records), and a
fresh empty notebook at desktop and phone widths. The first two showed the
updated background-state wording, while the empty notebook kept initial
setup wording. The reviewer also caught literal command backticks in the
desktop rail; those were removed before the final desktop recheck. The
sampled pages had no horizontal overflow or browser page errors. This was a
role-based AI review, not a human founder or an audit of every page.

The compact status does not explain that `co rem start` also asks the owner
to approve sources. The CLI guide covers that step; we will revisit the
reader copy if people still mistake scheduling for source approval. The key
boundary is that a past memory and a future update are separate states. The
reader should name the one that is actually off.
