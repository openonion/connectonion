# OneNote source commands

These commands read explicitly selected Microsoft OneNote content into local
source records. They accept `Notes.Read`, `Notes.Read.All`, or existing compatible
broader grants through the existing Microsoft authorization and refresh flow.
They never write to OneNote or call a model. Images and attachments remain
metadata only, including names, MIME types, sizes and safe fetch references.

```sh
co onenote source --help
co onenote source verify
co onenote source notebooks
co onenote source sections NOTEBOOK_ID
co onenote source pages NOTEBOOK_ID SECTION_ID --limit 100
co onenote source sync NOTEBOOK_ID SECTION_ID PAGE_ID --output ./note-source
co onenote source sync NOTEBOOK_ID SECTION_ID PAGE_ID --output ./note-source --full
co onenote source sync NOTEBOOK_ID SECTION_ID PAGE_ID --output ./note-source --mode export --export-id snapshot-1
```

Each command supports `--json`. Listings follow pagination; a bounded page list
reports `truncated` rather than claiming complete coverage. Sync requires explicit
page IDs and validates each page's current notebook/section parents. Browsing
row numbers are not source IDs.

Daily imports append versioned JSONL under `daily/YYYY/MM/DD.jsonl`. The committed
daily files are the checkpoint across dates and interruptions. A normal manual
import skips already saved modification timestamps; `--full` rereads the selected
bodies and saves only changed content. Native REM sync always uses this full
body-check path. Changing ingestion mode/path alone does not repeat REM work.

Export mode rereads selected pages into `exports/ID/records.jsonl` plus a manifest.
Export IDs are exclusive; choose a new ID instead of overwriting an old export.
`--full` is only meaningful in daily mode. `source.yaml` records account, scope,
read-only/media policy and validation provenance; it is not a credential file.
Use separate output directories for different accounts or sections. Preserve
corrupted files for diagnosis instead of silently resetting checkpoints.

| Exit | Meaning | Recovery |
| --- | --- | --- |
| 0 | Success, including empty/no change | Inspect written/skipped counts |
| 1 | Auth, scope, provider or storage failure | Follow `recovery_action`; authorization uses `co auth microsoft` |
| 2 | Invalid command syntax or partial/page failures | Inspect errors and retained valid records; use command help |

An API timeout or denied page is a failure, never an empty success. Transient
HTML reads honor bounded `Retry-After` handling; a long requested wait is reported
for manual retry. Authorization can refresh once. Error receipts avoid provider
response bodies or credential values.

For the ordinary automatic workflow, use [native connection](onenote-native-connection.md).
Existing imported records can also be subscribed from a notebook's `docs/onenote`
with `co rem sources add onenote`, then approved in init. Changed account/scope
declarations require renewed approval. Manual source imports alone do not prove
REM processing, model quality, Reader freshness or timer execution.
