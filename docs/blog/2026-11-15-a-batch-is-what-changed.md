# A batch is what changed, not what exists

*2026-11-15, revised 2026-11-21*

We were adding a task tracker as a REM source (#3034), and the first real
account taught us something that had nothing to do with task trackers.

We moved one task's due date and synced. The project page moved to the new
date. The agenda page, which keeps one dated line per item of that project,
kept the old one. Nothing had refused it; it simply never got a turn.

The reason is how a batch picks its pages. It is given the pages its material
names: a person by name, a project by its title or by the folder a session ran
in. An agenda page names its project, never its items, so a batch about one
item never names it either. Every source has this shape, not only trackers:
the item changes, the page that lists items by date does not hear of it.

The first fix lived inside the source. Review asked the right question: is
this the tracker's problem? It is not. So the rule went into REM's lead
picking, for every source: when a project page is among a batch's pages, its
agenda page comes too, found by the same file name (`agenda/atlas.md` for
`projects/atlas.md`) or by a link to the project page.

Review found a second, quieter mistake in that first fix, twice. The first
version put each agenda right after its project and then cut the list to the
15 pages a batch may be given, so a batch naming fifteen projects lost seven of
them. Fixing the 15 was not enough: a batch updates only its first five pages,
so with five named projects the first project's agenda took the fifth
project's place, and the sync still moved its cursor past that material. The
agendas now come after every page the material named, so they only ever use
room no named page wanted, and an agenda two projects share comes once.

The same review noticed the link rule was narrower than the notebook. An
agenda page that points at its project with a `[[projects/atlas]]` wikilink,
which the reader follows, was not found. The rule now asks the reader's own
link parser, so whatever the reader treats as a link to the project, this does
too.

An earlier version of this change also taught page review about "versions"
of a record, so that a newer copy of a task could replace an older cited copy.
That half is gone. The owner decided on 2026-11-21 (#3249) that REM keeps
nothing from a source: a citation opens the item live, through the source's own
command, and there is no saved version to tell apart. What stays is the rule
that was never about storage: a batch is what changed, not what exists, and
the pages that list what changed have to be asked.

The tests use a made-up notebook, not the tracker: an agenda found by name and
by every kind of link the reader follows, another project's agenda left out, a
shared agenda added once, and batches of five and fifteen named projects where
no agenda squeezes one out.
