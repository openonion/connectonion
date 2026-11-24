---
description: The first Granola source copied approved meeting summaries into local REM records and touched 45 files. Under the CLI JSON contract it is two read-only commands, changes and show, and REM keeps only a cursor.
tags: [REM, Granola, Sources, CLI]
---

# A source that keeps nothing

The first Granola source for `co rem` worked like an importer. It read the
approved personal folder, wrote local records holding each generated summary,
and added Granola branches to the REM sync, consent and Reader code. The diff
against `main` came to 45 files.

That made the source REM's problem. Every change to Granola's API, or to what a
user had approved, meant touching generic REM files. And a copy of each summary
sat on disk long after the user might have narrowed or removed the folder.

The owner decision in #3040, recorded as DD-081, turns this around. REM keeps
nothing from a source except a cursor. A source is just a CLI that answers two
questions in JSON:

    co granola changes --since 2026-11-01T00:00:00Z --json
    co granola show not_example123 --json

`changes` lists only metadata for notes updated after the cursor: id, version,
time and title. It never fetches a summary. `show` returns one note's summary
and its original Granola link, but only after checking that the note really sits
in the approved personal folder. Shared folders, child folders that were not
approved, deleted notes and anything outside that folder are refused.

Approval still lives in `co rem sources`. Until Granola is turned on and
consented there, neither command reads the API key or sends a request. A
failure exits 1 with an error code on stderr, so a rate limit halfway through
the second page cannot pass as a complete, shorter list. More than 1000
changes since the cursor is refused as `too_many_changes`, never truncated.

The diff is now 13 files, all Granola plus one line in `command_tips.py`. No
generic REM file knows Granola exists. 150 Granola unit tests cover the
refusals above with a fake HTTP client and no real account.

One leftover: nothing on `main` writes the approval yet, because
`co rem sources add granola` belongs to the generic caller in #3249. The
approval shape matches the OneNote source, so both can plug into it together.
