# Built-in Plugins

Pre-built plugins that extend agent behavior via event hooks.

## Quick Reference

| Plugin | Purpose | Import |
|--------|---------|--------|
| [re_act](re_act.md) | ReAct reasoning pattern | `from connectonion.useful_plugins import re_act` |
| [eval](eval.md) | Task evaluation/debugging | `from connectonion.useful_plugins import eval` |
| [image_result_formatter](image_result_formatter.md) | Format images for vision | `from connectonion.useful_plugins import image_result_formatter` |
| [shell_approval](shell_approval.md) | Shell command approval | `from connectonion.useful_plugins import shell_approval` |
| [gmail_plugin](gmail_plugin.md) | Gmail OAuth flow | `from connectonion.useful_plugins import gmail_plugin` |
| [calendar_plugin](calendar_plugin.md) | Calendar OAuth flow | `from connectonion.useful_plugins import calendar_plugin` |

## Usage Pattern

```python
from connectonion import Agent
from connectonion.useful_plugins import re_act, eval

agent = Agent(
    "assistant",
    tools=[search],
    plugins=[re_act, eval]  # List of plugins
)
```

## Categories

### Reasoning
- **re_act** - Plan before acting, reflect after tools

### Debugging
- **eval** - Generate expected outcomes, evaluate completion

### Media
- **image_result_formatter** - Convert base64 images for vision models

### Security
- **shell_approval** - Require approval for shell commands

### OAuth
- **gmail_plugin** - Handle Gmail authentication flow
- **calendar_plugin** - Handle Calendar authentication flow

## Event Lifecycle

Understanding when events fire is key to writing plugins.

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  after_user_input                                   │
│  (re_act: plan_task, eval: generate_expected)       │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────── ITERATION LOOP ──────────────────┐
│                                                     │
│  before_llm → LLM Call → after_llm                  │
│                   │                                 │
│                   ▼                                 │
│        ┌─────────────────────┐                      │
│        │ Tool Calls (if any) │                      │
│        └─────────────────────┘                      │
│                   │                                 │
│                   ▼                                 │
│  ┌─────────────────────────────────────────────┐    │
│  │ before_tools (fires ONCE before all tools)  │    │
│  └─────────────────────────────────────────────┘    │
│                   │                                 │
│                   ▼                                 │
│  ┌─────────────────────────────────────────────┐    │
│  │ For EACH tool in parallel:                  │    │
│  │   before_each_tool → Execute → after_each_tool  │
│  │   (shell_approval)         (logging only!)      │
│  └─────────────────────────────────────────────┘    │
│                   │                                 │
│                   ▼                                 │
│  ┌─────────────────────────────────────────────┐    │
│  │ after_tools (fires ONCE after ALL tools)    │    │
│  │ (re_act: reflect, image_result_formatter)   │    │
│  │ ⚠️  ONLY place safe to modify messages       │    │
│  └─────────────────────────────────────────────┘    │
│                   │                                 │
│           Continue or Exit Loop                     │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  on_complete                                        │
│  (eval: evaluate_completion)                        │
└─────────────────────────────────────────────────────┘
```

### Key Distinction

- **`after_each_tool`**: Fires for EACH tool individually. Use for logging, monitoring, side effects. **DO NOT modify messages here.**
- **`after_tools`**: Fires ONCE after ALL tools complete. **ONLY place safe to modify messages.**

### Why This Matters

LLM APIs require tool results to match tool calls exactly. If you modify messages in `after_each_tool`, you'll break the tool_call_id sequence.

```
❌ WRONG - modifying messages in after_each_tool:
tool_1 result → modify messages → tool_2 result → API ERROR!

✅ CORRECT - modifying messages in after_tools:
tool_1 result → tool_2 result → tool_3 result → after_tools → modify messages → OK
```

**Rule:** If your plugin modifies `agent.current_session['messages']`, use `after_tools`.

### Error You'll See If You Get This Wrong

```
BadRequestError: 400 An assistant message with 'tool_calls' must be
followed by tool messages responding to each 'tool_call_id'.
The following tool_call_ids did not have response messages: call_xxx
```

If you see this error, check if any plugin is modifying messages in `after_each_tool` - move that logic to `after_tools`.

Example: If LLM calls 3 tools in one round:
- `before_tools` fires 1 time
- `before_each_tool` fires 3 times (logging only!)
- `after_each_tool` fires 3 times (logging only!)
- `after_tools` fires 1 time (safe to modify messages)
