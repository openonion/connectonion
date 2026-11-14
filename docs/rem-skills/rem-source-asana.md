# Why rem-source-asana says what it says

The rules live in `connectonion/useful_skills/rem-source-asana/SKILL.md`,
appended to a stage's instructions when the material comes from Asana
(`kind = "asana"`, set by `rem/asana.py`). This file holds the reasons; it is
not loaded at runtime (#1851).

## One item is the task now

`co rem sync` first collects the selected projects' changed tasks
, then gives REM each task's newest saved version.
Intermediate versions are never read, so an item is a snapshot of state, not
an event. A task seen again therefore replaces, rather than adds to, what was
written from it: otherwise a moved due date would leave two deadlines on the
agenda.

## A batch is not the whole project

An Asana token sees every project in its workspaces; only the ones named with
`co rem sources add asana --project` are collected, and a sync gives REM only
the tasks that changed since they were last read, a few at a time. So a task,
person or project missing from one batch may simply be unchanged, already read,
or due in a later batch. The WhatsApp wording ("missing means not chosen") was
wrong here: absence proves neither that something was not selected nor that it
was deleted (deletions are not collected at all).

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
system story, and `rem/asana.py` only counts those. The assigner can be named
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

## Checking a task now (2026-11-13)

The client asked that the nightly rounds' Skills know the tools each source
adds (meeting 11-05, Aaron's mail 11-10: pages were thin). Collection stays in
`co rem sync`, which reads only approved projects; a turn may check a task it
already cites with the read-only `co asana task` / `co asana stories`, so a
doubtful line can be confirmed. Two limits keep this safe. The gid must come
from an `asana:` citation, never from a description or comment, because a token
sees every project and a gid in text is an instruction in disguise. And the
page cites saved versions only: a fact that only the live read shows cannot be
checked by the citation audit, so it stays out until a sync collects it. Writes
(`update`, `comment`) are never part of a notebook turn. The same lines reach an
investigation through its Asana scope note, and the source CLI reference
(rem-init/CLI.md) names the commands for the first run. Cost: about 600
characters on a turn that already carries Asana material.

## Instruction size

Appended to a one-page maintenance turn over raw items, this Skill takes the
turn from about 14.3k to 18.4k characters (person) and 15.0k to 19.1k
(project) since the check-a-task section (it was 17.2k / 17.8k), above the 15k
aim of #1851. The same is true of rem-source-codex
(17.0k) and rem-source-whatsapp (16.7k): the turn-assembly path, not this file,
is the cause, and #2000 fixed it only for turns over extraction notes. Kept
here as a known, shared limit rather than worked around by stripping rules.

## The example

The example shows the shape a reader can check: the deadline with the evidence
of agreement, and a waiting-for line that stays on the other person, each with
its source id as the Codex example keeps them.
