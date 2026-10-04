---
description: One REM page reread the same coding sessions each time the CLI restarted. A local parsed window cut a repeat source pass from 103.5 to 2.1 seconds without hiding new input.
tags: [REM, Performance, Design]
---

# A window that survived the command

A page had already been mapped. Its sources were on the same laptop. Yet
running `co rem investigate` again began by walking the coding sessions as if
the page had never been seen. On a 90-day notebook that meant waiting more
than a minute before the page writer could even begin. A second invocation
paid the same wait.

The map did have a source inventory, but it held paths and dates, not the
words someone typed. Those pointers could say which session file existed;
they could not answer whether a person or project was mentioned inside it.
The investigation also kept a parsed window in memory for ten minutes. That
helped several pages in one process, then vanished as soon as the CLI exited.

We kept the parsed typed inputs beside the notebook, with the per-file read
position that the existing importer already understood. A later command
checks the source files, reads changed tails and new files, and narrows that
saved window to the page's requested dates. It still looks at source changes
every time. The original source ID remains the session and byte offset, so a
speedup does not turn an old citation into a new one. If a session file goes
away, the derived window rebuilds without it.

The first measurement seemed to prove we had fixed nothing: 103 seconds,
then 104 seconds, with no cache file in sight. The probe script lived under
`/tmp`, and Python imported the installed a33 package instead of the edited
checkout. Once the probe explicitly loaded the candidate, its first pass
took 103.5 seconds and counted 2,050 Codex plus 2,907 Claude Code typed
messages. A new process found the same counts in 2.1 seconds. A separate
source test appended an input, added a session file, removed one, and checked
that the old source ID did not change.

The private window is about 4.6 MB for that sample and lives under the
notebook's owner-only `.state/` directory. It contains the typed text needed
for matching, not the full tool-output transcripts, and it stays out of
reader exports. This trial measured source collection only. It did not write
the 255 pages still unfinished in the broader first run, or establish that
their claims are sound. The lesson is narrower and useful: remember parsed
evidence across commands, but let the source files decide whether it is still
current.

The [a34 preview notes](https://docs.connectonion.com/releases/1.9.0a34)
give the exact install pin and trial limits.
