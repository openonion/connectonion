# YOLO

YOLO is the CLI and API shorthand for [Full access](full_access.md), the
operator-only, approval-free mode with a Host-owned turn bound.

```python
from connectonion.useful_plugins import enable_yolo, tool_approval, yolo

agent = Agent("worker", plugins=[tool_approval, yolo])
enable_yolo(agent, turns=10)
agent.input("Fix the failing tests")
```

```bash
co ai --yolo "Fix the failing tests" --yolo-turns 10
```

The canonical mode ID, types, state, and events use `full_access`. See the
linked page for authority rules, checkpoints, and migration behavior.
