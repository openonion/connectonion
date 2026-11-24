# Notion keeps its edit times to the minute

*2026-11-24*

We had a Notion source for REM before we had a rule for sources. It captured
every page in a chosen scope, saved each version as a snapshot, downloaded
the files Notion hosts, kept a state per page and taught the reader a
Notion-specific panel. Nearly nine hundred lines, most of them about keeping a
copy. Then the owner decided, in design decision 081, that a REM source is its
`co` command and REM keeps nothing from it. Asana and Obsidian were rebuilt as
two subcommands each. This change does the same for Notion, and none of the
nine hundred lines came with it.

`co notion changes --since <time> --json` lists the pages this key can read
that were edited since then, oldest first, in the shape `co asana changes`
gives. Database rows are pages, so an edited row is listed. `co notion show
<id> --json` reads one page as it is now: its text, who created it, when it was
last edited, its link and properties. A citation `notion:<id>` opens through
`show`.

The detail that shaped `changes` is a small one. Notion keeps
`last_edited_time` to the minute: a page edited at 10:05:30 reads 10:05. A
cursor of 10:05:20 that compared exactly would skip it forever. So the minute
`--since` falls in is included, and a page can appear in two consecutive lists.
That is the cheaper mistake: a reader keeps one item per id and time, and
nothing is missed.

Notion's search can sort by last edit, newest first, so `changes` stops at the
first page older than `--since` instead of reading everything the key can see.
If more than 5,000 pages changed it lists nothing and says the read was
incomplete, rather than handing REM a cut list.

`show` is careful about what it cannot see. A page read that hits its block
limit ends with an `[INCOMPLETE]` line and `complete: false`. The author's name
needs a capability an internal connection may not have; without it `author` is
null beside the user id, never a guess.
