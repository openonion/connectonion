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

An offline snapshot keeps the letter readable. Its single draft action,
**Open in the live reader / 在实时阅读器里打开**, reveals the notebook's exact
`co rem open` command with a copy button. A custom notebook keeps its `--root`
argument; live-reader availability still follows the existing CLI rules.

Verification and remaining browser limits: [sprint evidence](testing/rem-draft-coverage.md).
