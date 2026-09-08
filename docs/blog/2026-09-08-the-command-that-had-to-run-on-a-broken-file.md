# The Command That Had to Run on a Broken File

Draft for 1.8.4; publish after release acceptance.

The owner asked a simple question: do we have `co env`? He remembered one.
Issue #1444 had even told the implementer to audit and reuse it. The audit
found nothing: there had never been a `co env`. What existed after #1450 was a
root option, `co --env-file PATH`, that chose which file a command read. Nothing
showed what that file held, and nothing edited it.

That gap had a shape. `co doctor` reported a missing OpenAI key and, in the
column that is supposed to name the fix, said "set OPENAI_API_KEY in global
keys.env". That is an instruction, not a command. A person has to find the file;
an agent driving the CLI through a shell invents a command and pays a round
trip for it. The mail commands did the same thing in a subtler way: "Google
account not connected. Next: co auth google". People ran the auth again. The
account had been connected an hour earlier — in the other file, the one this
invocation had not selected. The message never said which file it read.

Then there was the case I reproduced before writing any code. Put one bad line
in `~/.co/keys.env` — a pasted key with a stray quote, a note without an equals
sign — and every `co` command stops with exit 2 and `Next: co --help`. Help lists
thirty commands. None of them opens the file. `import connectonion` raised the
same message from package startup, so an `agent.py` died with a traceback that
pointed at a help screen.

So `co env` had one obvious job, showing and setting values, and one job that
turned out to be the real design constraint: it had to run on the file that
nothing else could use. That is where the first attempt broke. The env file is
selected in an eager Typer callback, because it must happen before any command
loads settings. Eager callbacks run before the parser knows which command was
asked for. The same check that stopped `co gmail` on a broken file stopped
`co env`, the command meant to explain it. I could not exempt one command from
inside a callback that did not yet know the command's name.

The fix was to stop deciding there. The callback now records the failure and
returns; the group callback, which does know the subcommand, exits for every
command except `env`. `co env` reads the recorded error and prints the line
number. It never prints the line, because in a credentials file the broken line
is as likely as any other to hold a secret. It also refuses to `set` anything
while the file fails to parse: rewriting around a bad line drops that line
silently, and that is precisely the kind of change nobody can explain later.

The second constraint came from the fix that had just landed. #1450 made
provider credentials whole records, so a token from one account could not be
stitched to the email of another. A `co env set GOOGLE_ACCESS_TOKEN …` would
reopen that hole by hand. So `set` refuses the ten record fields and names the
auth command instead, and `unset` on any one of them removes the whole record
and says so. That last part is also the first supported way to disconnect an
account from a file.

Everything else followed from those two decisions. The doctor's column now
reads `co env set OPENAI_API_KEY <key>`. The provider errors name the file they
read, or say that the process supplied a partial record, and point at `co env`
before their `Next: co auth …` line. The startup message became
`~/.co/keys.env: invalid syntax on line 2. Next: co env`, and running that
command tells you what to do.

What I measured: the new test file has 31 cases, written before the command
existed and red until it did. The two existing contract tests that had pinned
`co --help` as the recovery were changed on purpose and say why. The full unit
suite passed with 8,014 tests, and the CLI e2e suite with 435; the one e2e
failure is a pre-existing case that shells out to whichever `co` is on PATH,
which on this machine is a different install. The text-only tip test from the
CLI design skill was run per command, twelve cases, and it earned its keep:
the first run scored 10 of 12, and both misses were a model answering `cat`
on the credentials file. The tips now say what `co env` does that `cat` does
not, and the rerun scored 12 of 12. Its table is in the pull request.

The lesson is small and I will forget it without writing it down: a tip is only
a tip if the command it names can run in the state the error describes. `co
--help` was reachable and useless. `co env` was useful and, until the callback
moved, unreachable.
