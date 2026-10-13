# 1.9.2b22: everything arrives with accept

*2026-10-13*

When someone picks up your handoff, their agent now gets your code, even
unpushed, and your session the moment it accepts, then gets on with the work.
The repository is rebuilt in their folder with your uncommitted changes applied.
Nothing waits on your machine being online.

```bash
python -m pip install --upgrade 'connectonion==1.9.2b22'
```

See the [release notes](../releases/1.9.2b22.md).
