---
description: Every test of automatic answers passed, and they all ran in one afternoon. A review asked what happens a month later, with two programs checking at once and a session that no longer exists. Nine things broke.
tags: [Handoff, Reliability]
---

# The question asked on day thirty-one

Automatic answers shipped two days ago. The tests were green and a real
handoff between two machines answered a question in six seconds. Every one of
those runs had something in common: it happened within an afternoon, with one
program checking for questions, on a session that was still on disk.

So we asked a different reviewer to read the code and assume time passes.

The first thing it found was the one that mattered most. The sender's side
remembered how many questions it had answered, and treated that number as a
position in the list of questions it could see. Messages in the agent inbox
expire after thirty days. Once the first two questions expired, the list got
shorter, the third question landed at position zero, and position zero counted
as already answered. A question asked on day thirty-one would never get an
answer, and nothing would say so. Now each answered question is remembered by
when it was asked and what it said.

The rest had the same shape. Two programs check for questions, `co ai` in the
background and `co handoff status` when you ask, and if they ran at the same
moment both answered, each sending a copy of the session. A session copy from a
long-running session was larger than the inbox accepts, so its answer was
retried forever. Claude Code deletes old sessions, and a session that was gone
made the check crash. The inbox was read five hundred messages from the oldest,
so a busy agent stopped seeing new ones. One plain-text message from anyone
broke every read of the inbox it was sent to.

None of these appear in a test that runs for one afternoon, because each of
them needs a month, a second process, or a stranger. The reviewer was told to
reproduce everything it reported, so every finding arrived as a failing test,
and all nine now pass.

What we take from it: a test that runs in seconds proves the first day. If a
feature keeps state for thirty days, the review has to ask what day thirty-one
looks like.
