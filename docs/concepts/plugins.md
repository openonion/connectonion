# Plugins

Plugins are reusable event handlers. Package capabilities and reuse them across agents.

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_plugins import re_act

agent = Agent("assistant", tools=[search], plugins=[re_act])
agent.input("Search for Python")
# 💭 Planning: Will search for Python info first.
# ... tool executes ...
# 🤔 Reflecting: Found Python basics, task complete.
```

## What is a Plugin?

A plugin is a list of event handlers:

```python
from connectonion import after_user_input, after_tools

# Define handlers
def plan(agent):
    print("Planning...")

def reflect(agent):
    print("Reflecting...")

# Plugin = list of event handlers
re_act = [after_user_input(plan), after_tools(reflect)]

# Use it
agent = Agent("assistant", tools=[search], plugins=[re_act])
```

## Plugin vs on_events

```python
# on_events: one list (custom for this agent)
agent = Agent("a", on_events=[after_llm(handler)])

# plugins: list of lists (reusable across agents)
agent = Agent("a", plugins=[re_act, logger])
```

## Built-in Plugins

| Plugin | Purpose | Docs |
|--------|---------|------|
| `re_act` | Planning + reflection (ReAct pattern) | [re_act.md](../useful_plugins/re_act.md) |
| `eval` | Task evaluation for debugging | [eval.md](../useful_plugins/eval.md) |
| `image_result_formatter` | Format images for vision models | [image_result_formatter.md](../useful_plugins/image_result_formatter.md) |
| `shell_approval` | Approve shell commands before execution | [shell_approval.md](../useful_plugins/shell_approval.md) |
| `tool_approval` | Web-based approval for dangerous tools | [tool_approval.md](../useful_plugins/tool_approval.md) |

```python
from connectonion.useful_plugins import re_act, eval, image_result_formatter, shell_approval, tool_approval

# Combine plugins
agent = Agent("assistant", plugins=[re_act, image_result_formatter])
```

## Writing Custom Plugins

Simple example - log each tool execution:

```python
from connectonion import Agent, after_each_tool

def log_tool(agent):
    trace = agent.current_session['trace'][-1]
    print(f"✓ {trace['tool_name']} completed")

# Plugin = list of handlers
logger = [after_each_tool(log_tool)]

# Use it
agent = Agent("assistant", tools=[search], plugins=[logger])
```

For more complex plugins, see [Events](events.md) for available event hooks.

## Reusing Plugins

```python
# Define once
logger = [after_each_tool(log_tool)]

# Use across agents
researcher = Agent("researcher", tools=[search], plugins=[logger])
writer = Agent("writer", tools=[generate], plugins=[logger])
```

## Next Steps

- [Events](events.md) - Available event hooks
- [llm_do](llm_do.md) - Use LLM in handlers
- [Built-in Plugins](../useful_plugins/) - Detailed plugin docs
