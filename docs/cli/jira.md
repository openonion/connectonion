# Jira CLI

The Jira CLI is read-only. It lists accessible projects and reads only the issue keys you explicitly name.

```text
co env set JIRA_URL https://your-domain.atlassian.net
co env set JIRA_EMAIL you@example.com
co env set JIRA_API_TOKEN --secret --prompt
co jira verify
co jira projects
co jira issues ALPHA ALPHA-1
co jira sync ALPHA ALPHA-1
```

`sync` writes `source.yaml` and JSONL records below `~/.co/rem/docs/jira` by default. Use `--output` for a different local directory and `--json` for machine-readable successful and failure output. The command does not modify Jira, install a scheduler, or refresh the reader.

If credentials fail, follow the `Next:` recovery command. Never put an API token into a command argument or commit it to a file.
