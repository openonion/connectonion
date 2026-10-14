# 1.9.2b30: from whichever agent you used

*2026-10-14*

A handoff used to start only from a Codex or Claude Code session. Plenty of
people do their thinking in Gemini CLI, opencode, Factory's droid, Cursor or
Grok, and asking them to switch agents to pass work on was the wrong way round.

Now `co handoff send` reads whichever one you were using, from where that agent
keeps its own sessions: the messages and the AI's replies, never its tool calls.
Cursor's conversations are read from its own database without changing it. The
person receiving it still pastes one line into Codex or Claude Code.

```bash
python -m pip install --upgrade 'connectonion==1.9.2b30'
```

See the [release notes](../releases/1.9.2b30.md).
