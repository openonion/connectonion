# Four of three hundred and fourteen

The owner looked at `co rem status` and asked why it read like a debugger's
variable window. Then he asked something harder. The problem was not only co
rem. Every command should look finished, and `co audit` should check that the
same way it already checks help pages.

Adding colour was the easy part. Deciding what "finished" means in a form a
machine can check took longer, because `co audit` has one strict habit: it
never reads source code. It runs a command and judges what it prints, the
same way an agent meets it. Any rule about appearance had to follow that
habit.

So the new rule runs everything twice. The first run is under a
pseudo-terminal, where a person would see colour. The second is into a pipe
with `NO_COLOR`, which is what a log file, launchd or an agent capturing
output sees. There are three questions. Is the terminal run styled? Is the
pipe run free of escape codes? With the codes removed, are the words the
same? The third question is the one that matters. Styling may change how a
word looks, but it must never change which words are printed, because the
agent reading the pipe and the person reading the terminal are acting on the
same information.

The first full run surprised us. We expected co rem and a few old commands to
fail. Instead, 4 of 314 outputs passed. Almost every page failed the same
check: the command after `Example:` and `Back:` was printed without colour.
Typer renders those lines from the epilog, and nobody had ever styled them.
For two years, every help page in co put its most copyable line in the one
place that got no colour.

The run also turned up two false alarms in our own rule. `co schedule check`
and `co rem doctor` print the path of their empty HOME, and each run gets a
fresh temporary directory, so the words were never going to match. The
audit now writes both directories the same way before it compares anything.
A rule that fails when nothing is wrong teaches people to ignore it.

Then came the question of what the rule may run. It is fine to ask for a help
page. Running `co gmail send` to see how it looks is not. We settled on two
locks, both checked from outside. A command is run only if its name is
`status`, `check`, `ls` or `doctor`, and only if its own help page says
`Read-only`. Twelve commands in co meet both conditions. Nothing else runs,
and every run is killed after twenty seconds, because a status command that
waits for input is its own finding.

The standard is written down in `docs/cli/style.md`. It uses the palette the
code already used most: cyan for things you can copy, bold for headings and
numbers, green ✓, yellow !, red ✗, dim for detail. It is built as one module,
`connectonion/cli/style.py`, that returns plain strings. Using it is one
import. Making the 310 failing outputs pass is the next set of PRs, and the
first one is a single change: colour the Example and Back lines where Typer
draws them.
