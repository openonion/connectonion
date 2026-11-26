# co rem store: SQLite v3

`.state/rem.db` is the derived index behind REM's record queries, people table,
conversations and reader search. Markdown pages and captured originals remain
authoritative: deleting the database and running `co rem sync` rebuilds it.
The store never edits a page or makes a network request.

`SCHEMA_VERSION = "3"` is a clean-cut rebuild. Older schemas, corrupt databases
and databases without incremental auto-vacuum are recreated from their inputs;
there is no legacy-schema compatibility layer.

## Storage and connections

The database is created with mode `0600` inside `.state/`. Its WAL and shared
memory files inherit that mode. Every writer enables:

```sql
PRAGMA auto_vacuum = INCREMENTAL;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
```

Incremental auto-vacuum is configured before creating any tables on a new file.
A matching schema with the wrong on-disk auto-vacuum setting is also rebuilt.
WAL and auto-vacuum persist in the file; synchronous and foreign-key settings
are applied on each writer connection. Plain external SQLite connections must
enable their own foreign-key enforcement.

After a changed build or cache sync, a freelist above 64 pages triggers
incremental vacuum until the free pages are reclaimed. Pages may remain partly
occupied, so this bounds the freelist rather than guaranteeing a fixed file size.
Readers use `mode=ro`, open no maintenance lock, and never create a database.
WAL lets them keep a consistent snapshot while the writer commits.

## Indexed data

| Table | Contents |
|---|---|
| `meta` | Schema version, build time, cache directory listings and file stamps |
| `sources` | Input file `(mtime_ns, size)` and build group |
| `records` | Record path, category, titles, public summary/body, privacy, census flags, dates, tags and facts |
| `records_fts` | External-content FTS5 index over `records`; no duplicate content table |
| `people` | CRM facts, addresses, company, role, contact dates and mapped mail counts |
| `orgs` | Domains, people count and latest member contact |
| `projects` | Paths, session counts and activity dates |
| `links` | Per-page link counts used to maintain person–project relationships |
| `edges` | Person–organisation and person–project relationships |
| `messages` | Mail/session identifiers, participants, dates and body locations |
| `runs` | Run outcome, timing, model and token usage |
| `attachments` | Source ID, provider/message, filename, relative path, MIME type, size, mtime and extracted text |
| `translations_cache` | Current translation text keyed by `(record, lang)`, with file mtime |
| `research_cache` | Dated capture text keyed by `(source, capture_file)`, title, mtime and privacy flag |

`records` stores public body text once. Public text omits personal/sensitive
passages and leaves private-page bodies empty. Original Markdown remains the
source for an authorised full-page read. JSON columns return as decoded values.
`rel_path` and `capture_file` are relative to the notebook root, including `.state/`.

## Incremental refresh

`store.refresh(root)` runs under the caller's maintenance lock after map/sync.

| Group | Inputs |
|---|---|
| `pages` | Indexed Markdown categories and `.state/map.json` |
| `mail` | Source inventory and mail snapshot directories |
| `sessions` | `.state/projects/*/messages.jsonl` |
| `runs` | `.state/runs/*.json` |

Independent leaf edits read only changed Markdown files. Changes to people,
organisations, skills or the map recompute joined census/rollup values, compare
them with stored rows, and write only differences. They do not delete entire
page tables. Unchanged record rowids survive, while deletion of a record
cascades to its CRM row, link rows and relationship edges. Link counts include
links from both people and project pages, even when only one side changes.

Cache sync runs independently of the page group:

- `.state/attachments/<provider>/<message>/<filename>` is extracted once with
  `attachments.extract_text(path, limit=20_000)`, then again only when size or
  nanosecond mtime changes. Hidden fetch markers are excluded.
- `.state/translations/<lang>/<record>` follows the translation writer's exact
  layout. Only translations with a current source hash and matching source
  citations are cached, without the hash header. Editing or removing the
  original page also invalidates its translations.
- `.state/research/*/*.json` caches each dated capture separately. Privacy-marked
  capture text is omitted by default when reading the cache.

Directory mtimes and cached child lists in `meta` avoid relisting unchanged
cache directories. File stamps still need checking to detect in-place edits:
unchanged refreshes do no extraction, cache text reads or database writes.
Vanished files remove their cached rows. Symlinks are never followed.
The existing `rebuilt` report retains the four group names above; cache row
counts are included in `rows`, and cache-only changes update `built_at`.

## Search and privacy

FTS5 uses `unicode61` and `content='records'`. Insert, update and delete triggers
maintain the index in the same transaction as record changes. There is no
`records_fts_content` shadow table.

CJK queries use literal, parameterized substring matching across titles,
summaries, record paths and public bodies. Empty FTS results and SQLite FTS
operational errors use the same fallback. Snippets come from public text,
including a short window around a substring match. `cover` and `public` searches
exclude private pages; marked passages are absent from searchable bodies and
summaries. The query dispatcher and `search(max_privacy=...)` enforce the caller's
privacy ceiling on both indexed and fallback paths.

## Read API

```python
query_records(root, *, category="", query="", tag="", privacy="cover",
              include_unlisted=False, limit=200, offset=0) -> dict
get_record(root, record, *, privacy="cover") -> dict | None
search_records(root, query, *, category="", privacy="cover",
               include_unlisted=False, limit=50) -> list[dict]
search(root, query, *, max_privacy="cover", **kwargs) -> list[dict]
dispatch_query(root, params, *, max_privacy="all") -> dict
people_table(root, *, company="", query="", open_only=False, recent_days=0,
             sort="activity", descending=True, include_unlisted=False,
             today=None) -> list[dict]
person(root, record) -> dict | None
edges(root, record) -> list[dict]
thread(root, thread_id, *, bodies=False) -> list[dict]
threads(root, record) -> list[dict]
attachment_row(root, source) -> dict | None
attachments_map(root, sources=None) -> dict[str, dict]
translations_map(root, records=None) -> dict[str, dict[str, str]]
research_for_sources(root, sources, private=False) -> dict[str, list[dict]]
```

Attachment maps use citation source IDs as keys. Translation maps are
`{record: {language: text}}`. Research maps group raw capture rows by source;
callers can retain individual dates and select the captures their citations name.
An explicit empty source/record list returns an empty map.

Full mail and session bodies remain in their original JSON/JSONL files and load
on demand via `body_path`/`body_line`. All retained evidence and run records stay
outside disposable task workspaces.

`tidy` removes finished turn logs after a short grace period, and abandoned turn
scratch after six hours. Running tasks, active turn logs, durable turn receipts,
run records and cited originals remain. The CLI-served live HTTP reader can
query the current index without regenerating an embedded notebook snapshot; its
routing and rendering are maintained separately from the store engine. See
[the v3 decision](../design-decisions/081-sqlite-first-live-rem-reader.md).
