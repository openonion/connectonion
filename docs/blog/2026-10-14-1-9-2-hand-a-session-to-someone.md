# 1.9.2: hand a session to someone else's agent

*2026-10-14*

The usual handover is a long message that leaves out half of what you and your
AI worked out. 1.9.2 sends the session itself. You say "hand this to Bob" in
Codex or Claude Code, read exactly what would leave your machine, and say yes.
Bob pastes one line into his own agent, which picks up where yours stopped,
asks yours whatever the session does not answer, and sends the work back as a
patch.

Two things had to be true before we called it stable. Nothing private should
leave by accident: your own agent takes out sentences about health, family,
travel, money and other people before you even see the preview. And handing
over work must not hand over your agent: each side gets messages about that one
handoff, nothing more.

We ran it the way two people would, in both directions between Claude Code and
Codex, and the patch applied on the first try every time.

```bash
python -m pip install --upgrade 'connectonion==1.9.2'
```

See the [release notes](../releases/1.9.2.md).
