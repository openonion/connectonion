# yolo

Approval-free, bounded autonomous work backed by the existing ULW engine.

## Usage

```python
from connectonion import Agent
from connectonion.useful_plugins import enable_yolo, tool_approval, yolo

agent = Agent("worker", plugins=[tool_approval, yolo])
enable_yolo(agent, turns=10)
agent.input("Fix the failing tests")
```

`enable_yolo()` can be called before the first input. The plugin activates after
the session is initialized and before the first model or tool call.

For the built-in coding agent:

```bash
co ai --yolo "Fix the failing tests" --yolo-turns 10
co ai --yolo "/deploy-oo-chat" --yolo-turns 10
```

## Compatibility

YOLO is the public name for the existing ULW behavior. The old imports remain
valid:

```python
from connectonion.useful_plugins import handle_ulw_mode_change, ulw
```

The frontend wire mode and persisted session fields also remain unchanged:

```json
{
  "mode": "ulw",
  "ulw_turns": 10,
  "ulw_turns_used": 0,
  "skip_tool_approval": true
}
```

Existing `mode_change` messages and `ulw_turns_reached` checkpoint events keep
working. See [ulw](ulw.md) for the compatibility protocol.
