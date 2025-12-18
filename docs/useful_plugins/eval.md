# eval

Debug and test AI agent prompts and tools during development.

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_plugins import eval

agent = Agent("assistant", tools=[search], plugins=[eval])

agent.input("Search for Python docs")
# ... agent executes ...
# /evaluating...
# ✓ Task completed successfully
```

## How It Works

The plugin hooks into two lifecycle events:

1. **`after_user_input`**: Generates expected outcome (if not already set)
2. **`on_complete`**: Evaluates if task completed correctly

### Why `on_complete`?

The evaluation needs to see the **entire execution** - all iterations, all tool calls, and the final response.

```
User Input
    ↓
📝 Generate Expected (after_user_input)
    ↓
┌─────────────────── ITERATIONS ──────────────────┐
│ LLM → Tools → LLM → Tools → ... → Final Response│
└─────────────────────────────────────────────────┘
    ↓
✓ Evaluate (on_complete) - sees full trace + result
```

The `on_complete` event fires once after the agent finishes all iterations

## Events

| Handler | Event | Purpose |
|---------|-------|---------|
| `generate_expected` | `after_user_input` | Generate expected outcome |
| `evaluate_completion` | `on_complete` | Evaluate actual vs expected |

## Combine with re_act

Best used with re_act for full debugging:

```python
from connectonion.useful_plugins import re_act, eval

agent = Agent("assistant", tools=[search], plugins=[re_act, eval])
# re_act sets expected during planning
# eval evaluates completion against that expected
```

## Session Data

The plugin stores:
- `agent.current_session['expected']` - Expected outcome
- `agent.current_session['evaluation']` - Evaluation result

## When to Use

- Testing new prompts or tools
- Debugging agent behavior
- Validating task completion
- Development and experimentation

## Customizing

Need to modify eval's behavior? Copy the source to your project:

```bash
co copy eval
```

Then import from your local copy:

```python
# from connectonion.useful_plugins import eval  # Before
from plugins.eval import eval                    # After - customize freely!
```
