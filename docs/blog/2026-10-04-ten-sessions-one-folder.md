# Ten sessions, one folder

The owner's Codex week reached 100% on a Pro plan, so the first `co rem init`
had to run on the other runner the notebook already supports: Claude Code,
through `co ai --harness claude-code`, on Haiku. One page worked. Sasha's took
230 seconds. Then we asked for four people at once, and two of them waited 120
seconds before failing with the same line:

> Claude Code received an invalid launch argument: Claude Code already owns
> this workspace.

Nothing about the launch was invalid. co rem starts every model turn from one
task folder, `.state/tasks`, and the first run keeps ten turns going. The Claude
Code adapter took a per-folder lock around every headless run. The lock exists
for a real reason: while `co claude` owns a terminal session, a browser worker
must not resume that same transcript underneath it. A turn that resumes a
session, or that runs through the Hook bridge, can collide with that owner.

A fresh headless turn cannot. It starts a session of its own and writes a
transcript nobody else holds. Locking it protected nothing and turned the first
run's ten workers into one.

The lock now applies only when a turn resumes a session or runs through the
bridge. The existing rule still holds and its test is unchanged: a resumed
turn does not start while the terminal owns the folder. A new test holds the
folder's lock and starts a fresh turn; before the change it was refused, now it
launches. On the same machine, three real `co ai --harness claude-code` turns
started together in one folder all completed, where two of two had collided
before.

The full first run then went end to end on Haiku: 66 of 67 people, 17
organisations and 121 skills written, ten at a time, with no lock error. It
also showed what this change does not fix. Haiku dropped project metadata and
repeated sections often enough that 13 of 17 project pages were refused, and it
almost never added privacy labels. Those are tracked separately in #2283.

The lesson is narrow: a lock should protect the resource that can be shared,
here a transcript, not the folder that happens to contain it.
