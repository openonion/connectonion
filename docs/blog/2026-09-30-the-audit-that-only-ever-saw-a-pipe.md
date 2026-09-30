# The audit that only ever saw a pipe

`co status` opens with a coloured table, a red line for a missing key and the
command to run in bold. `co rem status` printed bare `key: value` lines, and
`co commands` printed three hundred lines of grey. The owner's question was
simple: why does one command look finished and the next one look like a debug
dump, when `co audit` already checks every page on every PR?

The answer was in the first lines of `run()` in `cli/audit.py`. Every page is
run the way an agent meets it: `NO_COLOR=1`, `TERM=dumb`, 200 columns, output
captured. That is the right way to ask whether an agent can use a page, and it
is exactly why the audit could not have caught this. With colour switched off,
a styled page and an unstyled page print the same bytes. The audit had never
seen a terminal, so it had nothing to say about how one looked.

So the audit now runs each page twice. The second run is how a person's
terminal would run it: `FORCE_COLOR=1`, `TERM=xterm-256color`, 100 columns,
the same empty HOME. The new `look` rule compares the two. The pipe must hold
no colour codes, the words must be the same, and for `co` the terminal must
show some colour, because a plain co page is one nobody moved onto the shared
style. Other programs are allowed to be plain. Plenty of good CLIs print plain
help on purpose, and that never stopped an agent.

The first full run over 302 pages found four problems outside `co rem`. Two
were expected: `co commands` and the hand-written `co proxy` page printed no
colour. The third was a real bug nobody had reported. At 100 columns
`co doctor` cut the package path to `…/connec…`, so a person at a normal
terminal saw less than a script did. Rich cuts a long cell to an ellipsis by
default, and the fix was one `overflow="fold"` per column.

The fourth was the rule getting it wrong. `co ai --help` has a `--sandbox`
row whose value, `read-only|workspace-write|danger-full-access`, is too wide
for 100 columns. Rich folds it onto the next line while the description keeps
going beside it, so reading line by line the words come out in a different
order. The words were all there, only arranged differently. So the rule
compares the characters each run prints, ignoring order. A cut or changed word
still fails, and a table reflowing at a narrower width no longer does.

The lesson for us: a gate only judges what it runs. The help contract has
passed every page for months, and every one of those runs was a pipe. Adding
the terminal run took one environment switch. The harder part was making the
comparison fair to both ways of printing.

`co rem`'s fifteen pages still print plain while their rewrite lands (#1996).
They wait in a list in the test that can only get shorter: once one of them
passes, the test fails until someone takes it off the list.
