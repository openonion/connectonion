# Where the session actually worked

Earlier today the notebook learned to write project pages from what the owner
types to Codex and Claude Code. The measurement that shaped it also carried a
number nobody liked: 590 of his 1,359 messages, 43%, reached no page at all.
They were typed in `~/projects`, the folder that holds six of his repositories.

That was on purpose. `~/projects` is not a project. It is where he opens a
session before deciding which repository to work in, and the map has a rule
that recognises it: agent instructions at the top, no `.git` of its own, two or
more repositories inside. A page for "projects" would be a page about
everything, which is a page about nothing. So those messages were skipped,
counted and listed as excluded. Correct, and nearly half of what he said went
unused.

The way out was already in the files. A session started in the workspace does
not stay there. It reads `connectonion/wiki/scan.py`, runs `git -C onionwright
status`, edits a file in a worktree. Every one of those tool calls names a path,
and the path says which repository the work was in. The folder where he typed
was the least informative fact in the session. The tool calls after it were the
most informative.

So the rule changed from "where was it typed" to "where did it work". A script,
still no model, reads the calls a workspace session made: Codex's `exec` and
`shell` calls and its `turn_context` when the folder changes, Claude Code's
`Read`, `Edit`, `Write` and `Bash` inputs, and the `cwd` on each row. It never
reads a call's output, and never the text an edit wrote, because a path in the
output is not a place the agent went. Each path goes to the deepest project
folder that holds it, which is a folder on a page or a folder with its own
`.git`, so a worktree counts as a worktree and not as its parent. Each message
goes where its own turn worked most. A message with no tools in its turn, like
"thanks, what is left?", goes where the whole session worked most. A session
that touched no repository stays out, as before.

Then we ran it on his machine, read only and counting only. 250 of the 590 were
placed, into 24 project folders, and 8 of the 21 sessions were split across two
or more repositories. That is the case the rule was built for. 340 still stay
out, and the reason was not what we expected. 312 of them are in 22 Codex
Desktop threads that contain no tool calls at all, only messages. The work
happened somewhere the thread file does not record. The assistant's replies in
those threads do name paths, and counting them would place 282 more. We left
that out on purpose. A reply that mentions a file is the agent talking about a
place, not working in it, and the owner should decide whether that is good
enough evidence.

The second change was smaller. A folder with his messages and no page used to
be counted and left alone, because only the map made pages. Now a folder active
in the last 14 days gets a page, made by the map's own function so the stub,
the record name and the grouping of worktrees under their repository are the
ones `co wiki init` would have produced. Older folders are listed, not created:
"14 more folders with messages and no page; not created (older than 14 days)".

The lesson is about which fact to trust. The folder a session was opened in is
recorded once, at the start, before any decision is made. The paths it touched
are recorded as it works. When the two disagree, the second is the better
record of what the session was about.
