# Material

Each item below starts with its source id. The page as it stands is source `investigation:page`, and the coverage note is source `investigation:coverage`.

### investigation:coverage
7 messages the user typed in codex, claude-code sessions in this project's folders, 2026-09-02 to 2026-09-26. The last activity is 2026-09-26. Only the user's own messages: no assistant replies, no tool output, no repository files.

### codex:sessions-arc:1 · 2026-09-02 — user (codex, /Users/alex/code/harbour-tides)
New project: a small CLI that prints today's tide times for a harbour, so my sailing club can check before going out. Python, reads the free BOM tide tables.

### codex:sessions-arc:2 · 2026-09-04 — user (codex, /Users/alex/code/harbour-tides)
Call it harbour-tides. Command should be `harbour-tides sydney` and print high and low tides with times.

### codex:sessions-arc:3 · 2026-09-09 — user (codex, /Users/alex/code/harbour-tides)
Cache the tide table for a day in ~/.cache so we don't hit BOM every run. They rate limit.

### claude-code:sessions-arc:4 · 2026-09-15 — user (claude-code, /Users/alex/code/harbour-tides)
Ran it at the club this morning, works. The 11 tests pass on my laptop too.

### claude-code:sessions-arc:5 · 2026-09-18 — user (claude-code, /Users/alex/code/harbour-tides)
Decision: publish to PyPI instead of sharing a zip, because club members already have pip and can upgrade with one command.

### codex:sessions-arc:6 · 2026-09-22 — user (codex, /Users/alex/code/harbour-tides)
Add a --week flag that prints seven days.

### codex:sessions-arc:7 · 2026-09-26 — user (codex, /Users/alex/code/harbour-tides)
The --week output wraps badly on phones. Make it one line per day.
