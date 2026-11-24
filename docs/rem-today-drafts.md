# Today and prepared replies

Today and the night's reply budget use the same Python queue, included as
`today_queue` in the reader snapshot. Deadline cards come first, followed by
the morning cards shown on Today, then the remaining threads. A copied
obligation has one group identity. The reader consumes these identities and
their order without regrouping them.

An undrafted card explains its state in the interface language:

- A draftable reply is queued for tonight, or waiting while background updates
  are off. In the live reader, **Draft now / 现在起草** prepares it immediately.
- The nightly round fetches missing originals from already-consented mailboxes
  and records any failure on the card outcome.
- Owner-last answers receive an already-handled verdict with quoted words;
  promised work receives a ready task prompt. The snapshot exposes these for
  the morning confirmation; see the [outcome contract](rem-night-outcomes.md).

Only `【需要你：<what> — <by when or date not agreed>】` is accepted as bracketed
text in a new draft. The reader highlights these parts with **Fill in / 需要你填**.
Sending, including from the full-screen writer, requires filling every marked
part first. Older English placeholders and incomplete brackets also block send.

Send never goes silent (sprint 22, the owner's report of 2026-11-18: he clicked
Send on a Lark reply with one unfilled part and nothing happened, because the
button was disabled and the only hint was a caption). Send stays clickable while a
part is open; a click says **Fill the marked part first / 先填好标出的部分** under
the button and moves the focus to the first open part. A click that is accepted
says at once that it is working, then either the Host's error or the hold:
**Sending to {name} at {time} · Undo / {time} 发给 {name} · 可撤销**, on the card
and in the line Today keeps after it.

**Write full screen / 全屏写** is a visible control on every reply card, beside
Send, not an entry in the card's ⋯ menu: the owner could not find it there.
The ⋯ menu keeps Edit in Outlook/Gmail and Skip.

An item's **Show more / 更多背景** sheet ends with **Talk it over / 聊一聊**: the
two agents are one row of buttons the height of a thumb, in ink, aligned with
the sheet's text, not a column of grey words indented under the heading.

An offline snapshot keeps the letter readable. Its single draft action,
**Open in the live reader / 在实时阅读器里打开**, reveals the notebook's exact
`co rem open` command with a copy button. A custom notebook keeps its `--root`
argument; live-reader availability still follows the existing CLI rules.

## Who REM may reply to without asking (#3121)

The owner, 2026-11-19: «回邮件如果是给我合伙人回，那就直接发就好了，因为合伙人和外部的人是不一样的……每一个人背后都有他自己的一套审批».
Each person's page carries a send policy as its `Direct send` fact (D-101):

| Tier | #3121 name | What happens to a prepared reply |
|---|---|---|
| `partner` | send | REM sends it without a click, through the same 10-minute hold with Undo |
| `close` | send-routine | sent only when the writer marks it `send: now`, which it may do only for a reply with no owner slot and nothing for the owner to decide |
| `none` (default) | approve | a card in Today, as before |
| `never` | draft-only | a draft only; only the owner sets it, and REM's rule never raises it |

- **Who sets it.** REM, from the relationship the page already states (co-founder or partner is `partner`); a line it wrote says `(set by REM, DATE; change it any time)`. The owner sets any person's tier in one click: **以后直接发给他 / Send to them directly from now on** or **以后先给我看 / Show me first from now on**, in the reply card's ⋯ and the person page's ⋯ (`POST /rem/direct-send`, `direct_send.set_tier`). His line reads `(set by you, DATE: reason)` and REM never changes it again.
- **Every change is recorded,** REM's and the owner's, one JSON line each in `.state/direct_send.jsonl` with when, who and why.
- **Never in the small hours.** A reply REM sends itself never leaves before 07:00 in the notebook's time zone: the hold ends at 07:00 instead, so the owner wakes to it with Undo.
- **A private fact holds it.** A reply that carries a passage labelled private waits for the owner, whatever the tier.
- **Today says so.** While REM's own reply is held, the Undo bar names it: **Sending to {name} at {time} · {left} to undo / {time} 发给 {name} · 还有 {left} 可撤销**. Sent ones are counted in "Replied to N people for you".

