---
description: A fresh map read 26 GB of coding sessions four times, once for each thing that needed them. Now it reads them once, and the four outputs are the same, byte for byte.
tags: [REM, Performance]
---

# One read, four readers

Four parts of a fresh init need the owner's coding sessions. The skill map
counts invocations. Project filing puts typed messages under their projects.
The session import writes a page per conversation. The session cache keeps
typed messages for investigations. Each opened every session file itself:
about 20,500 files and 26 GB on this machine. On a fresh init that came to
four reads.

Now the map reads each file once, at the start, and hands the same bytes to
all four. Each still applies its own window and skip rules after reading: 180
days for skills, filing and the import, two years for the cache. Filing's
folder-dependent step still runs later, when the project pages exist, but on
results already parsed. A Codex session that marks itself as REM's own turn on
its first line is read only that far, because every reader stops there.

To show nothing changed, we ran the old readers and the new pass on two copies
of the same notebook, against a frozen copy of the session stores. The files
were cloned in place, with their times kept. Every output matched:

- skill-usage cache and counts
- filing's returned counts, the 121 files of project material, and the 40 project pages
- the import's report, `sessions.json` and all 303 session pages
- both session-window caches, item for item and checkpoint for checkpoint

The only differences were a timing field and the window's start time, which
the old code took from the clock. Together the four reads took 49 minutes on a
busy machine. The single pass and what follows from it took 16.

Two smaller things went with it. Session summaries and the mail-body download
now run side by side, since both mostly wait on servers. And the session cache
is no longer built in a separate process during init: the pass writes it.
