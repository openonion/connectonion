# Granola meeting summaries

`co granola` reads generated meeting summaries from one personal Granola folder.
It is read-only for Granola and writes no local files. Use `co granola --help`,
then each command's help, for exact syntax and recovery.

Save your personal API key once, encrypted: `co env set GRANOLA_API_KEY <key> --secret`.
Keep keys out of command history you share, scope files and logs.

## Browse

```bash
co granola verify
co granola folders
co granola notes fld-example --limit 20
```

Only personal folders (`space_id: null`) are listed. A folder read in Granola
includes its child folders, so a parent folder with children needs explicit
approval of `include_children`, and every descendant must also be personal.

## REM source commands

REM reads a source through two JSON commands (see #3249):

```bash
co granola changes --since 2026-11-01T00:00:00Z --json
co granola show not_example123 --json
```

- `changes` returns a JSON array of `{id, version, time, title}` for approved
  notes updated after `--since` (exclusive). It reads note metadata only, never
  summaries. Deleted notes are left out. An empty array is a valid result.
- `show` returns one approved note: `id`, `version`, `time`, `title`, `text`
  (the generated summary), `author`, `link` (the original Granola URL) and
  `meeting_time`. The public API names no author, so `author` is `null`.
- `version` and `time` are Granola's `updated_at`, the only revision marker the
  public API documents.

Both commands read the selection approved in `co rem sources` (the notebook's
`.state/subscriptions.json`, `granola.remote.selection`: one personal
`folder_id`, optional `include_children`, optional single `note_id`). Until the
source is turned on and consented there, they read no key and send no request.
Every call rechecks that the folder is still personal and that a shown note sits
in it.

Never returned: private notes, transcripts, attendees and their emails, audio,
attachments, or anything from shared spaces. Credential-shaped text in a title
or summary is replaced with `[withheld: possible credential]`.

## Exit codes and errors

Success prints JSON on stdout and exits 0. A failure exits 1 and, with `--json`,
prints `{"error": {"code": ..., "message": ...}}` on stderr; a failed read never
prints partial results. Invalid arguments exit 2.

| Code | Meaning |
|---|---|
| `approval_required` | Granola is not turned on and consented in `co rem sources` |
| `invalid_scope` | The saved approval is malformed |
| `invalid_since` | `--since` is not ISO 8601 with a timezone |
| `not_configured` | No usable `GRANOLA_API_KEY` |
| `auth_failed` / `permission_denied` | Granola rejected the key (401) or the scope (403) |
| `not_found` | The folder or note is missing, deleted or still processing |
| `out_of_scope` | The ID, folder or a child folder is outside the approved personal scope |
| `rate_limited` / `incomplete` | Granola throttled the read, or it did not finish; retry later |
| `too_many_changes` | 1000 or more notes changed; use a later `--since` |
| `invalid_response` / `unavailable` | Granola returned malformed data or an unexpected status |

API reference: [Granola official documentation](https://docs.granola.ai/help-center/sharing/integrations/granola-api).
