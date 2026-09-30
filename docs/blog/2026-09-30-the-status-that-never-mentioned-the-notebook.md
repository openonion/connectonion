# The status that never mentioned the notebook

On 1.9.0a4 the owner ran `co rem status` on his own notebook and stopped at
the first line. He had 154 skill pages, a few hundred people and every
project he had worked in over the summer. The command that is supposed to
tell you how that notebook is doing did not mention any of it.

What it printed was the result dictionary, one field per line. The six
schedule times, and then the same six again under `Worker`. The path of a
launchd plist. `Known attempts` and `Total attempts` three times, once for
each kind of token. A whole run record, nested and indented. Every field was
correct. Nothing told him whether the notebook was filling in, which
mailboxes it read, or what to do next.

`co rem init` had the opposite problem. It printed one plain line per stage
and then went quiet for ten minutes while a model wrote his page. A person
at a terminal could not tell a slow mailbox from a hung one. The skills
count, the one number he cared about that day, appeared once in the middle
of the summary and scrolled away.

Neither command was broken. Both had been written to be read by tests and by
scripts, and a person just got the same output. The fix was to write for the
person without taking anything away from the tests and scripts.

Status is now a small dashboard. The first line gives the state and the next
run. Then comes the notebook: people, projects, organizations and skills,
written against mapped, and which page to write next along with the command
for it. After that, today's runs in one line, each mailbox with a ✓ or a ✗
and the command that fixes it, and the last run in one line. The plist, the
counters and the full run record are still there, behind `--verbose`.
`--json` returns the same document it always did.

In a terminal, init now shows a bar for every stage it can count: the
seven-day mail windows, the message bodies, the session files and the
skills. While a model writes a page it shows a spinner with the elapsed time.
It ends by giving the counts again, skills included, then what was written
this run and what to run next.

The lesson was in the constraint, and the constraint helped. Every help page
in co rem is a reviewed text that tests compare byte for byte, and scripts
and launchd logs read the output. So the styling could not touch a word. In
a terminal each line is read for what it contains, such as a `co rem`
command, a count, a path or a warning, and marked up with the palette every
co command shares. Anywhere else, the plain words print exactly as before. A
new test holds every co rem page to that rule. The page must be styled in a
colour terminal, carry no escape codes in a pipe, and have the same words
both ways. The only surprise came from backslashes. Rich reads a backslash
as an escape only when a tag follows it, so a help line that ends in `\`
came out doubled until the test caught it.

The owner's complaint was about looks, but the bigger problem was that
status never showed him the notebook. That took a new layout, not colour. The
colour only had to leave the words unchanged.
