---
description: A handoff now sends every word the person typed. A test against the real fix showed what that still misses, a requirement that only ever appeared in the AI's own tool calls, and why asking is the answer.
tags: [Handoff, Codex, Release]
---

# The requirement nobody said

To test the new handoff we took real sessions, cut each one back to the
moment before the work was done, and handed it to a fresh Codex on another
machine. Then we compared what it built with what had actually been merged.

One task was a failing release build. The handoff carried the person's
messages and the summary of what the AI had found, and Codex fixed it in 144
seconds, the same fix that had shipped. The old handoff had taken 662 seconds
on the same task.

The other task did not go as well. Codex picked the right issue, which the old
handoff had missed, and wrote a reasonable fix. It was only part of the real
one. The merged change also made `co keys` behave a certain way, and nobody in
the session had ever asked for that. We searched the whole conversation for it.
It was not in anything the person typed, and not in anything the AI said back.
It appeared in the AI's own tool calls: it had read a file, noticed the
behaviour, and changed it along the way, without a word in the chat.

A handoff deliberately leaves tool calls out. They are most of a session's
size, they are full of paths and file contents the recipient has no business
reading, and most of them are dead ends. Sending them would turn a message a
person can read into a dump nobody does.

So this requirement could not travel in the message. What it needed was the
other half of the design: when something is missing, the recipient asks, and
the sender's side, which still has the whole session, answers. In this release
`co handoff status --wait` sits in the background and returns the moment a
question or an answer arrives, so asking costs a minute instead of a day.

The lesson is about where knowledge lives in an agent's session. What the
person said is the intent. What the AI said is the reasoning. But some of what
was decided was never said by anyone; it was done. A summary of the
conversation cannot contain it, because it was never in the conversation.
