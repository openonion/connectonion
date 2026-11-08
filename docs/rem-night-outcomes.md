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
By default (`tasks.auto: false`) morning approval reserves a receipt and the
Host starts `co rem task run ID`. With `tasks.auto: true` the night also starts
owed tasks after drafting and records each in `.state/approvals.json` with
`by: rem`, so Today says "REM started this" and offers Stop and Undo. Undo stops
the task, removes its folder, worktree and branch, and records `cancelled`: the
night never starts it again, while morning approval still can. It stays off by
default until the sealed run reads only an allow-list (today it denies a list of
credential paths). Either way a task passes one gate: one task at a time, at
most `limits.tasks_per_night` (3) started per night, counted noon to noon, and
none once the Codex week reaches `limits.quota_floor_percent`. A task that has
to wait is written to `.state/tasks/waiting.json` and its Today card says
"Queued: later tonight" or "Queued: budget used up" with the reason.
`co rem status` names the choice.
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
`co rem task stop ID` to stop it. Each ID gets one Codex session with the
configured work model, sealed. The prompt comes from mail, which is untrusted,
so Codex runs its own seatbelt with a permission profile (`default_permissions =
"rem_task"`, no `-s` flag: with codex 0.167 a `-s workspace-write` run ignored
the profile, read canary credentials and reached the network). The profile reads
the disk except the owner's credential paths (`sandbox_profile.CREDENTIAL_DIRS`
and `CREDENTIAL_FILES`: `~/.co`, `~/.ssh`, `~/.config/gh`, `~/.aws`, `~/.gnupg`,
`.netrc`, `.git-credentials` and more), writes only the task folder, its work
directory and temp, and has no network. `--ignore-user-config` with apps,
plugins, browser use and computer use off means none of the owner's MCP servers,
connectors or hooks start (they run outside the sandbox); web search is off.
Codex starts with no environment variable whose name matches
KEY|TOKEN|SECRET|PASSWORD|API (it signs in from `CODEX_HOME`), and its shell tool
inherits only Codex's core variables (`shell_environment_policy.inherit="core"`),
so `env` cannot show what connectonion loaded from `keys.env`.
So a task cannot push, merge into the owner's checkout, send mail or post, and
cannot read keys. The cost: it cannot browse, search the web, install packages,
call any API, or read notebook pages (they live under `~/.co`); it works from
its prompt and what else is on disk, and names anything missing. When the
obligation's project page (or an explicit project link on its page) names one
existing directory inside a git repository, REM creates a worktree of it at
`.state/tasks/do-ID/work` on branch `rem/task-ID` and Codex edits there,
uncommitted; the owner's checkout is untouched. Otherwise `do-ID/work` is an
empty folder and the project is named in the prompt to read.

The prepared prompt is extended with the completion criteria, the absolute
`.state/tasks/do-ID/result.md` deliverable path, and “do not send anything to
anyone; write the result and stop”. Reviewable work can include repository edits;
the deliverable names changed files, evidence, checks and missing inputs.

`do-ID/receipt.json` records `queued_at`, `started_at`, `finished_at`, `exit_code`,
`result`, `by` (`rem` or `owner`), worker/Codex process identities, `cwd`,
`project`, `repository` and `branch` when a worktree was made, `log`,
`last_message` and `deliverable`. Terminal results are `completed`, `failed`, `timed-out` or
`stopped`. A zero exit without a nonempty deliverable is failed. Repeated `run`
returns the same receipt, including failures; automatic retries are deliberately
absent. `status` reconciles dead workers into a durable failure and stops verified
orphan Codex groups. Stop and timeout terminate tools before the Codex group.
Native maintenance cleanup preserves every `do-*` directory.

Local Today snapshots attach receipt fields to `outcome.task`; shared snapshots
still expose no private outcomes. The Today card shows receipt progress and,
who started it, Stop while it runs, Undo, a failure's reason, and after
completion a link to the deliverable plus a copyable prepared reply:
`REM 已经做完：<one line> · 附：<path>`. The owner sends it. Existing receipts
are not offered for another batch approval. Live cards provide a refresh action;
offline snapshots need a new `co rem open` to obtain later receipts.

