# The command that ended in silence

*2026-09-08 · Design Journal*

We gave a model the output of `co trust add 0x7f3a…` and one instruction:
reply with the next shell command. The output was a single line, `✓ 0x7f3a…:
promoted to contact.`. Asked to confirm the address was now a contact, the
model replied `contact list`, and on a second run, `shell`. Asked to see
every trust list, it replied `bash`, then `trust list`. Given `✓ Announced.`
and asked for the address subscribers would follow, it replied `rad self`,
twice — a command from a different tool altogether. Given `Index written to
~/.co/skills-index.json`, it ran `cat` on the file. Not one reply began with
`co`. The model did what any reader does when a page ends without saying
what comes next: it wrote the sentence it expected to find there.

That is the whole problem with a command that ends in silence, and it is not
a problem a human notices. A person at a terminal has the rest of the screen,
the muscle memory of yesterday, and `--help` a keystroke away. An agent has
the output. When we drive `co` from Claude Code or Codex, the output is the
entire world, and every command that does not name the next one is a command
that asks the agent to guess. A guessed name costs a round trip when it is
wrong, and it is wrong more often than you would think, because the names
that feel natural — `show`, `open`, `get` — are exactly the ones we did not
happen to pick.

## How many were silent

We walked every command to its last printed line. There are about a hundred
and sixty of them. Roughly a third ended on a URL, a file path, a checkmark,
or nothing at all. The whole of `co trust`. The whole of `co sms`. Most of
`co skills`. `co init` and `co create`, which end their welcome screen on a
link to the GitHub repository. `co deploy`, which ends on the dashboard URL.
`co announce`, whose last word is `Announced.`

None of these were bugs anyone had filed. Each command did its job and said
so. What they did not do was the thing a good colleague does at the end of a
handover: point at the next step. The mail commands already did this —
`co gmail inbox` ends with `Read one with: co gmail read <#>`, and the
Synology commands end every path, success or failure, with a `Next:` line —
because those surfaces were built for agents from the start. The older
commands were built for people, and people do not need to be told.

## One place instead of a hundred and sixty

The first instinct is to add a line to each handler. That works for the
handlers you remember, and the one written next month in a hurry inside an
error branch will not have it. So the next step is no longer something a
handler prints. Every command in `co` passes through one group class on its
way out, and that class now does the pointing: after a command returns
normally, it looks the command's path up in a table and prints the entry on
stderr.

```
$ co trust add 0x7f3a…
✓ 0x7f3a…: promoted to contact.
Next: See every list:  co trust list
```

Stderr, so stdout stays whatever the command's data was — a JSON caller
parses the same bytes it did before — and the line still reaches anyone who
captures both, which is every agent we run. Only a normal return gets there:
`--help`, a usage error and every deliberate exit leave by exception, so a
failed command never gets a "next" that assumes it worked.

The table has an entry for every command. Commands whose next step depends
on what they found — a listing that says `co gmail read <#>` only when there
is something to read — are marked as handling it themselves, and the table
prints nothing for them. Everything else has one line, one command, spelled
out with the argument shape filled in: `co skills copy <name from this
index>`, not `co skills copy <id>`.

And the table is the register. A test walks the command tree and fails when
a registered command has no entry, so a new command cannot ship without a
next step by forgetting one. A second test reads every tip in the CLI's
source — the `Next:` lines, the rotating browser tips, the table — and checks
each `co …` phrase it names against the tree, at a group the next word must
be a subcommand, so `co gmail open` fails and `co browser tab ls` passes.
That test went red the first time we ran it, on a placeholder command a
helper had used for years, which is the kind of thing you want a test to be
embarrassed about instead of a user.

## Testing a tip the way it will be read

A tip that reads fine to a person can still fail its actual reader. So we
grade them the way they will be used: a fresh model, given only the tip and
a one-line goal, replies with one shell command. Pass means the command
exists and is the one the tip named. All thirty-seven static tips passed,
along with the rotating tips on `co status` and `co browser`. The one reply
worth quoting came from `co skills discover`, whose tip says
`co skills copy <name from this index>`; the model replied with a pipeline
that runs the discover command and copies its first result. That is a reader
who understood where the value comes from, which is what the placeholder was
for.

## The screen before the first command

The same audit turned up the oldest gap. Bare `co` printed a hand-typed list
of commands under a heading that read as the whole list, and it named
sixteen of twenty-four. `ai`, `server`, `skills`, `sub` — the network story
of the last two releases — were real, registered, and absent, because a
hand-typed list has no way to notice the ninth thing it forgot. That list is
now read from the CLI itself, so a command is on the first screen the moment
it is registered, with the same summary its `--help` carries. And a new
`co commands` prints the whole tree, three levels deep, one line each, plain
text, so `co commands | grep draft` finds the draft commands without knowing
which group holds them. `--help` only ever showed one level; an agent that
cannot find a command from `--help` invents one.

Three levels of disclosure, each complete at its own level: `co` for every
command, `co commands` for every subcommand, `co <command> --help` for the
options of one. And after each of them runs, the next one.
