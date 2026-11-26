# Notion keeps its edit times to the minute

We had a Notion source for REM before we had a rule for sources. It captured
every page in a chosen scope, saved each version as a snapshot, downloaded
the files Notion hosts, kept a state per page and taught the reader a
Notion-specific panel. Nearly nine hundred lines, most of them about keeping a
copy. Then the owner decided, in design decision 081, that a REM source is its
`co` command and REM keeps nothing from it. Asana and Obsidian were rebuilt as
two subcommands each. This change does the same for Notion, and none of the
nine hundred lines came with it.

What replaced them is small. `co notion changes --since <time> --json` lists
the pages edited since a time, and `co notion show <id> --json` reads one. REM
remembers where it stopped and asks again later. Everything rests on one
comparison: was this page edited after the cursor?

That comparison is where Notion surprised us. Notion keeps `last_edited_time`
to the minute: edit a page at 10:05:30 and the API says 10:05. Now picture REM
reading at 10:05:20 and saving that as its cursor. Ten seconds later someone
edits the page. The next read asks for pages edited after 10:05:20, Notion
reports 10:05, which is earlier, and the page is skipped. It stays skipped
until somebody edits it again. Nothing fails and nothing is logged; the edit
simply never arrives.

There were two ways out, and each is wrong some of the time. Compare exactly,
and REM can miss an edit without a trace. Round `--since` down to its minute,
and the same page can come back in two reads in a row. We took the second. A
duplicate costs REM one comparison, since it keeps one item per id and edit
time. A missed edit costs someone the thing they were looking for, with no sign
it was ever there.

The lesson: a cursor is only as precise as the clock it is compared against.
When the other side rounds, round with it, and choose the mistake you can see.
The same rule decides the edge: if more than 5,000 pages changed, `changes`
lists nothing and says the read was incomplete, rather than handing REM a cut
list that looks whole.
