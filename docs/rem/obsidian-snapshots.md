# Single-vault Obsidian REM source

This draft connects one notebook to one Obsidian vault through the
[shared source hooks](source-interface.md) in
[#3228](https://github.com/openonion/connectonion/pull/3228). The alignment uses
the published shared commit `f9d5f156`, which includes upstream `main` at `ffe3f133`
and the follow-up fixes from Asana's review.
It reads notes and stores snapshots;
it provides no vault write commands or multi-vault REM subscription.

## Select, approve and collect

```bash
co rem --root /Users/example/Notebook sources add obsidian --vault /Users/example/Vault --folder Work
co rem --root /Users/example/Notebook sources
co rem --root /Users/example/Notebook collect --source obsidian --dry-run
co rem --root /Users/example/Notebook start
```

Registration validates explicit folders but does not read note bodies. The adapter
returns selection metadata; the shared configuration writer saves it and clears
approval when the selection changes. The notebook must be outside the vault.
Interactive start displays the scope and model routes, then records approval directly;
it does not prompt for y/n. An unapproved noninteractive start requires explicit
`--yes`. Start can run the first batch and installs a schedule.
Use `co rem --root /Users/example/Notebook stop` to stop that schedule after a demo;
manual collection remains available. Approval includes the effective stage model
routes, so changing one requires approval again before saved notes reach that model.

```bash
co rem --root /Users/example/Notebook collect --source obsidian
co rem --root /Users/example/Notebook sources remove obsidian
```

Selection changes clear approval. A different vault requires explicit `--replace`;
this replaces the one selection, rather than adding a second vault. Removing the
source blocks subsequent dispatch and citations. It does not delete notes, historical
snapshots or already generated notebook pages.

For a demo with only the Obsidian subscription enabled, first unsubscribe every other source in a dedicated
notebook. Disabled default sources can remain visible in the list. Selecting
`--source obsidian` for one collection does not change the notebook's other subscriptions.
Collection processes one batch; repeat it while saved material remains pending.
Approved coding-session imports and unfinished mail-archive work can also run
outside that batch. The source option does not limit that housekeeping.
Subscriptions govern source collection, not all tools available to the shared
investigation runner. See the investigation limitation below.
See the [step-by-step validation guide](obsidian-validation.md).

## Acquisition and offline consumption

The store's low-level `collect` scans only selected folders and atomically saves
snapshots. Public REM calls it through `obsidian_source.fetch`, with approval checked
at the storage boundary. It refuses symlinks and system folders through the existing
read-only CLI reader. An incomplete scan fails before any snapshot writes.

A source-specific writer lock serializes scans. The scan runs outside the notebook
lock. Publication takes the shared acquisition guard, rechecks the selection and
model approval, then commits versions, heads and changes together. Offline hooks
never wait for the acquisition writer, so a running scan cannot deadlock a reader
that already owns the notebook lock.

Registration saves canonical paths. Every scan checks that the vault, its ancestors
and selected folders still represent those paths. A directory replaced by a
symlink, including a self-referential loop, blocks acquisition without reading the
replacement's notes.

The hook named `collect` has a different job: read saved changes into a bounded
`Batch`. It does not rescan the vault. Pending/dry-run reads saved index metadata,
not note bodies, and cannot predict unseen changes in a live vault.

Only current added/modified versions become batch items. Superseded, deleted and
out-of-scope events advance proposed progress without presenting old bodies as new
material. A failed model stage leaves the committed cursor unchanged, so the batch
can be retried. The stage owns progress; providers never save the caller's checkpoint.

Output has item and serialized-character limits. A first oversized note is explicitly
truncated by the existing fitter; subsequent notes that do not fit wait for a later
batch. The event scan streams past obsolete entries. Long histories can still take
time to scan, and the initial selected folder can need several model batches.

## Versions and citations

Content determines changes: touching modification time alone preserves the version;
renaming produces deletion plus addition. Recreating a deleted note produces a new
version. IDs contain the notebook/vault instance, note identity and version.

The SQLite store retains exact old versions. A citation retrieves its saved version,
not today's live note. Deleted notes remain citable if their saved paths are still in
approved scope. Narrowing scope or withdrawing approval hides those contexts without
reading the live vault. `record_of` only parses identity; it does not prove existence
or chronological order. Removal does not automatically erase claims from REM pages.

The reader context distinguishes note modification time from snapshot capture time.
Private labels (`[personal]`, `[sensitive]`) in full content or paths are checked before
truncation, and labelled notes are omitted from model batches, gathering and citations.
There is no owner-only override in this draft.

## Investigation

Gathering matches literal text in saved paths/content, ignoring case. A match is a
candidate, not proof of identity or project membership. The start time filters saved
modification times, not dates of claims. The target record never broadens folder scope.
An optional end time is exclusive. The shared caller supplies the remaining item
and character budgets; direct calls default to 100 items and 100,000 serialized
characters. Invalid budgets or time windows fail before reading snapshots, and
coverage identifies limited output. Owner-only requests return no notes because
the stored note format does not establish authorship. Investigation uses saved
snapshots: collect first after edits.

These limits apply to the Obsidian gathering adapter. The shared investigation
runner can independently search other material. In the local walkthrough, it
retrieved Codex-session material and performed web searches despite the other
source subscriptions being disabled. The generated page contained both Obsidian
and Codex citations. Collection coverage is not proof of tool isolation, and a
shorter lookback window does not guarantee a faster investigation.

## Storage and errors

`.state/obsidian-snapshots.db` is authoritative snapshot storage, separate from the
derived `rem.db` index. Include it in notebook backups. It is bound to the original
notebook path, so copying it to another notebook requires an explicit migration.
Versions, heads and changes commit together under the notebook lock. Failed scans
or transactions preserve the prior snapshot state. Temporary access failures can
leave approved saved versions available with a stale-data notice. Scope changes,
approval changes and snapshot-integrity failures block saved material through the
shared failure receipt. Restoring a path alone does not clear that block: a fresh
successful acquisition is required. Unexpected programming errors propagate.

If another collector holds the acquisition writer lock until the wait expires,
the attempt reports temporary unavailability and keeps approved saved versions
readable with a stale-data notice. This does not clear an existing scope or
integrity block. Errors after acquiring the lock keep their original handling;
a scan or publication failure is not treated as writer contention.

SQLite reports of a corrupt or non-database file block saved material. Other
SQLite errors, including binding mistakes, invalid SQL and missing-table errors,
propagate rather than becoming an ordinary source-unavailable result.
Expected unavailable versions use `SnapshotUnavailable` and return no citation.

The low-level store API is for explicit local operations. Product/model consumers
must use `source_hooks`, which enforces the current consent receipt and scope.
The interface remains subject to shared-PR review. This migration adds only the
Obsidian registration and adapter; Asana and Granola migrations are owned separately.
