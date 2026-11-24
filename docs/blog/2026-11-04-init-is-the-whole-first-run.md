# `co init` is the whole first run now

A read-only audit of a first run on a clean machine went like this: `co init`
wrote keys, linked skills, refreshed the command index and said done. The
person then had an agent that could read mail and calendars but no notebook,
because the notebook lives behind a second command, `co rem init`, that
nothing on the screen had mentioned. On macOS, `co init --background` had
quietly done the opposite: it created the REM storage folder without asking
whether any source could be read, and then also never built anything.

The fix is the obvious one, and it was decided by the owner in one line: the
global `co init` sets REM up itself. It offers `co auth google` or `co auth
microsoft` when no mailbox is connected, asks the one question that has to
stay, whether these sources may be read with this model on this schedule,
installs the scheduler and says which one it installed (a Codex Scheduled
task or launchd), and then runs the same first-notebook build that `co rem
init` runs. `--no-rem` opts out. Without a terminal, or with `--yes`, it
creates storage only and prints the two commands to run later: unattended
setup must not grant consent on someone's behalf.

Two things turned out to matter more than the plumbing.

The first was a pause. The first run prints an estimate before it spends
anything: about so many pages, so many tokens, so many minutes. Until now
the only way to decline at that point was Ctrl-C. Inside `co init`, where the
person did not ask for twenty minutes of model work, that is not a choice,
it is an ambush. So the estimate now ends with `Build the first map now?
[Y/n]`, default yes. Pressing `n` keeps upkeep installed and prints `co rem
init` for later. The same pause applies to `co rem init` itself; `--yes` and
non-tty runs keep today's behaviour.

The second was what counts as spending. The session summaries, a model
call per recent coding session, used to run in parallel with the mail
download, saving several minutes on a fresh map. They now run after the
pause. A few minutes on the first run is the price of a prompt that means
what it says: nothing is charged before you answer it.

The first version of this change, written by Codex from a brief, recorded
consent and installed the scheduler and stopped there. Its tests were green.
A scheduled sync on a never-mapped notebook only extracts new mail; the
owner page, the map of people and projects and the first pages all come from
the init flow. The review caught it by asking what the person would be
looking at ten minutes after `co init` returned: nothing. The second version
moves the body of `co rem init` into a function both commands call, so there
is one first run, reached from two places.

What was measured: on the unit suite restricted to init and REM, 4984 tests
pass; the new file `tests/unit/test_init_rem.py` holds twenty cases under an
isolated HOME, with the model boundary mocked, including that `co init` asks
for consent exactly once and asks the estimate question exactly once.
