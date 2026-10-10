---
description: co rem 1.9.2b4: a real run of the last beta found the notebook citing its own machinery as the user's words, and the filter that should have stopped it was matching the wrong name.
tags: [REM, Agents]
---

# The notebook that quoted itself

After we shipped 1.9.2b3 we installed it from PyPI on a real Mac and read
everything it left behind: every run record, every refusal, and the Codex
transcript of each of its 584 turns.

The owner's own page said the user had asked for a "Wiki-only" task, and cited
a session for it. The session was real, and the user had never typed it. It
was REM's own model check, the one line REM sends to make sure the model
answers: "Reply READY only. Do not use tools or read files."

REM reads the user's coding sessions to learn what they work on. It had read
one of its own, taken the instruction it gave itself for something the user
said, and written it on the page with a citation that checked out.

There was a filter for exactly this. It skipped sessions marked `co_rem`. But
Codex labels REM's sessions with the same client name as `co ai`, and `co ai`
sessions are the user's real work, so the label could never tell the two
apart. We had written a rule against a name nothing used.

What does tell them apart is where a session ran. Every REM turn runs inside
the notebook's `.state/tasks` folder; nothing the user does runs there. That is
the test now. That one citation was only the first: 583 more of the day's REM
sessions were waiting for the next sync, each about to become something the
user "said".

The lesson is about how the bug hid. The check existed, its test passed, and
the page it protected looked right, cited and confident. Only reading what the
system had actually done, turn by turn, showed the gap between the rule and
the world.
