# Full access (YOLO)

Full access is ConnectOnion's operator-only, approval-free mode for bounded
autonomous work. “YOLO” is the recognizable shorthand used by the CLI.

## Usage

```python
from connectonion import Agent
from connectonion.useful_plugins import (
    enable_full_access,
    full_access,
    tool_approval,
)

agent = Agent("worker", plugins=[tool_approval, full_access])
enable_full_access(agent, turns=10)
agent.input("Refactor the codebase")
```

The shorthand is equivalent:

```python
from connectonion.useful_plugins import enable_yolo, tool_approval, yolo

agent = Agent("worker", plugins=[tool_approval, yolo])
enable_yolo(agent, turns=10)
```

For the built-in coding agent:

```bash
co ai --yolo "Fix the failing tests" --yolo-turns 10
```

## Behavior

When activated, Full access:

1. skips tool approval prompts for the local/admin operator;
2. continues after each completed turn;
3. pauses at the Host-owned turn ceiling; and
4. lets the operator continue locally, switch modes, or stop.

The canonical mode-change request is:

```json
{ "type": "mode_change", "mode": "full_access", "turns": 10 }
```

At the limit, the frontend receives:

```json
{ "type": "full_access_checkpoint", "turns_used": 10, "max_turns": 10 }
```

The canonical responses are:

- `{ "type": "FULL_ACCESS_RESPONSE", "action": "continue", "turns": 10 }`
- `{ "type": "FULL_ACCESS_RESPONSE", "action": "switch_mode", "mode": "default" }`

Any other response exits to Default. A hosted grant cannot be extended beyond
the launch-time ceiling; another durable mode transaction is required.

## Session state

```json
{
  "mode": "full_access",
  "full_access_turns": 10,
  "full_access_turns_used": 0,
  "skip_tool_approval": true
}
```

Client snapshots never grant Full access by themselves. The Host validates the
authenticated operator, launch policy, remaining turn budget, and session
ownership before restoring or changing this state.

## Mid-run direction

The frontend can update the goal while the agent is working:

```json
{ "type": "prompt_update", "prompt": "Focus on the authentication module" }
```

## Compatibility window

Versions before 1.7 used the name “ULW” and corresponding lower-case IDs and
field prefixes. New readers accept those legacy inputs only at the migration
boundary, normalize them immediately, and never emit or newly persist them.
Deprecated imports remain available from
`connectonion.useful_plugins.ulw` for one compatibility window.

## Source

`connectonion/useful_plugins/full_access.py`
