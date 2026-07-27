# yolo (with ULW compatibility)

YOLO is the public autonomous mode: the agent keeps working turn after turn
without asking for approval until it reaches a bounded checkpoint. The original
`ulw` plugin and frontend protocol remain available as compatibility aliases.

## Usage

```python
from connectonion import Agent
from connectonion.useful_plugins import tool_approval, yolo

agent = Agent("worker", plugins=[tool_approval, yolo(turns=25)])
```

`yolo(turns=N)` activates itself on the first user input. It works with
`tool_approval` by setting a bounded autonomous mode that bypasses approval
checks.

Existing frontend-controlled agents can continue using:

```python
from connectonion.useful_plugins import tool_approval, ulw

agent = Agent("worker", plugins=[tool_approval, ulw])
```

## What it does

When activated:
1. Skips all tool approval prompts (`skip_tool_approval = True`)
2. After each turn completes, automatically starts another turn
3. At the turn limit (default: 100), pauses for user input
4. User can continue, extend turns, or switch back to safe mode

## How to trigger YOLO mode

From the `co ai` CLI:

```bash
co ai --yolo --yolo-turns 25 "Complete the task"
co ai --yolo "/project-skill"
```

From a frontend:

```json
{ "type": "mode_change", "mode": "yolo", "turns": 10 }
```

The runtime normalizes that public alias to the existing `ulw` wire mode. The
legacy ULW message remains supported:

```json
{ "type": "mode_change", "mode": "ulw", "turns": 10 }
```

In code, use the auto-activating plugin:

```python
from connectonion import Agent
from connectonion.useful_plugins import tool_approval, yolo

agent = Agent("worker", plugins=[tool_approval, yolo(turns=10)])
agent.input("Refactor the entire codebase to use async functions")
```

## Turn-based checkpoints

The legacy `ulw_turns` session keys and checkpoint event stay stable so current
SDK and oo-chat clients do not break. After reaching the budget, the frontend
receives:

```json
{ "type": "ulw_turns_reached", "turns_used": 10, "max_turns": 10 }
```

The user can respond with:
- `{ "action": "continue", "turns": 10 }` — extend by N more turns
- `{ "action": "switch_mode", "mode": "safe" }` — return to safe mode
- Anything else — exit to safe mode

## Prompt injection mid-session

The frontend can update the agent's goal while it's working:

```json
{ "type": "prompt_update", "prompt": "Focus on the authentication module" }
```

This is injected into the system prompt before each LLM call, keeping the agent on track.

## When to use

- Large refactoring tasks
- Batch code generation
- Extended research and writing sessions
- Any autonomous work where you don't want to approve every tool call

YOLO bypasses approval prompts. Invoke it only after the user has explicitly
authorized the full task and production targets.

## Events used

| Event | Handler | Purpose |
|-------|---------|---------|
| `after_user_input` | `activate_yolo` | Activate YOLO for `yolo(turns=N)` |
| `on_complete` | `ulw_keep_working` | Start next turn if turns remain |
| `on_stop_signal` | `stop_autonomous_mode` | Stop immediately on interrupt or hard rejection |
| `before_iteration` | `poll_prompt_update` | Check for goal updates from frontend |
| `before_llm` | `inject_ulw_prompt` | Inject current goal into system prompt |

## Source

```
connectonion/useful_plugins/ulw.py
```
