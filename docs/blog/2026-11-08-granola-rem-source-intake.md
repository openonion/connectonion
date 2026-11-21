# Granola source intake for co rem

This change adds a read-only Granola source to ConnectOnion and wires it into
the existing co rem consent, sync, investigation, and Reader workflow.

The CLI uses a user-managed `GRANOLA_API_KEY`. It lists only personal folders,
requires an explicit folder selection, and writes canonical local records that
contain generated summaries, meeting time, Granola URLs, and folder metadata.
It deliberately excludes transcripts, private notes, audio, and attachments.

`co rem sources connect granola` records a selected scope but does not approve
body reads or run a model. The existing `co rem init`/`co rem start` consent
flow remains the only path that approves a connected source. After approval,
the existing REM sync and scheduler can refresh the selected scope; no separate
scheduler or Reader-open refresh hook is added.

Granola evidence is consumed through the existing semantic maintenance and
investigation path, so resulting material belongs in existing People,
Organisations, or Projects pages rather than a new Reader category.

Before enabling an account, run the relevant unit tests, CLI help checks,
benchmark and eval for `co-granola` and `rem-source-granola`, then perform the
manual selected-folder checks with an authorised personal account. Never put an
API key into command history, fixtures, screenshots, or this repository.
