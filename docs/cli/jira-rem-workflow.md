> Updated 2026-11-07: opt-in native remote collection is now implemented.
> See [one-time connection and scope selection](jira-native-connection.md).
> The manual import commands below remain diagnostic/recovery workflows. Live
> account, real edits and actual timers for the new intake path are pending.

# Jira imports in the normal REM workflow

Jira CLI collects selected issues. REM subscribes to the resulting **local imports** in the selected notebook and uses its existing Init → Investigate → Maintain workflow. Reader displays the resulting People and Projects pages. No bridge script is required.

```sh
NOTEBOOK=/path/to/notebook
co jira sync-inc --project DEMO --issues DEMO-1 \
  --output "$NOTEBOOK/docs/jira" --state "$NOTEBOOK/.state/jira-cli" --no-history
co rem --root "$NOTEBOOK" sources add jira
co rem --root "$NOTEBOOK" init --no-investigate --no-start
co rem --root "$NOTEBOOK" investigate projects --limit 1
co rem --root "$NOTEBOOK" sync --source jira --all
co rem --root "$NOTEBOOK" open --local
```

Configure Jira using [the existing Jira CLI instructions](jira.md). `--no-history` is optional; omit it to collect issue history. `co jira sync` selected imports and exports are also supported. Their `source.yaml` must declare the same account and selected scope as every record in `docs/jira`. Use a separate notebook for a different account/scope; arbitrary outside directories and symlinks are refused.

`init` shows the existing approval summary. Review all enabled sources, model, permissions and schedule before approving: a new notebook can also have coding sessions selected and offer connected mailboxes. Remove any unwanted sources with `co rem sources remove NAME`. `--no-start` keeps the timer off. Noninteractive `--yes` explicitly approves the summary; it is not required for an interactive run.

Init creates canonical stubs for the Jira project and explicitly identified reporters/assignees. Same display names do not merge people. Existing page bodies and project Paths remain intact. Project names use the imported project key in this baseline; a separate project-name change is not included.

Investigate reads only snapshots for that mapped identity, within its requested time window. Maintain reads one changed issue per bounded batch so its project and up to two people fit the existing page budget. `--all` catches up through successive batches while respecting the existing daily quota. A repeat without changed record content calls no model. Supplied immutable snapshot references are preserved, including dated source descriptions.

Refresh local data by repeating the normal Jira import command, then run REM sync. REM's existing background timer can consume approved local imports; this integration does **not** poll Jira remotely. Adding Jira does not install another timer or attach work to Reader opening.

If a new reporter/assignee needs a page, sync preserves progress and asks for another normal Init map. If a target is cooling or belongs to the existing project writer, its version stays pending: wait for the cooling period, or explicitly investigate the page before retrying. A daily budget too small to handle all target pages also leaves the version pending. Do not delete source files, checkpoints or consent to recover.

Full records, source ownership and pinned references are validated before consumption. The existing imported-evidence size limit and normal batch limits apply; oversized evidence is refused, never truncated into a successful import. Corrupt/out-of-scope files stop this source with its progress preserved. A failed model with no accepted page leaves progress unchanged; existing post-write failure recovery and refusal-material retention remain in force.

Reader excerpts are short display views. Jira claim audits instead read complete pinned canonical records, including workflow status and history, through the existing evidence resolver. Audit and page-shape checks remain enabled. This prevents a Reader lookup status such as `resolved` from being mistaken for Jira workflow status.

Current scope is Jira consumption. OneNote/Granola development is tracked on independent feature branches; their CLI remediation deltas and normal REM consumption are separate work. Deletion/archival inference, automatic remote polling, exhaustive prompt-injection resistance and live edited-source acceptance are not claimed by this change.
