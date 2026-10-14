# 1.9.2b29: read by your own agent

*2026-10-14*

We handed a long working session to a colleague and checked what the server held. The page was
clean: other people's addresses and phone numbers were masked, and so were the names from our
contact notes. The AI's replies were not. The session had read our mail and our notes on people,
and its replies passed on personal trips, appointments and family matters.

Masking finds what has a shape: an address, a number, a name we already know. A family trip has no
shape. Flagging a few sensitive words for the sender to hunt down was not enough either: a
reviewer had to read hundreds of kilobytes, and still missed things.

Now your own coding agent reads every sentence before you see the preview. A Codex session is read
by Codex, a Claude Code session by Claude Code, on your own plan. Each private sentence becomes
`[removed: health]`, `[removed: travel and home]` and so on, in the page and in the copy that goes
with it. The preview tells you how many went and where, and `--edit` puts any back.

```bash
python -m pip install --upgrade 'connectonion==1.9.2b29'
```

See the [release notes](../releases/1.9.2b29.md).
