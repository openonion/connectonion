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
By default (`tasks.auto: true`) the night starts each task after drafting and
records it in `.state/approvals.json` with `by: rem`, so Today says "REM started
this" and offers Stop and Undo. Undo stops the task, removes its folder, worktree
and branch, and records `cancelled`: the night never starts it again, while
morning approval still can. With `tasks.auto: false` morning approval reserves a
receipt and the Host starts `co rem task run ID`. `co rem status` names the choice.
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
