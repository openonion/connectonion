# Asana is two commands now

*2026-11-21*

A week ago, getting Asana into a REM notebook took a store. `co rem sync`
asked Asana what had changed in the chosen projects, saved every changed task
with its comments in daily files under `~/.co/inbox/asana`, and handed REM the
newest saved copy. Each line on a page cited the exact copy it came from:
account, task, daily file, byte offset. Then the store needed a lock, the lock
had to be ordered against the notebook's own lock, a busy notebook could make
a fetch wait ten minutes, and the whole thing was being moved onto a shared
protocol of nine functions per source. The Asana pull request had grown to 85
files, and most of them were about keeping a copy of something Asana already
keeps.

The owner's question on 2026-11-21 was short: the command's output is the
status, so why does code need to describe the source a second time? And then a
shorter one: why keep the copy at all? A REM source is now its `co` command,
and REM keeps nothing from it (design decision 081).

So Asana became two read-only subcommands. `co asana changes --since <time>`
lists the tasks that changed after that time, oldest first, and says in
`until` when it began reading, so the next run picks up from there without a
gap. `co asana show <id> --json` reads one task as it is now: its description,
every comment oldest first with its author, and how many times Asana itself
recorded activity. A citation is `asana:<task id>` and opens through `show`.

The hard part was not the code. It was deciding what `changes` reads when no
one says. REM calls it with nothing but a time, and an Asana token sees every
project in every workspace its owner belongs to. Reading all of them would be
slow on a big account and would put other teams' tasks into one person's
notebook. We chose the tasks assigned to the user, one request per workspace:
that is what a personal notebook is about. `--project` reads whole projects
when someone wants more. The price is a blind spot: a task reassigned away from the
user stops being "assigned to the user", so that change is never listed. The
Skill now says a missing task proves nothing at all, rather than "unchanged".

We also lost something on purpose. The old store could show the exact text a
page cited; a live read shows the task as it is today. The task's `time` tells
a reader it changed since it was cited, and design decision 081 accepts that.

Review of the first version caught something subtler. `show` gave each
comment its author's name, and the Skill decides whether a comment is the
user's own promise. Two people named Alex would both have looked like the user.
Each comment now carries the author's Asana ID and a `you` flag matched by ID,
and a completed task carries `completed_at`, since a later comment would make
its last-changed time look like the day it was done.

And Asana documents that a new comment updates a task's `modified_at` but does
not promise the same for an edited one, so an edited comment may not appear in
`changes`. That limit is written in the docs, not hidden.

The pull request went from 85 files to a handful. The Asana source Skill kept
every rule the real-account runs taught us (a batch is what changed, not what
exists; an assignment is not a promise; a completed task closes its agenda
line) and lost every word about daily files and offsets. What is not measured
yet is the whole chain on a fresh install, from `co init` through a night's
pages that cite `asana:<id>`: that waits for REM's side of the same decision.
