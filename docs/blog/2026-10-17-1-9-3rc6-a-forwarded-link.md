# 1.9.3rc6: a forwarded link no longer takes the name

*2026-10-17*

Checking 1.9.3rc5 from PyPI turned up one problem. A handoff addressed to one agent's mailbox and
accepted by a different agent re-pointed that agent's name to the acceptor's key. Since rc5, that key
decides who can open everything sent afterwards. This candidate saves the acceptor under its own name,
leaves the addressed name its own key, says so in `co handoff status`, and repairs names rc5 had
already re-pointed. Why a name is not a key is in
[A name is not a key](2026-10-17-a-name-is-not-a-key.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc6'
```
