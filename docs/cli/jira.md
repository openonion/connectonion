# Jira

Read Jira Cloud projects and explicitly selected issues with `co jira`. Every
command is read-only and writes no source copies or local checkpoints.

## Connect a test account

Use an account authorized to read your chosen Jira Cloud project. Start with
`co jira verify --help`. Set the site root and email, then enter the token
through hidden input in Bash/Git Bash (never paste its literal value into a
command, screenshot, chat or source file):

```sh
co env set JIRA_URL https://your-team.atlassian.net
co env set JIRA_EMAIL you@example.com
read -rsp "Jira API token: " JIRA_API_TOKEN; echo
co env set JIRA_API_TOKEN "$JIRA_API_TOKEN" --secret
unset JIRA_API_TOKEN
co jira verify
co jira projects
```

Use the email associated with your Atlassian token and a supported token with
read access. Verification checks that account, not access to every project.
For another selected configuration, retain `co --env-file PATH` on every
command. An authentication error names the safe recovery step.

## Read an explicit scope

Replace ALPHA and ALPHA-1 with keys selected from your Jira site:

```sh
co jira show ALPHA-1 --project ALPHA --json
co jira changes --project ALPHA --issues ALPHA-1 --since 2026-11-01T00:00:00Z --json
co jira issues ALPHA ALPHA-1 ALPHA-2 --json
```

`changes` requires a project; repeat `--issues` to narrow it to named issues.
Without `--issues`, it reads changes across that selected project. There is no
all-project default. `show` selects one issue; optional `--project` rejects a
cross-project key before reading. All search pages are fetched before success.
Deleted or inaccessible items are not evidence of a successful empty read.

## JSON and live citations

`changes` returns `{since, until, scope, items}`. Each item has `id`, `version`,
`time`, `title` and `link`. Pass `until` as the next `--since`; inclusive
boundaries may repeat an item, so deduplicate by id/version. The caller manages
the cursor; the command writes none.

`show` returns `id`, `title`, `text`, `author`, `author_id`, `time`, `link`,
`source` and `version`. Text is the current issue description rendered from
ADF. Comments, attachments and change history are not fetched by show/changes.
Version hashes describe the current representation; they are not saved copies.

Cite `jira:ALPHA-1` and read it with `co jira show ALPHA-1 --json`.
The content may have changed since it was cited. A missing or inaccessible
issue reports failure; no historical snapshot is substituted. REM owns source
selection and approval; a working Jira token does not imply consent to read it.

JSON data is stdout only; error and next-step messages go to stderr. Successful
reads, including an empty changes list, exit 0. Source failures exit 1 without
a partial success list; CLI usage errors exit 2. Follow the printed recovery
command before retrying.

## Limits and verification

No create, update, delete, sync, export or local snapshot store is provided.
Use `co jira <command> --help` for examples and the next command. Verify a
non-sensitive test issue, an empty changed-since window, cross-project rejection
and JSON parsing before using the source in an automated workflow. Source CLI
validation alone does not prove generic REM nightly-stage or Reader acceptance.
