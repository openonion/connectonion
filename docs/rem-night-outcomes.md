# Nightly outcomes for the morning confirmation

The daily and native rounds cover every open, owner-owed item in the shared
Today order, including items outside the first visible cards. The default
`limits.drafts_per_night` is **30** model attempts per notebook day. Explicit
configured caps remain in force across rounds. Owner verdicts and task prompts
need no model calls. Every item left by a draft cap, daily cap, quota stop,
missing consent, provider failure or rejected draft has a named reason.

REM retrieves missing cited originals through the existing Outlook/Gmail
clients, only for enabled, consented, non-unsubscribed mailboxes. Metadata-only
messages and unique hashed citation aliases resolve to native message IDs.
Unindexed citations get their headers directly from the provider. After retaining
the body in the private archive, REM indexes and rechecks the latest message
across all cited threads before drafting or recording an owner-last verdict.
Fetching retains a local copy; it does not move mail in the provider mailbox.

An owner answer records an `already_handled` verdict with quoted owner words.
Future promises, clarification questions and explicit noncompletion become
`task` outcomes. There is no obligation-task dispatcher on this base branch:
tasks contain a ready-to-dispatch prompt, **not a claim that the work is done**.
That prompt includes the obligation, source, page and full cleaned owner message.
Non-mail tasks never attribute notebook prose to the owner as a quotation.
Nothing here sends messages or marks an obligation done; the morning UI still
owns confirmation.

## Snapshot contract

Both full and Today-only **local** snapshots expose `night_outcomes`, in Today
order, with one entry per grouped owner-owed item. The same object is attached
as `today_queue[i].outcome`. Done/skipped obligations are excluded by
the existing thread-state rules. The reader builds this projection without
writes or provider/model calls. Shared snapshots have `night_outcomes: []`, no
card outcomes, and counts only in `status.tonight`.

```json
{
  "key": "the existing Today group key",
  "keys": ["all existing obligation keys in this group"],
  "record": "people/fern.md",
  "title": "Fern Vale",
  "text": "You owe Fern the pilot review. [1]",
  "kind": "task",
  "source": "gmail:latest-native-message-id",
  "prepared_at": "2026-11-08T00:00:00+00:00",
  "owner_quote": "I'll review the pilot and send feedback tomorrow.",
  "task": {
    "status": "ready",
    "prompt": "Prepare the work owed by the owner..."
  }
}
```

Common fields: `key`, `keys`, `record`, `title`, `text`, `kind`, `source` (empty
for a non-mail task). Recorded outcomes carry `prepared_at`. Kind-specific fields:

| `kind` | Additional fields and meaning |
| --- | --- |
| `prepared` | `draft_id` references the existing `drafts` payload with body, recipients and sources. |
| `already_handled` | `owner_quote`, `reason`; a sent local draft may also supply `draft_id`. |
| `task` | `task: {status: "ready", prompt: string}`, `owner_quote` (empty without owner-authored evidence). |
| `no_reply` | `draft_id`, `reason`; the writer's validated no-reply verdict. |
| `could_not_prepare` | `reason`, including the configured cap or safe provider diagnosis. Before a round, the reason is `Not prepared yet.` |

The private ledger is `.state/night.json`; the public UI contract is the
snapshot, not that internal file. Ledger entries are checked against current
obligation keys, text and latest-message classification. Current accepted drafts
are projected from the existing draft store. New source evidence invalidates old
verdicts; resolving or returning a thread follows existing thread-state rules.

`co rem status` and its JSON response use the same projection:

```text
tonight: 17 items · 12 drafts · 2 already handled · 2 tasks · 1 could not be prepared
  Fern Vale: You owe Fern the pilot review. [1] — Gmail read failed: TimeoutError
```

A nonzero `no_reply` count is appended as `N no reply needed`. JSON
`tonight` has `items`, `drafts`, `already_handled`, `tasks`, `no_reply`,
`could_not_prepare`, and `unprepared` (key, record, title, text, reason).
Provider failures retain safe error classes/HTTP diagnoses, never raw exception
text that might contain credentials or private URLs.

`reader.html` is unchanged. This contract supplies the other engineer's morning
approval UI; no new rendered UI or batch-confirmation endpoint is claimed here.
