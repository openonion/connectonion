# Jira incremental query dates

`co jira sync-inc` reads issues in the selected project/key scope and writes
versioned canonical records. It does not generate Markdown profiles or open
the Reader. Open the selected notebook separately with:

```bash
co rem --root /path/to/notebook open --local
```

Jira does not accept a quoted ISO timestamp such as
`updated >= "2026-11-05T11:57:00.473000+11:00"`. Incremental cursors with a
timezone are now serialized as unquoted epoch milliseconds, preserving the
instant across Jira account timezone settings. The example becomes
`updated >= 1793840220473`. Sub-millisecond precision is rounded down so a
boundary update cannot be skipped. Date-only and timezone-free inputs use
Jira's quoted calendar date format and retain Jira account-local semantics.
The cursor itself remains an ISO timestamp; existing checkpoint files do not
need to be deleted or rewritten.

See [Atlassian's Updated field reference](https://support.atlassian.com/jira-software-cloud/docs/jql-fields/#Updated)
for supported date and unquoted epoch values.

Search warnings/errors or a missing issues array fail the read instead of
reporting a successful empty result. The incremental transaction preserves
the previous cursor when the read fails.

A repeat sync can read records inside the two-minute overlap while adding
zero versions. Compare `net_new_records`, not only `issues_read`.
`--full` performs an explicit complete read and leaves the existing incremental
cursor unchanged; it is a recovery operation, not evidence that an incremental
update succeeded.
