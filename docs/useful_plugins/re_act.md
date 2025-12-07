# re_act

ReAct (Reason + Act) plugin - Adds planning and reflection to agents.

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_plugins import re_act

agent = Agent("assistant", tools=[search], plugins=[re_act])

agent.input("Search for Python tutorials")
# /planning...
# 💭 Will search for Python tutorials first.
# ... tool executes ...
# /reflecting...
# 🤔 Found Python basics, task complete.
```

## How It Works

The plugin hooks into two points in the agent lifecycle:

1. **`after_user_input`**: Plans what to do (💭)
2. **`after_tools`**: Reflects on results and plans next step (🤔)

### Why `after_tools`?

Each LLM call may trigger **multiple tools in parallel**. The reflection needs to see ALL tool results before deciding next steps.

```
User Input
    ↓
💭 Plan (after_user_input)
    ↓
LLM decides to call 3 tools
    ↓
┌─────────────────────────────────────┐
│ tool_1 executes ──┐                 │
│ tool_2 executes ──┼── all complete  │
│ tool_3 executes ──┘                 │
└─────────────────────────────────────┘
    ↓
🤔 Reflect (after_tools) - sees all 3 results
    ↓
LLM decides next action or responds
```

If we used `after_each_tool`, reflection would fire 3 times with partial information.

## Events

| Handler | Event | Purpose |
|---------|-------|---------|
| `plan_task` | `after_user_input` | Generate initial plan |
| `reflect` | `after_tools` | Reflect on tool results |

## Combine with eval

For debugging, combine with the eval plugin:

```python
from connectonion.useful_plugins import re_act, eval

agent = Agent("assistant", tools=[search], plugins=[re_act, eval])
# re_act provides plan as expected outcome
# eval evaluates if task completed correctly
```

## Customization

The plan is stored in `agent.current_session['expected']` and can be used by other plugins.