Not in this slice: a `partners:` list in config.yaml (config keys are validated strictly; the page line and the one-click choice cover it), and `send-routine` judged by a separate classifier (the writer's `send: now` rule is the gate).

Verification and remaining browser limits: [sprint evidence](testing/rem-draft-coverage.md).

## Following a hand-off to Codex or Claude Code (#3138)

When a row is handed to Codex or Claude Code, the run is no longer a black box until it ends.

- **What it is doing now.** The run reports each step as co ai's Work Room does. These are the OIP
  `provider_activity` events (`core/provider_events.py`): a fixed phrase such as "Running the requested tests" or
  "Preparing workspace file changes", never the command or file contents. The worker writes one line per step to
  `.state/tasks/do-<id>/events.jsonl`. `POST /rem/task` status returns the latest as `step` (plus the count as
  `steps`). The work strip and the card show it after "Codex is working · started 2 min ago" and update it every
  few seconds without redrawing the card.
- **Watch it.** When tmux is installed, the worker runs in a tmux session named `rem-<task id>`. Its environment is
  handed over with `env -i`, so the pane's pid is the worker's, and the pane is piped to `worker.log`. **Watch in
  Terminal** (action `watch`) opens Terminal attached to that session. Without tmux the worker is a plain detached
  process, as before, and the page's step line is the progress.
- **Carry on by hand.** When the run has finished and kept its session id, **Continue in Codex / Claude Code**
  (action `resume`) opens Terminal in the task's folder with `codex resume <id>` or `claude --resume <id>`.
- Both buttons are local only. `/rem/*` answers loopback clients only, and the phone's reader is a snapshot. On the
  phone the row says "Watching and continuing happen on your computer." The commands are written into a `.command`
  script in the task folder and are never shown to copy (D-60).

## Hand-off outcomes and recovery (#3147)

Both hand-off buttons show **Codex / Claude 正在做 · 0:00** synchronously on
click. The elapsed clock advances each second. A pending hand-off is kept by
item key across queue refreshes; the two agents use the same launch path, which
detaches the worker without waiting for its provider's app-server. A definite
Host refusal restores the buttons. An uncertain response keeps the running
state and confirms the receipt by item key instead of inviting a duplicate run.

New reports use the notebook owner's language (`owner_language`, falling back
to `config.language`), start with a one-line summary, and put proposed replies
inside a fenced `reply` block. A finished row shows that summary and one primary
action:

- **用这个回复起草 / Draft with this reply** promotes the proposed reply into the
  existing local prepared-draft store, tied to one current archived mail thread.
  It opens the existing draft card for review and never sends or creates a
  provider draft on this click. Repeated clicks reuse the draft, preserving edits.
- **标为完成 / Mark done** uses the item's existing completion path when there is
  no reply. Project investigation requests have no obligation to close and keep
  their report and continue controls.

**看结果 / See result** opens the full report in the source side card, leaving
the queue's layout intact. Relative report links use the authenticated,
loopback-only `GET /rem/task-file?id=<task>&path=<relative path>` endpoint. Paths
resolve inside that task's `work/` only; absolute paths, parent traversal and
escaping symlinks are refused. Text opens in the side card. Other files are
downloads with a sandbox policy, so report HTML cannot execute on the Host's
origin. Raw Outlook, Gmail and coding-session source IDs become chips opening
the source side card and respecting the existing privacy reveal control.

Failures show one Chinese reason and **重试 / Retry**. In particular, the old
Codex sandbox error says **Codex 当时无法启动（已修复），可以重试**. A run with
no output has no result link. Retrying archives the previous receipt, files and
events under `.state/tasks/history/`, then starts the same item with a fresh
workspace and session. A retry uses a new worktree branch and tmux name. Old
failures stay reachable in the work strip until retried or hidden together with
**清除失败记录 / Clear failed runs**; clearing preserves their audit files and
leaves active and completed work alone.

Browser work is prompted to open `co browser tab open rem-<full task id>`, pass
`-t rem-<full task id>` on every browser command, then close that tab at the end.
This is a prompt requirement, rather than a browser isolation mechanism.

Verification: `test_rem_handoff_polish.py` covers receipt summaries, prepared
replies, fresh retries, old failure dismissal, prompt language/tab instructions,
optimistic state across a refreshed queue and confined file access. The initial
regressions failed before implementation. `test_rem_handoff_polish_browser.py`
covers running, completed and failed rows, reply/done actions, side-card links,
retry and bulk clear at 1440 and 390; it writes `handoff-*.png` to the requested
rc30 fixture directory. This sandbox aborts Chrome at launch and denies `ps`
for pytest's final leak check, so browser execution, screenshots and rendered
experience review remain unverified here. An independent AI static review
identified and rechecked report links, investigation completion, uncertain
retry responses and repeated draft preparation; it is not a human or rendered
review.
