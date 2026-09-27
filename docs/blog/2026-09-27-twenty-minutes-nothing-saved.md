# Twenty minutes, nothing saved

The Wiki's nightly upkeep reads new material from your coding sessions and
updates the pages it concerns. On the author's notebook, the one we use every
day, a batch of forty messages cost about two and a half million tokens. Twice
in a row, the same batch ran for twenty minutes and timed out with nothing
saved.

We read what the model actually did in those twenty minutes. It was being
careful. It searched the notebook's 1,187 pages for where the material
belonged, found eight pages, and spent seven minutes planning every edit
before writing any. Then it rewrote each page in full and started checking
its own work. The clock ran out during the check. Along the way it also tried,
again, to delete a duplicate page left behind by an older map, and the rules
refused that.

The fix was to stop asking one turn to do everything. Taken one at a time,
none of these jobs is hard for a model. Doing all of them in one turn, against
the whole notebook, is what made it slow and fragile. A script now does the
parts a script can do. It finds the pages a batch concerns: the project whose
folder the sessions ran in, and the people the material names. It sets aside
the pages an old map made that the current map would not. Then the model
updates one page per turn: that page plus the batch, written, checked and
saved on its own.

The same batch now takes about seven minutes and under half a million tokens,
and a page the checker refuses costs only that page. It is also closer to how
the Wiki was meant to work. The map is a script that builds the frame, and a
Skill fills in one page at a time.
