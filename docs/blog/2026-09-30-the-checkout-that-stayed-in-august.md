# The checkout that stayed in August

This morning we fixed a page that read an agent's throwaway worktree as the
project and reported a version weeks out of date. The fix pointed investigation
at the main checkout instead. Then the 1.9.0a3 acceptance run went over a copy
of the owner's notebook, and the connectonion page said the version was 1.8.0a3.

We had fixed the path, and it didn't help. The main checkout on the owner's
machine is `~/projects/connectonion`. Nobody works in it anymore, because every
session runs in a worktree of its own. It was still on
`feat/1.8-paid-browser-release`, and its `pyproject.toml` was last touched on
August 30. The folder we had called "the real one" was just the one people had
stopped opening. Git knew the real version the whole time: `origin/main` said
1.9.0a3 in the same repository.

So "which folder is the project" was the wrong question. A folder only ever
holds one branch, and the question the page needs answered is where the
project's current line is. Investigation now asks git before the model reads
anything. It records which branch each checkout is on and when its HEAD was
committed, and it finds the current line: `origin/HEAD`, then `origin/main`,
then the most recently committed branch. The version comes from that line. If
HEAD is more than two weeks older than the project's newest session, the turn
gets a plain sentence saying this checkout's files are not the current state.
Run against the owner's real machine, that sentence says 31 days.

The same run turned up two more pages built on stale input. A person's window
since her last investigation held no mail and no sessions, and a model still
spent 92k tokens on her page, only to delete one line. That window now stops
before the model with "Nothing new since" and the date. A project's file list
no longer counts as new material by itself, because a project always has files.
The people map also had pages for Airbnb, Google Cloud and X, and none of those
addresses says no-reply. What they share is a display name that matches the
sender's own domain, and mail that almost only comes in. Those are services
now. Someone writing from their own name at a domain named after them stays a
person.

In all three cases the input looked current and wasn't. So the check now comes
first, before the model: which branch this checkout is on, whether anything is
new since the last pass, and whether the sender is a person at all.
