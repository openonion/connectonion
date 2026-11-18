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

Verification and remaining browser limits: [sprint evidence](testing/rem-draft-coverage.md).
