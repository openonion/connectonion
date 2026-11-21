# The reviewer who never flagged the same page twice

*2026-11-15*

`co asana` passed every rule `co audit` checks on its first try: eight pages,
ten rules, each with an example, a usage line, a way back and no private
paths. Then we ran the model half, `co audit co asana --review`, which asks a
model whether a newcomer could use each page, and it failed. One page.

The first time it was `co asana comment`. Its second example was
`co asana comment 1209876543210987 - --yes`, where `-` reads the comment from
standard input. Copied as written, it would sit there waiting for input that
never comes. A fair catch: we wrote it as the shortest form of a feature, not
as a command anyone would run. It became `... - --yes < note.md`.

The next run passed `comment` and failed `check`, whose first line opened with
the variable name `ASANA_ACCESS_TOKEN` and "the gid scripts use". The run after
that failed `tasks`, because `--listing` promised "to pin its rows". Then
`projects`, whose help said "every page is read before anything is shown":
we meant pages of Asana's API, and a reader hears pages of help. Then
`comment` again, for the words "Task gid".

Each fix was right and each run found a new page. The reviewer does not keep
a list; it reads one page cold and reports the weakest sentence it sees, so
fixing that sentence only moves the weakest sentence somewhere else. What the
five findings had in common was not a page but a vocabulary: "gid", "pin",
"page", a variable name in a first line. Words that are exact to the person
who wrote the client and opaque to the person typing the command.

So the last change was not to one page. Every option and argument that said
"gid" now says "ID" (Asana's own JSON still says `gid`, and `--json` prints it
unchanged), and every page was read again for words that only make sense from
inside the code. The rule checks still pass, 10 of 10 on 8 of 8 pages.

The lesson we are keeping: when a judge that varies between runs keeps
finding something new, stop fixing its findings one by one and look for what
they share.
