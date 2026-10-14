# 1.9.2rc1: both directions, end to end

*2026-10-14*

Before calling handoff stable we ran it the way two people would: one in
Claude Code, one in Codex, each starting fresh, then the other way round. The
sender said "hand this to Bob" and approved the preview. Bob pasted one line.
His agent did the work and sent a patch back, and it applied cleanly on the
sender's side. Nobody else had to do anything.

This release candidate carries two small fixes from those runs.

```bash
python -m pip install --upgrade 'connectonion==1.9.2rc1'
```

See the [release notes](../releases/1.9.2rc1.md).
