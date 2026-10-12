---
description: We ran a handoff the way a stranger would, from an empty machine, with Codex reading the mail. It worked, and it still found three things no unit test had.
tags: [Handoff, Testing]
---

# The test where a stranger pastes the block

Every earlier handoff test had one thing in common: the person receiving it
already had `co`. So this time we started from nothing. A new identity on each
machine, a short real Claude Code session on one, and on the other an empty
folder, a mailbox and Codex. We pasted the block from the mail and watched.

It worked. Codex ran the install line, saved the brief, stopped to let the
person accept, asked the sender which way to go, and 36 seconds later had a
copy of the sender's session and said, correctly, that the sender had not
decided yet. It did not open an unrelated skill on the way, which an earlier
run had.

It also found three things.

The install line ended in a traceback. Codex keeps `~/.codex` read-only inside
its sandbox, and `co init` tried to link skills there and crashed. `co` was
installed and worked; the script still said it failed. Now a directory that
cannot be written is skipped, with a line saying so.

The sender's side told a confusing story. The line for an answered question
repeated the question, as if that were the answer, and the next time you
checked, the line was gone and `co` asked you to answer it. Now every question
says, each time, whether your agent answered it and how.

And the text version of the mail ran words together: "HANDOFF0xf9e5…",
"ENDFirst time?". The mail service writes that version from our HTML and starts
new lines only at paragraphs, not table cells. Nobody sees it in Gmail. An
agent reading the mail as text sees exactly that. Each piece of text now sits
in its own block; the HTML looks pixel for pixel the same.

None of the three shows up when the test already has `co` installed, runs
outside a sandbox, and reads the mail as HTML. The test has to start where the
stranger starts.
