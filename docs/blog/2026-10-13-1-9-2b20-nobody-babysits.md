# 1.9.2b20: a handoff nobody has to babysit

*2026-10-13*

Paste one block into your coding agent and it takes over: it accepts the
handoff, does the work in your folder, and tells the sender it is done, with the
patch attached. The sender sees "Done" in `co handoff status`. You are asked
only before something that cannot be undone or that leaves your machine.

```bash
python -m pip install --upgrade 'connectonion==1.9.2b20'
```

See the [release notes](../releases/1.9.2b20.md).
