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
`task` outcomes. Tasks contain a ready-to-dispatch prompt, **not a claim that the work is done**.
Morning approval reserves a receipt and the Host starts `co rem task run ID`.
The night may dispatch after drafting only when `tasks.auto: true`; its default
is false. `co rem status` names this choice.
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
| `task` | `task: {status: "ready", prompt: string, id: string}`, plus receipt fields when dispatched; `owner_quote` is empty without owner-authored evidence. |
| `no_reply` | `draft_id`, `reason`; the writer's validated no-reply verdict. |
| `could_not_prepare` | `reason`, including the configured cap or safe provider diagnosis. Before a round, the reason is `Not prepared yet.` |

The private ledger is `.state/night.json`; the public UI contract is the
snapshot, not that internal file. Ledger entries are checked against current
obligation keys, text and latest-message classification. Current accepted drafts
are projected from the existing draft store. New source evidence invalidates old
verdicts; resolving or returning a thread follows existing thread-state rules.

`co rem status` and its JSON response use the same projection:

```text
Tonight          17 items · 12 drafts · 2 already handled · 2 tasks
                 1 could not be prepared
                 Fern Vale: You owe Fern the pilot review. [1] — Gmail read failed: TimeoutError
```

A nonzero `no_reply` count is appended as `N no reply needed`. JSON
`tonight` has `items`, `drafts`, `already_handled`, `tasks`, `no_reply`,
`could_not_prepare`, and `unprepared` (key, record, title, text, reason).
Provider failures retain safe error classes/HTTP diagnoses, never raw exception
text that might contain credentials or private URLs.

## Obligation work

Use `co rem task status` to find IDs, `co rem task run ID` to start one, and
`co rem task stop ID` to stop it. Each ID gets one Codex session, using the
configured work model and the same sandbox/network/credential-directory flags
as upkeep. An unambiguous existing repository from the obligation's project
page (or an explicit project link on its page) is the working directory;
otherwise the working directory is `.state/tasks/do-ID/work`.

The prepared prompt is extended with the completion criteria, the absolute
`.state/tasks/do-ID/result.md` deliverable path, and “do not send anything to
anyone; write the result and stop”. Reviewable work can include repository edits;
the deliverable names changed files, evidence, checks and missing inputs.

`do-ID/receipt.json` records `queued_at`, `started_at`, `finished_at`, `exit_code`,
`result`, worker/Codex process identities, `cwd`, `log`, `last_message` and
`deliverable`. Terminal results are `completed`, `failed`, `timed-out` or
`stopped`. A zero exit without a nonempty deliverable is failed. Repeated `run`
returns the same receipt, including failures; automatic retries are deliberately
absent. `status` reconciles dead workers into a durable failure and stops verified
orphan Codex groups. Stop and timeout terminate tools before the Codex group.
Native maintenance cleanup preserves every `do-*` directory.

Local Today snapshots attach receipt fields to `outcome.task`; shared snapshots
still expose no private outcomes. The Today card shows receipt progress and,
after completion, the deliverable path plus a copyable prepared reply:
`REM 已经做完：<one line> · 附：<path>`. The owner sends it. Existing receipts
are not offered for another batch approval. Live cards provide a refresh action;
offline snapshots need a new `co rem open` to obtain later receipts.

This is execution evidence, not an independent judgement of work quality: the
owner reviews the deliverable before sending or marking the obligation done.
Tasks do not send messages, mark threads done, or make external commitments.

## Morning message (sprint 11)

The model-free morning projection reads `night.json` `items.*.outcome.kind`,
`draft_id` (deduplicated) and `prepared_at`; only `prepared` drafts count.
It reads `approvals.json` entries with `kind: reply`, `by: rem`, `status: sent`,
and `release_at` inside the overnight window. Held replies are not counted as
sent. Task receipts are the existing `tasks.py` `.state/tasks/do-*/receipt.json`:
`started_at` counts dispatches, and `result: completed` with `finished_at` counts
finished work. No task status reconciliation or model calls occur here.

The optional investigation contract is `.state/investigations/index.json`:
`{"items": [{"status": "explained", "explained_at": "ISO8601 with offset"}]}`.
Missing file means zero. The investigation writer must set `explained_at` when
its explanation becomes reviewable; merely starting an investigation never counts.
The window is yesterday 22:00 through today 06:00, in `schedule.timezone`.
Existing `.state/drafts/*.json` receipts (`id`, `status`, `prepared_at`) also
count prepared/held/sent drafts: sent work may have left the current night
projection. IDs deduplicate both sources; this adds no store.
Current unblocked `approvals.outcomes` supply one-click counts and up to two titles;
held/sent replies and dispatched tasks are excluded by the existing projection.

The only new store is `.state/morning.json`, keyed by notebook-local ISO date.
Each entry has `checked_at`, `channel`, and `status` (`quiet`, `disabled`, `sending`,
`sent`, `failed`); failures include only the exception class in `error`, never
provider payloads. The maintenance lock serializes the claim before external IO.
A crash leaves `sending`, diagnosed by doctor; it never auto-resends. A disabled
or quiet date is also final. Dry-run reads state without claiming a date.

Notification settings are round controls, not task evidence. Native-task input
checks accept legacy config digests with or without `notify`, including old
model/language digest variants, while still rejecting changes to task content.
Doctor reports incomplete setup when the selected sender or target is absent.
