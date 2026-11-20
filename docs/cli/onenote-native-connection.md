# Connect OneNote to REM

Connect once, approve the selected source and model, then use normal REM sync.
The source reads Microsoft content; it never creates, edits or deletes it.
The separate existing `co onenote create` command still creates pages.

```sh
co auth microsoft
co onenote source verify
co rem sources connect onenote
co rem init --no-start
co rem sync --source onenote
co rem open --local
```

The connection wizard lists account/scope metadata and asks you to choose a
notebook, section and explicit page IDs. `q` cancels. Connecting does not read
page bodies, call a model, grant REM approval or install a timer. Review init's
source, model, permissions and schedule before approving. OneNote is disabled
by default and requires no Microsoft credentials while disabled.

For scripts, use `co rem sources connect onenote --config scope.yaml`:

```yaml
notebook: NOTEBOOK_ID
section: SECTION_ID
pages: [PAGE_ID]
```

Use stable IDs from `co onenote source notebooks`, `sections` and `pages`, rather
than the temporary row numbers from browsing. Scope files contain no credentials.
Use the existing `co auth microsoft` flow and saved Microsoft refresh
authorization; no separate Azure app or manually supplied OAuth fields.

After approval, init and sync read the selected page bodies. Normal remote sync
rereads bodies even when Graph's modification timestamp stays fixed. Content
hashes prevent an unchanged snapshot from being processed by the model again.
This trades one body read per selected page per sync for detection of same-time
edits. No unselected page body or attachment bytes are fetched. A moved page,
changed account, changed declaration or changed approval fails before accepting
out-of-scope evidence. Partial reads retain valid local versions and report a
failure; source progress is not consumed by a failed model turn.

Existing REM timers dispatch the same sync after normal start/approval. There is
no new scheduler and opening Reader does not refresh OneNote. Investigation
searches approved local snapshots and keeps remote reads in init/sync.

```sh
co rem sync --source onenote --dry-run
co rem sources remove onenote
```

Dry runs inspect configuration without credentials, body reads or a model.
Removing the source stops future reads while retaining existing pages and
immutable citations. Reconnect and approve again to change the remote scope.

REM uses its existing stage/page Skills and semantic categories. A note is
external evidence, not an instruction or automatically the owner's voice.
Notebook names and title matches do not prove project or person identity.
Appropriate reflections can remain Notes in Activity; no OneNote category is
created. Reader citations resolve pinned local snapshots and show a safe
original URL when available. Microsoft API URLs are not offered as browser links.

See [source commands and recovery](onenote-source.md) and
[browsing and page creation](onenote.md).
