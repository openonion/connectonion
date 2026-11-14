# One comment, and the page forgot a deadline

*2026-11-14*

An Asana personal access token sees every project in every workspace its owner
belongs to. That was the first thing to settle before Asana could feed a REM
notebook: the token is not the scope. So `co rem sources add asana` takes a
project gid, never a name, and nothing is read until `co rem start` has shown
that project and the user has said yes. Adding a second project asks again.
Two projects called "Atlas" are two gids; merging them would put one team's
deadlines on another team's page, which is worse than reading less.

The rest looked mechanical. `co rem sync` asks Asana which tasks in the chosen
projects changed, saves each changed task with its comments, and hands REM the
newest saved version of each. Every claim on a page cites the exact version it
came from: account, task, the daily file and the byte offset.

Then we ran it against a real account, on two synthetic projects, and moved one
due date.

The project page moved to the new date. The agenda page, which keeps one dated
line per task, did not: the batch named the project, not its agenda, so no one
was asked to update it. Worse, a single new comment on another task, ATLAS-05,
made the project page forget ATLAS-04's new date entirely. The maintenance turn
had been told to audit every carried claim against its originals, and ATLAS-04
was not in the batch. It was not in the batch because it had not changed. The
model read "no original here" as "unsupported" and deleted a true line.

That is the lesson the source taught: a batch is what changed, not what exists.
Absence from it says nothing. The runner now refuses a maintenance page that
drops a task it cited before and was not given this time, and the repair turn
is told to put that task's lines back with their exact source entry. An agenda
line can still go once every date on it has passed, which is what the source
Skill asks for. Investigations, which read the whole saved project, still audit
everything.

The agenda page now follows its project into the turn. The same run found three
smaller faults of the same family. The reader resolved a citation to the newest
saved version instead of the one cited. A sync with nothing new pointed at
`co rem logs <id>` for a run it had not kept. The token owner's own person page
lost its "How the user writes to them" section, because the comments marked
"(you)" made the turn think it was writing the owner page. Each now has a test
that replays what the account showed.

Measured on this branch: 1,517 tests in the Asana tool, CLI and REM-source
suites pass, and `co audit co asana` passes all ten rules on all eight pages. What we have
not measured is a week of nightly rounds on a busy workspace; that is the next
thing to watch.
