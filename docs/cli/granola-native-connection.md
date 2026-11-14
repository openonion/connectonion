# Granola native connection and child folders

In a local terminal, run `co rem sources connect granola` to select scope by number.
No YAML is needed; the schema below remains available for scripts with `--config`.

```yaml
folder_id: PERSONAL_FOLDER_ID
profile: personal
note_id: NOTE_ID
include_children: false
```

Choose a child folder ID directly, or set `include_children: true` to approve the
selected folder plus current and future accessible personal descendants. The
folder hierarchy is checked on each run; shared-space or unknown-personal
folders are refused before note reads. Default exact scope refuses a parent with
children because the official API recursively includes them. Standalone import
has the same explicit `--include-children` choice. Records preserve their actual
folder_id and a collection root/path for descendants; they are not relabelled as
if the note physically belonged to the parent. Old snapshots remain valid if a
folder later moves; missing rows are not treated as deletion.

Use either note_id or a limit (default 1000). A limit selects a bounded returned
prefix, not complete folder coverage; older notes outside that bound may not be
rechecked. Prefer fixed note_id for a precise update trial. The profile remains a
local label, not a vendor-verified account ID. A non-secret key binding prevents
manual/automatic imports from silently mixing keys; key changes need a deliberate
new notebook/profile, not an inferred same-account identity.

The client requests normal note detail without include=transcript and returns
only summary and allowed metadata fields. The API may transport additional
private-note/people/media fields in its response; these are discarded at the
client boundary and never persisted or supplied to REM. This is not a claim that
the vendor supports a response field mask. No transcript endpoint, audio,
attachment download, team-space collection or source write is enabled.

Automatic collection is the user's new requested mode beyond the historical
client-approved manual MVP. It is not a claim of new client approval.

Official references checked 2026-11-07: [API and key scopes](https://docs.granola.ai/help-center/sharing/integrations/granola-api),
[folder filter includes descendants](https://docs.granola.ai/api-reference/list-notes),
[note detail and transcript opt-in](https://docs.granola.ai/api-reference/get-note),
[folder hierarchy](https://docs.granola.ai/api-reference/list-folders).

See [shared setup, consent, maintenance and recovery](rem-native-sources.md).
