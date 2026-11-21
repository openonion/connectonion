# Jira

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
