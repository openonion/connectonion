---
description: co handoff kept the last forty turns of a session and clipped the summary, so the numbers the task needed never left the machine. The recipient's Codex went looking for them on its own disk and nearly found the wrong ones.
tags: [Handoff, Codex]
---

# The handoff that kept the wrong half

We handed a real task to a real Codex. The sender was a Claude Code session on a
Mac that had spent a day measuring co rem: the first owner page took 890 seconds
against a promised four minutes, the notebook map took seven, the whole run
259. The recipient was a fresh Codex on another machine. The task was one line:
find out why the first page is slow.

The handoff arrived, the Codex accepted it, asked before changing anything, and
then did something sensible. It said it would "inspect existing traces". It had
none of ours, so it inspected its own. That machine had run co rem on October 2,
an older version, a different mailbox, and its first owner page had taken 13
minutes 18 seconds. Close enough to fifteen to look like the run we meant. The
Codex said, to its credit, that it could not tell whether this was the same run,
and asked. Another agent might not have asked.

None of our numbers had been sent. The handoff kept the last forty turns of the
session and the compaction summary before them, clipped at twelve thousand
characters. The session had been compacted nine times. The measurements were in
the second half of the summary, past the clip. What did fit were the first
twelve thousand characters: a discovery design, the release checklist, a
security note about invite codes. Everything unrelated went; everything needed
stayed home.

Aaron's answer was that a handoff is one message, and that a compaction already
knows what to keep: every message the person typed, word for word, and the AI's
side in summary. If the other side needs more, it asks, and the sender's side
answers. We stopped choosing turns. Both clients keep the whole history on disk,
so the handoff now reads all of it, across every compaction.

Then another session ran it against fourteen real compacted sessions and scored
131 facts. The old handoff kept 60 percent, and 47 of the facts it lost came
from before a compaction. Codex sessions lost the most: finished work came back
as open, and one brief said "do not release 1.6.0 yet" about a version already
on PyPI. The new one kept 130.

It also found what we had broken. One session was 124 megabytes and sent 1.1
million characters to the model in a single call. A Codex /goal, the person's
actual task, arrives wrapped in an internal-looking tag, and our filter for
injected text threw it away, so in one real session the work item never arrived
at all. Issues travelled as bare numbers. Each fix went back through the same
sessions, and through a fresh Codex on the other machine that had to implement
the work from the handoff alone.

The lesson we keep relearning: when you cut something to fit, you choose by
position, and position does not know what matters. The end of a summary is where
it puts what is still to do.
