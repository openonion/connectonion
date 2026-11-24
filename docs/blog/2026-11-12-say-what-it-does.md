---
description: Sprint testing found co ai's words promising things its behaviour did not do. "Read only" asked to write, a stopped turn looked like a question, and every reply began "I'll …". The labels and messages now describe what happens.
tags: [co ai, Modes, Design]
---

# Say what it does

We tested `co ai` through O Chat on a real Host for a sprint, and the bugs we wrote down had one thing in common. The code mostly did something sensible. The words around it said something else.

The mode called **Read only** showed an Allow once button when the agent wanted to write a file, and if you pressed it, the file was written. That is how the mode had always worked: it asks before every change. The name promised a write ban that never existed.

When we pressed Stop in the middle of a turn, the reply read "Result: What would you like me to do?" Nothing said the turn had been stopped. It looked like the agent had finished and was waiting for us.

Every reply began "understood, I'll …" before any tool had run. The prompt asked for that, with examples such as "I'll deploy your app to production", while `main.md` told the same agent not to announce what it was about to do. The agent obeyed the louder instruction.

Any coding request, even "fix this test", loaded the ConnectOnion agent-building workflow, which says never to create files by hand. And the Codex tool's prompt described hosted modes the way they used to behave, not the way they behave now.

## The fix was mostly words

We did not change what the read-only mode does. We changed what it is called. It is now labelled **Ask first**, with the description "Asks you before every change." The protocol id stays `read-only`, so existing clients keep working.

A stopped turn now says "Stopped by you after step N of M." The turn result keeps where the stop happened (which step, which tool), and only that. The tests check that it stores no tool arguments or results, because a step that was interrupted may have done only part of its work.

The acknowledgement is now a neutral label for the task, three to eight words, instead of a promise. The agent-building workflow loads only when the request is to build a ConnectOnion agent. The wire field `is_build` is still sent, so the TypeScript client does not break.

The Codex prompt now matches hosted behaviour, and when the mode changes in the middle of a session the model is told which mode it is in now. Claude Code is also found at `~/.local/bin/claude`, and the error says where it looked when it is not there.

## What we learned

Each of these was found by a person reading the screen, not by a failing test. The tests passed because they checked what the code did. A label is a promise too, and it needs the same check: run the mode, read the words, and see whether they agree. The new tests do that, and they failed on main before the change.
