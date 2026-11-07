# Today and prepared replies

Today and the night's reply budget use the same Python queue, included as
`today_queue` in the reader snapshot. Deadline cards come first, followed by
the morning cards shown on Today, then the remaining threads. A copied
obligation has one group identity. The reader consumes these identities and
their order without regrouping them.

An undrafted card explains its state in the interface language:

- A draftable reply is queued for tonight, or waiting while background updates
  are off. In the live reader, **Draft now / 现在起草** prepares it immediately.
- A missing original names its mailbox and reports a failed last read when
  status records one. A resolved message opens its provider thread; an unresolved
  citation opens the recorded source.
- When the last message was the owner's, the card is a task. It shows a bounded
  excerpt of that message and its date. A thread waiting on someone else opens
  the original conversation for follow-up.

Only `【需要你：<what> — <by when or date not agreed>】` is accepted as bracketed
text in a new draft. The reader highlights these parts with **Fill in / 需要你填**.
Sending, including from the full-screen writer, requires filling every marked
part first. Older English placeholders and incomplete brackets also block send.

An offline snapshot keeps the letter readable. Its single draft action,
**Open in the live reader / 在实时阅读器里打开**, reveals the notebook's exact
`co rem open` command with a copy button. A custom notebook keeps its `--root`
argument; live-reader availability still follows the existing CLI rules.

Verification and remaining browser limits: [sprint evidence](testing/rem-draft-coverage.md).
