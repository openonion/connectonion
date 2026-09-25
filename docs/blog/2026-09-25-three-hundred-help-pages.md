# Three hundred help pages

We asked a plain question: can an agent find every `co` command from
`co --help` alone? For an agent, a help page is the prompt that describes a
tool. If the page is vague, the agent guesses a command name, and a guess
costs a failed call.

So we audited all of them. There are 300 commands. Every one opened its help
without error, and none wrote a file doing it. Every command named in a tip
existed. But only 14 met the whole contract we set in #1643: say what the
command does, give an example, say what it changes, and name the way back.
240 had no example, 267 had no way back to their parent, and about 200 never
said whether they change anything.

We also tested discovery directly. A model got only the help pages it asked
for and a goal such as "check how much credit I have left", then had to name
one command. It managed 9 goals out of 14. The failures were specific. `co status`
never says it shows your balance. `co trust` never says that its lists decide
who may call your agent. `co env set` says "the selected file" but not that
the default file is shared by every project. In each case the right page was
open, and the model still couldn't tell that it was the right one.

Two things change in this pull request. The way back is now written once, from the
command tree, into every page, so a command added next year gets it without
anyone remembering. And CI now checks every page. Today's gaps are recorded in
a baseline file, and the test enforces that the file only shrinks: a new
command must pass, and a fixed command must leave the list in the same pull
request. We tried the check against the old code first. It failed 257 pages,
which is the evidence that it is actually checking something.
