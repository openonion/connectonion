# The dashboard that wrapped at the margin

`co rem status` already had a palette. Commands were cyan, counts were bold,
paths were dim, and every result ended on a `Next:` line. By the rules we had
written for how a `co` command should look, it passed. Then we opened it on
the owner's real notebook, in an 80-column terminal, and read it the way he
does first thing in the morning.

The first line was 130 characters long: "not scheduled here — the saved
schedule belongs to another notebook or was removed; co rem start schedules
this one · no run scheduled". It wrapped to the left edge. The archive line
under Mailboxes was longer still, and wrapped through the column that every
other mailbox lined up on. "6 written of 330 mapped" sat four lines above
"1 written of 142 mapped", and you had to read both numbers in both lines to
see which category was behind. What happened overnight, which is the reason
the notebook exists, came third, after the counts.

So the colours were right and the page still looked like a field dump with
colours on. A palette decides what each word looks like. It does not decide
where anything goes, and that was the part nobody had designed.

1.9.0a9 designs it. Every value starts at one column, so a section label sits
in the margin and the eye runs straight down the values. Status opens with
today: pages changed, items read, then what it cost. Each category is a row
of ten dots, filled for the share that is written, with the two counts
right-aligned beside it, so a notebook that is 2% written looks like one at a
glance. A fix goes on the line under the thing it fixes, after an arrow,
instead of trailing off the end of a line the terminal had already wrapped.
A line that is still too long now wraps under its own column, not at the
margin.

The same layout runs through `doctor`, the `sync` summary and the map that
`init` prints, so you only learn it once. A few glyphs carry a meaning each
and nothing more: a filled dot for written and an empty one for mapped, a
tick for fine, a cross for needs a fix, a circular arrow for work that picks
up where it stopped. They are words as well as decoration. A pipe or a log
gets the same characters as the terminal, and `--json` stays as it was.

The lesson we took: a style guide that only checks colours will pass a page
that is hard to read. Layout is part of the design too. The way to check it is
to read the page at 80 columns, on real data, before deciding it is done.