This is execution evidence, not an independent judgement of work quality: the
owner reviews the deliverable before sending or marking the obligation done.
Tasks do not send messages, mark threads done, or make external commitments.

## Morning message (sprint 11)

The model-free morning note covers one window: from the previous note's
`checked_at` (the latest earlier `morning.json` entry that is not `missed`), or
22:00 the evening before when there is none, through the moment of this check.
Work after 06:00 is therefore reported once, the next morning. The note is due
06:00–11:00 in `schedule.timezone`; before that a check returns `not_due` and
records nothing; after 11:00 it records `missed` and sends nothing. A missed
date does not move the window, so its work appears in the next note.

Sources and the exact fields read (start exclusive, end inclusive):

| Count | Source | Fields |
| --- | --- | --- |
| sent for you | `approvals.json` values | `kind: reply`, `by: rem`, `status: sent`, `release_at` |
| drafted, waiting | `night.json` `items.*.outcome` and `.state/drafts/*.json` | `kind: prepared`, `draft_id`/`id`, `prepared_at`; waiting only while the draft receipt's `status` is still `prepared` |
| tasks finished | `tasks.py` `.state/tasks/do-*/receipt.json` | `result: completed`, `finished_at` |
| problems explained | `.state/investigations/index.json` | see below |

A reply REM sent is counted as sent, never also as drafted. Owner-approved sends
are the owner's own act and are not reported back to him.

Investigation contract, as `connectonion/rem/problems.py` writes it
(night-investigations head `35b0a770b`): the index is one JSON object keyed by
problem key, each value the full receipt — the detector's problem fields
(`key`, `detector`, `repo`, `project`, `symptom`, `facts`, `evidence_revision`,
`priority`, `oldest_at`, …) plus `id`, `state`, `result`, `attempts`, `reason`,
`opened_at`, `updated_at`, `last_checked`, `resolved_by`, `receipt`, and once
run `started_at`/`finished_at`. `update()` stores the receipt under its key and
every `save()` sets `state` and bumps `updated_at`. There is no `items` list and
no `explained_at`. The morning note counts a receipt whose `state` is
`explained`, `needs_owner` or `fix_proposed` and whose `updated_at` falls in the
window. `investigating`, `inconclusive`, `could_not_investigate`, `violation`,
`resolved` and `stale` never count. Known edge: a later state change re-bumps
`updated_at` (a closed draft PR turns `fix_proposed` into `needs_owner`), and
that counts again on the morning after it. Missing file means zero.

Decisions are the current unblocked `approvals.outcomes` rows, at most two
lines, each one clause built from the row's `kind` and words: a reply names the
page `title` and hands back the draft's `gist` (else its `subject`); a task
names its page `title`. A title or phrase containing `@`, a path, a `.md`
record or a long hex ID is dropped, never shown — a reply whose only title is
the draft's `to` address is shown by its words alone. More than two ends with
"N more in Today". Zero counts and an empty decision list are left out.

The only new store is `.state/morning.json`, keyed by notebook-local ISO date
and pruned to the last 14 days on every write. Each entry has `checked_at`,
`channel`, `status` (`quiet`, `disabled`, `sending`, `sent`, `failed`, `missed`)
and, except for `missed`, `pending`: the sorted outcome IDs offered that
morning, used to stay quiet when nothing is new and the decisions are the same.
Failures include only the exception class in `error`, never provider payloads.
The maintenance lock serializes the claim before external IO; the Today link's
host check runs before the lock is taken. A crash leaves `sending`; doctor
reports the latest entry only when it is `failed` or `sending`, and nothing is
ever resent. A disabled, quiet or missed date is also final. An error while
preparing the note claims nothing and the next scheduled check retries it.
Dry-run reads state without claiming a date and states what a real run would do.

Notification settings are round controls, not task evidence. Native-task input
checks accept legacy config digests with or without `notify`, including old
model/language digest variants, while still rejecting changes to task content.
Doctor reports incomplete setup when the selected sender or target is absent.
