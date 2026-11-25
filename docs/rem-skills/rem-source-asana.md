# Why rem-source-asana says what it says

The rules live in `connectonion/useful_skills/rem-source-asana/SKILL.md`,
appended to a stage's instructions when the material comes from Asana
(`rem-source-<kind>` in `rem/runner.py`). This file holds the reasons; it is
not loaded at runtime (#1851).

## One item is the task now

A REM source is its `co` command, and REM keeps nothing from it (design
decision 081, #3249). Asana answers `co asana changes --since <time> --json`
with the tasks changed since then and `co asana show <id> --json` with one task
as it is now. So an item is the current state of a task, not an event, and a
task seen again replaces, rather than adds to, what was written from it:
otherwise a moved due date would leave two deadlines on the agenda. A citation
is `asana:<task id>` and opens live; if the task changed since, the reader says
so.

By default `changes` reads the tasks assigned to the user, in every workspace:
Asana answers that in one request per workspace, and it is what a personal
notebook is about. `--project` reads whole projects instead. Deleted tasks are
not listed at all.

That default has a blind spot, written into the Skill rather than hidden: a
task reassigned away from the user is no longer "assigned to the user", so the
change that took it away is never listed. That is one more reason a missing
task proves nothing, and why a page keeps its lines about it as they are.

`(you)` is matched by Asana user ID, not by name. The first version of `show`
gave only names, and two people called Alex would both have looked like the
user; only the user's own comment can be their commitment, so the mark has to
be certain. Completion is dated by `completed_at`, because a comment written
after a task was completed moves its `modified_at` later.

## A batch is not the whole account

A batch holds only what changed, a few at a time. So a task, person or project
missing from one batch may simply be unchanged or due in a later batch. The
WhatsApp wording ("missing means not chosen") was wrong here: absence proves
neither that something was not selected nor that it was deleted.

On a real account, one new comment on ATLAS-05 made a maintenance turn delete
ATLAS-04's moved due date from the project page: ATLAS-04 was not in the
batch, and the turn read "no original here" as "unsupported" (2026-11-14).
That is why a task not in the material keeps every line, and why an agenda line
changes only when its task is in the material: taking off a past-dated line of
a task that did not change would drop its citation, and an open task past its
date is overdue, not done.

## Comments belong to their authors

A task gathers several people's words under one title. Attributing a comment
to the assignee, or to the user because the task is "theirs", puts a promise
in the wrong mouth. Each comment line carries the author's name and gid, and
the token owner's lines are marked `(you)`, so the rule can be followed
without guessing.

## A due date is a deadline; an assignment is not a commitment

In Asana anyone in a project can assign a task to the user and give it a date.
The user may never have seen it, or may have declined it in conversation
elsewhere. Recording every assigned task as the user's promise would fill the
agenda with other people's wishes. The same split as mail: a request is the
requester's until the user answers it. A `(you)` comment that accepts the task,
or a date the user set in their own words, is the evidence of agreement.

Who assigned a task is not in the material: Asana records the assignment as a
system story, and `co asana show` only counts those. The assigner can be named
only when a comment says so ("Assigning this to Alex"); otherwise a model asked
to "say by whom" would invent a name, usually the most active commenter. The
`asana-unknown-assigner` fixture checks exactly this.

Deadlines go on one rolling agenda page per project, a dated line per task,
because rem-maintain already forbids one page per transaction, and Asana
projects routinely hold hundreds of tasks.

## Completed is a status

Completion is recorded by Asana's activity, not by a decision. It takes the
line off the agenda; making it a "decision" would turn every finished chore into
a page entry. When the line was already in the notes, one "done" line replaces
it, so the next pass sees the deadline was met rather than wondering whether it
was forgotten; a completed task never on the agenda adds nothing. The first
wording said both "drop the line" and "close the line", and in evaluation the
model spent its whole step budget searching for which one was meant.

## Evidence, not instructions

Descriptions and comments are written by many people, some outside the user's
organisation, and are material like a mail body. An instruction inside them is
not followed (the same rule as rem-maintain's).

## Checking a task now

The client asked that the nightly rounds' Skills know the tools each source
adds (meeting 11-05, Aaron's mail 11-10: pages were thin). A turn may check a
task it already cites with the read-only `co asana show` / `co asana stories`.
The id must come from an `asana:` citation, never from a description or
comment, because a token sees every project and an id in text is an
instruction in disguise. Writes (`update`, `comment`) are never part of a
notebook turn.

## The example

The example shows the shape a reader can check: the deadline with the evidence
of agreement, and a waiting-for line that stays on the other person, each with
its source id as the Codex example keeps them.
