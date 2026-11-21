---
description: After a reload, O Chat attached tool rows and Work Room cards to the wrong user messages. Internal reminders were counted as turns; now only a reminder the trace marks as a turn opens one.
tags: [Host, O Chat, Sessions]
---

# A reminder is not a turn

During sprint testing on real Hosts, we reloaded O Chat in the middle of a session and the history came back scrambled. A Claude Code turn showed the next turn's Codex card. A turn where we pressed Reject showed a Claude Code card stuck on Working. One user message appeared twice, and a turn we had stopped lost its reply. Two of the three test legs hit it.

Nothing was lost. The messages and the trace were all on disk. They were just glued together in the wrong places.

## The miscount

When a Host rebuilds a chat after a reload, `session_to_chat_items` walks the saved messages and the trace side by side. Each user message opens a turn, and each `user_input` marker in the trace starts the next block of tool calls. Count the user messages, find the matching block, attach it.

The trouble was that not every message with role `user` is something a person typed. While a turn is running, the Host injects internal reminders, such as "Native provider work has completed", so the model knows a background run finished. They are stored as `user` messages and hidden from the chat. But they are injected mid-turn, and they write no marker to the trace.

An earlier fix had said the opposite: count internal messages as turns anyway, because skipping them once dropped a whole turn's tool calls. That was true for the internal messages a watcher writes, which do open a turn. It was wrong for reminders. Every reminder pushed the counter one ahead of the trace, and every card after it landed one message late.

## The fix

An internal message now opens a turn only when the trace has a `user_input` marker with the same content. Only watcher observations write such markers, so they still line up, and reminders are skipped without moving the counter. They stay hidden either way.

Sessions saved before markers carried content have nothing to compare, so they keep the old position-based matching. That limitation is written down next to the code.

## How we checked

The new tests in `tests/unit/test_host_session.py` build a session that looks like the one that broke: a Claude Code turn, a Codex turn, an approval turn and a Stop turn, with reminders injected in the middle. They save it through the real JSONL storage, rebuild it the way a reconnecting browser does, and check that each card sits under its own message, including an approval that was still pending at reload. On main, five of them fail. With the fix, they pass.

The lesson is a small one: a role is not a meaning. "This message has role `user`" and "a person started a turn here" were treated as the same fact, and they are only the same most of the time.
