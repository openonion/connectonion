---
description: A source can keep every word yet lose its meaning when HTML fields become one line. An Outlook rendering fix keeps the boundaries that help a reader verify a claim.
tags: [REM, Evidence, Mail]
---

# A line break can be evidence

A cancelled meeting email can carry three separate facts: when it would have
happened, why it was cancelled, and whether anyone needs to follow up. In an
earlier REM source dialog, the words were present, but Outlook's HTML-to-text
rendering had pressed the fields into one line. On a phone, checking the page's
claim against that source took more effort than it should.

The small fix is at the source boundary. Outlook mail can use paragraphs,
line breaks and tables to distinguish clauses. When those elements become
text, we now preserve their separators. We keep the existing link text and
URL handling, and we still say the excerpt is a provider rendering rather
than original MIME.

We rendered an invented cancellation email through the actual reader at
desktop and phone widths. Its event time, reason and follow-up appeared on
separate lines in the source dialog, without horizontal overflow or a page
error. We then re-read one previously affected Outlook message: its captured
rendering went from 8 lines to 32, with the same non-whitespace characters.
The private source dialog remained readable on both widths. The Outlook and
link tests passed. This narrow check does not mean previously saved mail
changed, that every Outlook template has been checked, or that a new REM
finding has been written. The
[preview notes](/releases/1.9.0a36) state those limits.
