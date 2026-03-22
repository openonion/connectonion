# ulw (Ultra Light Work)

Autonomous agent mode: the agent keeps working turn after turn without asking for approval, until it reaches a checkpoint or declares itself "genuinely complete".

## Usage

```python
from connectonion import Agent
from connectonion.useful_plugins import tool_approval, ulw

agent = Agent("worker", plugins=[tool_approval, ulw])
```

Requires `tool_approval` — ULW mode works by setting a flag that tells `tool_approval` to skip all checks.

## What it does

When activated (via a `mode_change` event from the frontend):
1. Skips all tool approval prompts (`skip_tool_approval = True`)
2. After each turn completes, automatically starts another turn
3. At the turn limit (default: 100), pauses for user input
4. User can continue, extend turns, or switch back to safe mode

## How to trigger ULW mode

ULW is triggered from the web chat UI by sending a mode change message:

```json
{ "type": "mode_change", "mode": "ulw", "turns": 10 }
```

In code (programmatic use):

```python
from connectonion.useful_plugins.ulw import handle_ulw_mode_change

handle_ulw_mode_change(agent, turns=10)
agent.input("Refactor the entire codebase to use async functions")
```

## Turn-based checkpoints

After reaching `ulw_turns`, the agent pauses and the frontend receives:

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

## Events used

| Event | Handler | Purpose |
|-------|---------|---------|
| `on_complete` | `ulw_keep_working` | Start next turn if turns remain |
| `before_iteration` | `poll_prompt_update` | Check for goal updates from frontend |
| `before_llm` | `inject_ulw_prompt` | Inject current goal into system prompt |

## Source

```
connectonion/useful_plugins/ulw.py
```
