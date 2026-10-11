---
description: The co handoff mail ran off a phone and pinned a co version nobody could install. It now reads like a mail, and Codex on a second machine took it from paste to accept.
tags: [Handoff, Email, Codex]
---

# A mail you can read on a phone

A handoff is a mail. Someone hands you a task, and the mail is meant to do
two things: tell you, a person, what the task is, and give your coding agent
everything it needs to pick it up.

We read one of these mails the way a recipient would, in the Gmail inbox it
landed in. It opened with "Paste this into Codex or Claude Code:" and a line
of three backticks. Everything after that sat in one `<pre>` block, so
nothing wrapped, and on a phone every line ran off the right edge. The task,
the thing a person wants to know first, was at the bottom of a long install
step. Below it all was a block of base64 the width of the screen.

The install step had a worse problem. It asked for
`connectonion>=1.9.2b10.dev1`, the sender's own version, and the sender was
on a development build. No package index had that version, so a recipient
who followed the steps could not install co at all. The floor is now a fixed
version, the oldest release that can accept a handoff, and it only moves when
the recipient's side of the protocol changes.

The mail now starts with who handed you what. The task, where it stands and
the open questions come next, as ordinary paragraphs. After them is one
sentence on what to do: copy the box into Codex or Claude Code. The box wraps
on any screen. The base64 the `co handoff open` command reads is still there,
in small grey type at the very end.

Then we tested it the only way that counts. A handoff went from one Mac to
Parrot, another machine, whose co was three versions too old. We took the
text inside the box, exactly what a person would copy, and gave it to Codex
on Parrot. Codex upgraded co in its own environment with uv, saved the brief,
accepted the handoff, and stopped to ask before touching anything. A minute
later the sender's `co handoff status` said "Accepted".

The lesson: a mail has two readers here, a person and an agent, and the
person reads first. We had designed the mail for the agent, and the person
was left to scroll sideways past install instructions to find out what they
had been asked to do.
