# Completed, zero tasks

*2026-11-16*

The owner asked why 1,328 mails were waiting to be read. We went to look at the
queue and found something else: the night had not done any work since the 14th.

Every fifteen minutes the schedule started a round. Every round stopped while it
was being prepared, with the same line:

```
Permission denied: '/System/Volumes/Data/.fseventsd/.git'
```

That folder belongs to macOS. It records which files changed on the disk, and
only root may open it. REM had no business there, and had not chosen to go. It
reads coding sessions, takes out anything that looks like a folder path, and
asks of each one whether it is a repository, so it can tell which project a
session was about. On 2026-11-13 one session's text contained that path. A
folder that does not exist answers "no". A folder you may not look inside
answers with an error, and nothing caught it. The session text does not go
away, so the next round met it again, and the next. Sixty-six rounds.

The owner's first question was the right one: who refused, Codex? No. Codex
with full access has the owner's permissions, not root's, and the refusal came
from the operating system to REM's own Python. No setting would have fixed it.
The fix is one sentence of policy: a folder REM cannot read is not a
repository. It is now applied at every place the question is asked, thirteen of
them, each with a test.

The worse half was what the records said. Each failed turn was saved as
`completed`, exit 0, because the agent that runs the turn finished politely
after explaining that it could do nothing. The night's summary read 33 turns,
0 tasks accepted, 0 mail read, and offered no reason. Nothing on any screen
said the night was broken; it read as a quiet one.

A turn that prepared nothing now says failed and keeps its error. `co rem
status` counts how many in a row and since when, in a sentence, and so does
Today. The fix cannot repair the sixty-six that came before; they stay
recorded as completed.

Two other jobs turned out to be missing from the same background path, and we
found them the same way, by asking why a page was empty: pages had not been
deepened since 2026-11-07, and the calendar had never been saved, so Agenda had
nothing to show. Those are fixed on a branch and follow in the next release.
