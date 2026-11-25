# Jira live source commands

The previous local-snapshot REM intake described here was retired in response to
[#3249](https://github.com/openonion/connectonion/issues/3249), including its later
owner update: REM keeps no source copies or saved versions.

Read [the Jira CLI guide](../cli/jira.md) for setup and explicitly scoped live reads.
For acceptance, use [the current live-source checklist](../acceptance/jira-live-source.md).

`co rem sources connect jira` is no longer supplied by this PR. The live boundary
is `co jira changes --project KEY --since TIME --json` and `co jira show KEY-1 --json`.
Manual `sync` / `sync-inc` exports are separate opt-in tools, not REM storage.
