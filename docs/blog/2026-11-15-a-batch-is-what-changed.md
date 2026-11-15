# A batch is what changed, not what exists

*2026-11-15*

We were adding a task tracker as a REM source (#3034), and the first real
account taught us two things that had nothing to do with task trackers.

A tracker saves a task again each time it changes. A page cites one saved
version: the line "due 20 November" points at version 3 of the task. When the
date moves, version 5 arrives, and the maintenance turn rewrites the line and
cites version 5. REM already refuses a rewrite that drops a source id the page
had, for every source, and it should: one comment on another task once made a
turn delete a true deadline because that task was not in the batch. But here
the check could not tell an update from a loss. Version 3 was gone from the
page, so the rewrite was refused, and the page kept the old date.

The reader had the mirror image of the same fault. Asked to show what a
citation says, it found the newest saved copy of the task, not the version the
page cites, so the excerpt beside a line could say something the line never
claimed.

The first fix was a branch for that one source inside the runner. Review asked
the right question: is this the tracker's problem? It is not. Any source whose
records change in place has versions. So the fix is a small registry,
`rem/source_versions.py`. A source says, for its own ids, which record a
version belongs to and how to show exactly that version. Page review then lets
a rewrite replace a version with a newer version of the same record; a version
replaced by nothing is still a loss. The reader asks the registry before it
falls back. No source registers in this change, so nothing behaves differently
until one does.

The second lesson was about which pages get a turn. An agenda page keeps one
dated line per item of a project. It names the project, never the item, so a
batch about the item never names it either, and the agenda page never got a
turn: the project page moved to the new date and the agenda kept the old one.
Now a project that gets a turn brings its agenda page with it, found by the
same file name or by a link to the project page, whatever source the batch
came from.

Both rules are written as tests about a made-up source, so they stay about
every source, and each fails on `main` and passes here. Neither generic file
names a source. That is also what #3040 asks for, one hook per source, and
when that hook is agreed this registry should become part of it.
