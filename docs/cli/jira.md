# Jira

## Live source reads for REM (#3249 / DD-081)

Configure your site and account using `co jira verify --help`, enter the token
through hidden terminal input, then verify and list accessible projects:

```sh
co jira verify
co jira projects
co jira changes --project ALPHA --issues ALPHA-1 --since 2026-11-01T00:00:00Z --json
co jira show ALPHA-1 --project ALPHA --json
```

Replace ALPHA/ALPHA-1 with your explicitly selected project and issue. Omitting
`--issues` reads changes throughout the named project; omitting `--project` on
`changes` is an error. `show` selects one issue by its key; optional `--project`
rejects a cross-project key before a request. Neither command writes local files
or changes Jira. Tokens use the existing selected environment/secret store.

`changes` emits `{since, until, scope, items}`. Each item has `id`, `version`,
`time`, `title`, `link`. `show` emits `id`, `title`, `text` (description rendered
from ADF), `author`, `author_id`, `time`, `link`, `source` and `version`.
Comments, attachments and change history are not read by these two commands.
Version is a content hash of the returned representation, not a saved version.
Use `until` for the next `--since`; boundaries are inclusive, so deduplicate by
id/version. No cursor is persisted by the commands.

JSON is stdout only; next-step/error messages go to stderr. Exit 0 includes an
empty change list; source failures exit 1 without a partial list; parser errors
exit 2. Inaccessible/deleted issues are reported as unavailable, not proved
deleted. Cite `jira:ALPHA-1` and re-read through `co jira show ALPHA-1 --json`.
The current content may have changed; there is no historical snapshot fallback.

Source selection and consent remain REM's responsibility. This PR removes the
old Python Jira intake branches; it does not claim that the generic nightly
caller, source audit or Reader live citation routing has been verified for Jira.

## Separate manual exports

`co jira` reads Jira Cloud projects, selected issues and issue history. Imports
save local source records; they never modify Jira resources.

Start with `co jira --help`, then `co jira verify --help` for configuration and
temporary no-echo token setup. `co jira projects` discovers accessible project
keys. Copy issue keys from your Jira project for selected reads/imports.

| Task | Help |
|---|---|
| Check selected account/site | `co jira verify --help` |
| Discover project keys | `co jira projects --help` |
| Read named issues without source-file writes | `co jira issues --help` |
| Save selected issues or an immutable export | `co jira sync --help` |
| Repeat a project import without duplicate versions | `co jira sync-inc --help` |

Help is the current contract for flags, effects, results and recovery. Keep
`co --env-file PATH ...` when using an explicit account selection. A project
listing can be empty without indicating broken authentication.

For repeated imports, keep the same selected account, scope, output and state
directories. `--output` and `--state` have independent defaults; a custom output
alone does not relocate checkpoints. Check appended counts and checkpoint
status. A failed or partial read must not be reported as a complete import.

`--full` is a repair read with the existing cursor unchanged; it is not a reset
for corrupt or mismatched state. Preserve such files and follow help for using
separate directories. `--migrate-source` only upgrades a matching legacy source;
it does not bypass identity validation.

See [incremental query dates](jira-incremental.md) for cursor serialization and
query warning behavior. Importing source files does not establish that REM has
processed them, updated knowledge pages or refreshed the Reader. The Jira CLI
does not install a scheduler.
