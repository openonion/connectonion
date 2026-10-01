# co rem store: one SQLite index beside the pages (#2067, step 1)

Status: step 1 shipped in 1.9.0a9 — the index is built after every map and
sync, `co rem list people --table` reads it, and the JSON files stay
authoritative. Nothing else reads the index yet.

## Why

The owner asked (2026-10-02): when `init` builds the map we write JSON files;
should it be SQLite instead? Three views are waiting on structured data:

- **People as a CRM table** (#2064): email, company, role, phone, last
  contact, mails and what is open, one row per person, sortable and
  filterable. Today a screen gets those by re-reading every page and every
  JSON file, and each screen did it its own way (the census exists because
  People was 76 on one screen and 82 on another).
- **Conversations as chat history** (#2066): a mail thread or a coding
  session opened as messages in order. Today the raw material is spread over
  `source-inventory.jsonl`, one JSON file per mail body and a JSONL per
  project; nothing addresses a message by id.
- **The map at a glance** (#2066): who works with whom around each project,
  which needs edges with counts and dates, not prose.

One file the views can query answers all three, and gives the raw material
an id a page can cite.

## What stays files

- **The markdown pages are the product.** Readable, diffable, what agents and
  the owner read and edit. The store never writes a page.
- **Evidence files for the model** (`.state/evidence/`): the investigation
  hands a model files, and a file is what a model reads well.
- **Mail bodies** (`.state/mail/messages/<provider>/<sha256>.json`) and
  **session messages** (`.state/projects/<page>/messages.jsonl`). The store
  holds where each body is (`body_path`, `body_line`), not the body. The
  thread view loads bodies on demand, so the index stays small and a body is
  never copied into a second place.
- **All the JSON** (`map.json`, `source-inventory.jsonl`, `runs/*.json`,
  `aliases.json`, `tidy.json`, `archive.json`) stays authoritative in this
  step. The store is a derived index: delete it and the next map or sync
  builds it again from the same files.

## The file

`.state/rem.db`, mode `0600` inside the `0700` `.state` directory. SQLite
makes `-wal` and `-shm` with the database's own mode. It is never synced,
uploaded, or copied into a page or a deployment, like everything in
`.state`. Python's stdlib `sqlite3`; no new dependency.

## Schema (version 1)

| table | one row per | columns |
|---|---|---|
| `meta` | key | `key`, `value` — `schema_version`, `built_at` |
| `sources` | input file | `path`, `mtime_ns`, `size`, `grp` — what the last build read |
| `people` | person page | `record`, `name`, `emails` (JSON list), `phone`, `company`, `role`, `location`, `timezone`, `linkedin`, `website`, `how_known`, `language`, `first_contact`, `last_contact`, `mails`, `sent`, `received`, `open_threads`, `written`, `listed`, `held`, `service`, `classification`, `facts` (JSON object of every labelled fact) |
| `orgs` | org page | `record`, `name`, `domain`, `domains` (JSON), `people` (count), `last_contact`, `written`, `listed` |
| `projects` | project page | `record`, `name`, `paths` (JSON), `sessions`, `first`, `last`, `written`, `listed` |
| `messages` | mail or typed session message | `id`, `source`, `thread`, `sender`, `recipients` (JSON), `time`, `subject`, `body_path`, `body_line` |
| `edges` | person–org, person–project | `kind`, `person`, `other`, `count`, `last_contact`, `via` |
| `runs` | investigation run | `id`, `record`, `stage`, `outcome`, `model`, `started_at`, `finished_at`, `seconds`, `input_tokens`, `cached_input_tokens`, `output_tokens` |

Indexes: `messages(thread, time)`, `messages(sender)`, `people(company)`,
`people(last_contact)`, `edges(person)`, `edges(other)`, `runs(record)`.

Where each column comes from:

- **people**: the page's `## Contact` lines and, when #2068 lands, a
  `## Facts` block in the same `- Label: value` shape (Facts wins; citations
  stripped; `Unknown` is empty). Every labelled line also lands in `facts`, so
  a field #2068 adds is readable before it has a column. Counts and dates come
  from the map row; `last_contact` is the later of the map's and the page's
  own "Last contact:". `written`, `held`, `service` and `listed` are the
  census's, so the table's row count is the census's people count.
- **orgs / projects**: `map.json` rows and the pages.
- **messages**: mail from `source-inventory.jsonl` (`id` is
  `<provider>:<message id>`), `body_path` set only when the body snapshot
  exists; session messages from each project's `messages.jsonl` (`id` is its
  `source`, `kind:session:at`; the thread is `kind:session`).
- **edges**: person–org from the map's org rows (count = the person's mails,
  last contact = theirs); person–project from links between the two pages
  (count = links; no date yet — #2068's project people will give one).
- **runs**: `.state/runs/*.json`, tokens from `usage`.

### Mail threads are approximate

Neither the inventory nor the body snapshot records the provider's thread id.
A mail's `thread` is `mail:` plus a hash of its provider, its subject without
`Re:`/`Fwd:` prefixes, and the counterparts on From and To other than the
owner. A reply and its original land together; two unrelated mails titled
"Hello" between different people do not. Recording `threadId` at inventory
time is the fix (open question below).

## How it is built

`store.refresh(root)` compares every input file's `(mtime_ns, size)` with
`sources` and rebuilds only the groups whose inputs changed, each in one
transaction:

| group | inputs | tables |
|---|---|---|
| `pages` | `people/`, `orgs/`, `projects/` pages, `map.json` | people, orgs, projects, edges |
| `mail` | `source-inventory.jsonl`, the mail snapshot folders | messages (mail) |
| `sessions` | `.state/projects/*/messages.jsonl` | messages (session) |
| `runs` | `.state/runs/*.json` | runs |

Nothing changed: nothing is written. A schema version the code does not
know, or a file SQLite cannot open, is deleted and built from scratch — it
holds nothing that is not in the files. Building twice gives the same rows.

It runs at the end of `map` (after the second tidy) and of `sync` (after the
archive resume), inside the maintenance lock both already hold. An error is
not the map's or the sync's: it prints `co rem: store skipped: <reason>` to
stderr, the report carries `store: {"skipped": reason}`, and the next run
tries again.

## Concurrency

- Writes happen only under the maintenance lock, so there is one writer.
- Readers open `mode=ro` and never take the lock. WAL lets a reader keep its
  snapshot while a build commits; a reader never sees half a group.
- A reader with no file gets empty rows, and `co rem list people --table`
  says to run a sync.

## Read API (`connectonion/rem/store.py`)

```python
people_table(root, *, company="", query="", open_only=False, recent_days=0,
             sort="last_contact", descending=True, include_unlisted=False, today=None) -> list[dict]
person(root, record) -> dict | None   # the row plus its edges
thread(root, thread_id, *, bodies=False) -> list[dict]   # in time order
edges(root, record) -> list[dict]
threads(root, record) -> list[dict]   # a person's threads, newest first
```

Rows are plain dicts; JSON columns come back decoded. The reader (#2064) and
the facts work (#2068) read through these, not through SQL.

## Measured

On a copy of a real notebook (381 person pages, 142 orgs, 21 projects,
3,152 mails in the inventory with 574 bodies, 905 session messages, 60 runs):
see the PR for the numbers; they are filled in below at release.

<!-- MEASURED -->

## Not in this step

- Nothing reads the store but `co rem list people --table`. The census, the
  queue, the reader and status still read the JSON and pages.
- JSON is not dropped. Step 2 moves one reader at a time onto the store;
  JSON goes only when the store has been the source for a release.
- No chat messages (WhatsApp, Feishu) yet: they have no archive to index.
- No backup: the file is rebuilt, not restored.

## Open questions

1. Record the provider's thread id in the inventory so mail threads are exact?
2. Should the store keep a person's address → record table, so a thread view
   names senders by page rather than address?
3. When JSON goes, does `map.json` become rows in the store, or stay as the
   map's run report?
