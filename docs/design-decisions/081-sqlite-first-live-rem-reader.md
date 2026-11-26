# 081: SQLite-first live REM reader

Status: SQLite v3 store engine, CLI-served live HTTP reader and native attachment preview integration implemented together.
Tracks #3468 and #3469.

## Problem

A reader should open the current notebook quickly and show source text when a
citation is opened. Rebuilding a large embedded snapshot makes page loads pay
for unrelated pages and repeated attachment extraction. The previous SQLite
index also rebuilt whole CRM tables on a single person edit, duplicated body
text in an FTS shadow table, and retained free pages after large deletions.

## Decision

Use `.state/rem.db` schema version **3** as the structured read index for a
CLI-served live HTTP reader. Markdown pages, captured originals, map data and
run receipts remain authoritative. The store is disposable and can always be
rebuilt from those inputs.

This is a clean-cut migration: an older schema or wrong auto-vacuum mode causes
a fresh database build. There are no old-schema adapters or dual schema writes.
The implementation integrates the storage and query APIs with HTTP routes,
reader rendering and native attachment previews in the same change.

### One private SQLite file

Set `auto_vacuum=INCREMENTAL` before creating tables, persist `journal_mode=WAL`,
and enable `synchronous=NORMAL` and `foreign_keys=ON` on every writer. Keep the
database and its sidecars owner-only. Readers open read-only connections; the
maintenance lock still provides a single writer.

When mutations leave more than 64 free pages, incremental vacuum reclaims the
freelist. This controls dead-page growth without rewriting a live database in
place on every refresh. A schema/vacuum mismatch uses recreation rather than a
complex migration matrix.

### Change rows, preserve the rest

File size and nanosecond mtime identify changed inputs. Leaf edits update their
record and links directly. When the map, people, organisations or skills change,
recompute joined census classifications and rollups, compare rows, and upsert
only differences. Record deletion cascades through dependent CRM/link/edge rows.
A saved link-count table keeps relationships from either page correct across
one-sided edits. Unchanged rowids and FTS entries survive.

Joined recomputation still reads relevant notebook content; this change removes
full-table writes rather than claiming every cross-page classification is a
constant-time operation. Mail, session and run groups retain their existing
input-group refresh behavior.

### Index text once and search Chinese bodies

Use external-content FTS5 with `content='records'`, `content_rowid='rowid'` and
`unicode61`. SQLite insert/delete/update triggers keep postings synchronized.
Public bodies live once in `records`; there is no `records_fts_content` copy.

Token search alone cannot find arbitrary Chinese substrings inside a longer
sentence. CJK queries, empty indexed results and FTS operational failures use
parameterized literal `LIKE` matching across the record path, title, summary
and public body. Substring snippets center on the match. Both paths enforce
the privacy ceiling: `cover`/`public` searches omit private pages, and indexed
bodies/summaries omit personal and sensitive passages.

### Cache derived source text in SQLite

- `attachments` stores extracted text and file metadata, keyed by source ID.
  Extract only when `(size, mtime_ns)` changes, with a 20,000-character extraction
  limit. Keep the downloadable original file.
- `translations_cache` follows `.state/translations/<lang>/<record>` and stores
  valid translations without their source-hash header. File edits and original
  page changes trigger validation; stale translations disappear from the cache.
- `research_cache` retains individual dated captures keyed by source and capture
  file. Preserve dates and privacy flags so readers can choose the cited version
  and omit private captures unless explicitly allowed.

Persist directory child lists and directory/file stamps in `meta`. Unchanged
cache directories need no relisting, and unchanged files need no text reads or
extraction. Checking file stamps remains necessary to detect in-place edits;
directory mtime alone cannot prove that a file's contents are unchanged.

### Keep evidence, discard scratch

`.state/tasks/` and turn logs are workspaces rather than another evidence archive.
Tidy removes finished turn scratch after a grace period and abandoned scratch
after six hours. Preserve running-task files, active turns, turn receipts used
for statistics/recovery, `.state/runs/*.json`, retained research and cited
attachments. Do not follow symlinks during cleanup.

## Alternatives and tradeoffs

Keeping the old schema would require every reader to support two database
shapes. Rebuilding is simpler because every row is derived. Full-table refresh
is easy to implement but unnecessarily rewrites unchanged bodies and relations.
Internal-content FTS duplicates text; external content requires triggers, which
also make consistency independent of the Python write path.

Adding a dedicated CJK tokenizer would increase dependencies and still require
substring decisions. A parameterized fallback handles current notebook sizes,
with the tradeoff that CJK/substring scans cost more than indexed token queries.
Retaining original files means cached text consumes additional space, but avoids
repeated parsing and preserves the source for re-extraction and downloads.

## Validation and integration boundary

Unit tests cover writer pragmas and schema recreation, incremental page/map
changes and cascading deletes, FTS insert/update/delete consistency, CJK and
substring privacy, cache invalidation, translation source changes, freelist
reclamation and safe turn-scratch cleanup. Existing store, security and tidy
regressions remain part of the acceptance suite.

The engine does not certify all rendered reader pages. Reader integration must
inspect actual list/detail/search/evidence states, language changes, empty and
error states, desktop/mobile layout, navigation and progressive disclosure.
See [store API and operational details](../cli/rem-store.md).

### Independent review record

An independent AI reviewer used the technology-founder, marketing and UI role
required by the project review policy. Two findings were fixed and rechecked:

| Priority | Finding and user impact | Evidence and recheck criterion |
|---|---|---|
| P1 | Unindexed note originals did not invalidate translations, so removed or changed facts could remain visible. | `test_note_translation_invalidates_without_indexed_note_rows`: editing and deleting a note must each remove its stale cached translation. Dependencies now stat every translated original directly. |
| P2 | A scratch directory containing an active nested log could be removed, interrupting a running task. | `test_tidy_keeps_scratch_directories_containing_running_task_files`: the old active log and its directory survive. Independent fixture recheck also confirmed that an unrelated stale sibling is pruned. |

Review covered fictional-fixture record list/detail, Chinese search, privacy-safe
snippets and empty-search API states. Generated public-only HTML retained public
text and excluded sensitive fixture text. The reviewer found no remaining
significant engine issue after the fixes. Actual visual desktop/mobile and
browser-interaction states remain unverified because the computer-use browser
host was unavailable; generated HTML inspection is not a rendered-page pass.
