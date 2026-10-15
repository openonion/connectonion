# Session folders wait for a yes

`co rem init` maps projects by reading the first line of each Codex and Claude
Code session file under `~/.codex/sessions` and `~/.claude/projects`. That walk
ran while those sources were still `Consented: No`.

Collection already refused unconsented sources. Map metadata did not. A first
run could therefore list local session folders before anyone approved them.

The map scan now matches collection: enabled and consented, or skip. Init asks
before that walk and, if you say yes (or pass `--yes`), marks only the coding
session sources. It does not write `consent.json`, so `co rem start` still shows
the schedule summary. Declining leaves the map without session projects; the
coverage line says `waiting for approval; not scanned`.

Fixes #2443.
