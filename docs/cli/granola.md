# Granola Meeting Summaries (`co granola`)

`co granola` reads generated meeting summaries from your personal Granola
folders over Granola's public API v1. Every command is strictly read-only:
nothing in Granola or on local disk is modified.

## Setup

Create a personal API key in Granola settings and save it to your encrypted
ConnectOnion store:

```bash
co env set GRANOLA_API_KEY grn_... --secret
co granola check
```

`GRANOLA_API_KEY` is resolved in standard `co` order: process environment first,
then the active `.env`, then the encrypted `--secret` store.

## Browse Personal Folders and Notes

```bash
co granola folders
co granola notes fld_example --limit 20
co granola show not_example --folder fld_example
```

Only personal folders (`space_id: null`) are listed or read; shared-space
folders and notes are always refused. Because Granola's API includes child
folders when listing a parent folder, querying a folder with subfolders requires
`--include-children` (and verifies every descendant folder is also personal).

## REM Source JSON Commands

`co granola` implements the standalone CLI source contract (DD-081) with
explicit `--folder` scope on the command line and zero coupling to REM's
internal state files:

```bash
co granola changes --since 2026-11-20T00:00:00Z --folder fld_example --json
co granola show not_example --folder fld_example --json
```

- `changes --json` returns `{"since": "...", "until": "...", "items": [{"id", "version", "time", "title", "link"}]}` ordered oldest `updated_at` first. `until` is captured before the read starts so callers pass `until` as the next `--since` without missing concurrent edits. Deleted notes are excluded.
- `show --json` accepts `<id>` or `granola:<id>` and returns `{"id", "version", "time", "created", "meeting_time", "title", "text", "author": null, "link", "folder_id"}` live from Granola.

## Privacy Boundaries & Exit Codes

Private scratchpads, verbatim transcripts, attendee emails, audio, and media
attachments are stripped at the client boundary and never returned. Any title or
summary matching a known credential token pattern is replaced with
`[withheld: possible credential]`.

- **Exit `0`**: Read succeeded (including an empty list).
- **Exit `1`**: Missing/rejected key, shared-space or out-of-folder scope refusal, rate limit, or incomplete pagination (stderr prints the error and `Next:` recovery command; stdout emits no partial JSON).
- **Exit `2`**: Invalid CLI argument (for example `--since` without a timezone).
