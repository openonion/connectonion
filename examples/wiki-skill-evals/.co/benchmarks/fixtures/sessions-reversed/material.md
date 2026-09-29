# Material

Each item below starts with its source id. The page as it stands is source `investigation:page`, and the coverage note is source `investigation:coverage`.

### investigation:coverage
5 messages the user typed in codex sessions in this project's folders, 2026-09-01 to 2026-09-24. The last activity is 2026-09-24. Only the user's own messages: no assistant replies, no tool output, no repository files.

### codex:sessions-reversed:1 · 2026-09-01 — user (codex, /Users/alex/code/rota)
Rota: a web app for our cafe to plan staff shifts. Flask.

### codex:sessions-reversed:2 · 2026-09-02 — user (codex, /Users/alex/code/rota)
Use SQLite for storage. Zero setup, one file, fine for one cafe.

### codex:sessions-reversed:3 · 2026-09-12 — user (codex, /Users/alex/code/rota)
Two managers editing at once gets 'database is locked' errors. That's a problem.

### codex:sessions-reversed:4 · 2026-09-20 — user (codex, /Users/alex/code/rota)
We're switching to Postgres. The locking errors are the reason, and the second cafe opening in November means more people editing at once. Migrate the schema.

### codex:sessions-reversed:5 · 2026-09-24 — user (codex, /Users/alex/code/rota)
Postgres migration: shifts table moved, staff table still to do.
