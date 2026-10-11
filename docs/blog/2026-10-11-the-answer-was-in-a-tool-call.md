---
description: A handoff deliberately leaves tool output behind, and one real requirement lived only there. Now the sender's agent answers every question by itself and sends a copy of the session, tool calls included.
tags: [Handoff, Agents]
---

# The answer was in a tool call

Earlier today a fresh Codex took over a real task from a handoff and built the
right fix, but only part of it. The missing requirement was in the original
session, but not anywhere a person or the AI had said it. It was in a tool
call: the AI had run a command, read the output, and changed the behaviour to
match. A handoff carries what was said, so it could not carry that.

We had said this was what questions are for: the recipient asks, the sender
answers. But that puts a person in the loop for every question, and the person
who handed the work off has usually moved on to something else. Aaron's answer
was to take the person out of it. When a question arrives, the sender's agent
answers by itself, and the answer includes a copy of the session.

The copy is different from the brief. The brief is short and a person approves
it word by word. The copy is long and nobody reads it; it is there to be
searched. So it includes what the brief leaves out: every tool call, with its
output, clipped at the start and end when a command dumped a whole file. It
covers only the messages that were handed off, up to the moment the handoff was
sent, and before it leaves, every string shaped like a key, and every value from
the sender's keys file, is removed.

On this very session, three days long, the copy packs to 2.2 megabytes. The part
that was handed off is 150 kilobytes. Sixteen things that looked like
credentials came out of it.

The recipient's agent saves the copy next to the brief and is told to search it
before asking again. The second question gets a pointer to it, not a second
copy.

What we learned is that "ask if you need more" is only half a design until
someone is there to answer. A question about a session nobody is watching gets
no answer. Now an agent answers it, from the session itself.
