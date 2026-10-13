# The thread you open

*2026-10-13*

Aaron read the Codex threads our end-to-end runs had left on Parrot, from his
phone. They began with installing uv, linking skills and accepting a code. None
of it said what the other person had been talking about, or what they had
decided, which is the one thing a person handed a session wants to know.

So `co handoff open` now opens that session. In Codex it is a thread named
`Handoff from Aaron: Fix invoice dedupe`, and in it the sender's conversation
is replayed turn by turn, each bubble labelled with who said it. The last
bubble is the recipient's own agent: one line on who handed what, then what
was discussed, what was concluded and why, what is still open, and a small
ASCII diagram of how the conversation got there. It ends with "You can keep
asking me here." Behind it, a second turn is already doing the work.

On this session's own handoff, 190 exchanges, that took 50 seconds.
Codex has no API for writing history. The replay is in its session format,
checked against 0.162.1, and falls back to one seeded turn when a newer Codex
refuses it.
