# Plugin System

Plugins are reusable event lists. Package capabilities like reasoning and reuse them across agents.

---

## Quick Start (60 seconds)

```python
from connectonion import Agent
from connectonion.useful_plugins import re_act

# Use built-in ReAct plugin
agent = Agent("assistant", tools=[search], plugins=[re_act])

agent.input("Search for Python")
# /planning...
# 💭 Will search for Python info first.
# ... tool executes ...
# /reflecting...
# 🤔 Found Python basics, task complete.
```

That's it!

---

## What is a Plugin?

**A plugin is an event list:**

```python
from connectonion import after_user_input, after_tools, after_each_tool

# This is a plugin (one event list)
re_act = [after_user_input(plan), after_tools(reflect)]  # after_tools for message injection

# This is also a plugin (one event list with multiple events)
logger = [after_each_tool(log_tool)]  # after_each_tool for per-tool logging

# Use them (plugins takes a list of plugins)
agent = Agent("assistant", tools=[search], plugins=[re_act, logger])
```

**Just like tools:**
- Tools: `Agent(tools=[search, calculate])`
- Plugins: `Agent(plugins=[re_act, logger])`

---

## Plugin vs on_events

The difference:
- **on_events**: Takes one event list (custom for this agent)
- **plugins**: Takes a list of event lists (reusable across agents)

```python
from datetime import datetime

# Reusable plugin (an event list)
logger = [after_llm(log_llm)]

# on_events is one event list
agent = Agent(
    "assistant",
    tools=[search],
    plugins=[logger],                                                    # List of event lists
    on_events=[after_llm(add_timestamp), after_each_tool(log_tool)]     # One event list
)
```

---

## Built-in Plugins (useful_plugins)

ConnectOnion provides ready-to-use plugins that you can import and use immediately.

### ReAct Plugin

Implements the ReAct (Reason + Act) pattern with planning and reflection:

```python
from connectonion import Agent
from connectonion.useful_plugins import re_act

agent = Agent("assistant", tools=[search], plugins=[re_act])

agent.input("Search for Python and explain it")
# /planning...
# 💭 Will search for Python info first, then summarize key features.
# ... tool executes ...
# /reflecting...
# 🤔 Got Python basics, now explain its use cases.
```

**How it works:**
1. **After user input**: Plans what to do (💭)
2. **After each tool**: Reflects on results and plans next step (🤔)
3. **Agent decides** when task is complete

### Eval Plugin

Debug and test AI agent prompts and tools during development:

```python
from connectonion import Agent
from connectonion.useful_plugins import eval

agent = Agent("assistant", tools=[search], plugins=[eval])

agent.input("Search for Python")
# /evaluating...
# Task completed successfully. Search tool was used to find Python info.
```

**Best with re_act** - combine both for full debugging:

```python
from connectonion.useful_plugins import re_act, eval

agent = Agent("assistant", tools=[search], plugins=[re_act, eval])

agent.input("Search for Python")
# /planning...
# 💭 Will search for Python info first.
# ... tool executes ...
# /reflecting...
# 🤔 Got Python basics.
# /evaluating...
# Task completed successfully.
```

**How it works:**
1. **After user input**: Generates expected outcome (if not already set by re_act's plan)
2. **On complete**: Evaluates if task completed correctly

**When to use:**
- Testing new prompts or tools
- Debugging agent behavior
- Validating task completion
- Development and experimentation

### Image Result Formatter Plugin

Automatically converts base64 image results to proper image message format for vision models:

```python
from connectonion import Agent
from connectonion.useful_plugins import image_result_formatter

agent = Agent("assistant", tools=[take_screenshot], plugins=[image_result_formatter])

agent.input("Take a screenshot of the homepage and describe what you see")
# 🖼️  Formatted tool result as image (image/png)
# Agent can now see and analyze the actual image, not just base64 text!
```

**When to use:**
- Tools that return screenshots as base64
- Image generation tools
- Any tool that returns visual data

**Supported formats:** PNG, JPEG, WebP, GIF

**What it does:**
- Detects base64 images in tool results (data URLs or plain base64)
- Converts to OpenAI vision API format
- Allows multimodal LLMs to see images visually instead of as text

### Shell Approval Plugin

Prompts for user approval before executing shell commands (except safe read-only commands):

```python
from connectonion import Agent, Shell
from connectonion.useful_plugins import shell_approval

shell = Shell()
agent = Agent("assistant", tools=[shell], plugins=[shell_approval])

agent.input("Clean up temp files")
# ┌─ Shell Command ─────────────────┐
# │ rm -rf /tmp/test                │
# └─────────────────────────────────┘
# Execute this command?
#   ❯ Yes, execute
#     Auto approve 'rm' in this session
#     No, tell agent what I want
```

**Safe commands (no approval needed):**
- `ls`, `cat`, `head`, `tail` - File reading
- `grep`, `rg`, `find`, `fd` - Search
- `git status`, `git log`, `git diff` - Git read operations
- `pwd`, `echo`, `date`, `whoami` - Info commands
- `tree`, `wc`, `file`, `stat` - File info
- And more read-only commands...

**All other commands require approval.**

**How it works:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    Shell Approval Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Agent.input()                                                  │
│       ↓                                                         │
│  tool_executor.execute_single_tool()                            │
│       ↓                                                         │
│  Sets current_session['pending_tool'] = {name, arguments, id}   │
│       ↓                                                         │
│  agent._invoke_events('before_each_tool')                       │
│       ↓                                                         │
│  shell_approval._check_approval(agent)                          │
│       ↓                                                         │
│  ┌─────────────────────────────────────────┐                    │
│  │ 1. Check if bash/shell/run tool         │                    │
│  │ 2. Check if auto-approved command type  │                    │
│  │ 3. Check if safe read-only command      │                    │
│  │ 4. Show Panel + pick() UI               │                    │
│  │ 5. Handle user choice                   │                    │
│  └─────────────────────────────────────────┘                    │
│       ↓                                                         │
│  Clears current_session['pending_tool']                         │
│       ↓                                                         │
│  Execute tool or raise ValueError                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Using Multiple Plugins Together

```python
from connectonion import Agent
from connectonion.useful_plugins import re_act, image_result_formatter

# Combine plugins for powerful agents
agent = Agent(
    name="visual_researcher",
    tools=[take_screenshot, search, analyze],
    plugins=[image_result_formatter, re_act]
)

# Now you get:
# 🖼️  Image formatting for screenshots
# 💭 Planning: What to do
# 🤔 Reflection: What we learned and next step
```

---

## Writing Custom Plugins

Learn by example - here's how the reflection plugin is implemented:

### Step 1: Message Compression Helper

```python
from typing import List, Dict

def _compress_messages(messages: List[Dict], tool_result_limit: int = 150) -> str:
    """
    Compress conversation messages with structure:
    - USER messages → Keep FULL
    - ASSISTANT tool_calls → Keep parameters FULL
    - ASSISTANT text → Keep FULL
    - TOOL results → Truncate to tool_result_limit chars
    """
    lines = []

    for msg in messages:
        role = msg['role']

        if role == 'user':
            lines.append(f"USER: {msg['content']}")

        elif role == 'assistant':
            if 'tool_calls' in msg:
                tools = [f"{tc['function']['name']}({tc['function']['arguments']})"
                         for tc in msg['tool_calls']]
                lines.append(f"ASSISTANT: {', '.join(tools)}")
            else:
                lines.append(f"ASSISTANT: {msg['content']}")

        elif role == 'tool':
            result = msg['content']
            if len(result) > tool_result_limit:
                result = result[:tool_result_limit] + '...'
            lines.append(f"TOOL: {result}")

    return "\n".join(lines)
```

**Why this works:**
- Keep user messages FULL (need to know what they asked)
- Keep tool parameters FULL (exactly what actions were taken)
- Keep assistant text FULL (reasoning/responses)
- Truncate tool results (save tokens while maintaining overview)

### Step 2: Event Handler Function

```python
from connectonion.events import after_tools  # Use after_tools for message injection
from connectonion.llm_do import llm_do

def _add_reflection(agent) -> None:
    """Reflect on tool execution result (fires after all tools in round complete)"""
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        # Extract current tool execution
        user_prompt = agent.current_session.get('user_prompt', '')
        tool_name = trace['tool_name']
        tool_args = trace['arguments']
        tool_result = trace['result']

        # Compress conversation messages
        conversation = _compress_messages(agent.current_session['messages'])

        # Build prompt with conversation context + current execution
        prompt = f"""CONVERSATION:
{conversation}

CURRENT EXECUTION:
User asked: {user_prompt}
Tool: {tool_name}({tool_args})
Result: {tool_result}

Reflect in 1-2 sentences on what we learned:"""

        reflection_text = llm_do(
            prompt,
            model="co/gpt-4o",
            temperature=0.3,
            system_prompt="You reflect on tool execution results to generate insights about what was learned and why it's useful for answering the user's question."
        )

        # Add reflection as assistant message (safe in after_tools)
        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"💭 {reflection_text}"
        })

        agent.console.print(f"[dim]💭 {reflection_text}[/dim]")
```

**Key insights:**
- Access agent state via `agent.current_session`
- Use `llm_do()` for AI-powered analysis
- Add results back to conversation messages
- Print to console for user feedback

### Step 3: Create Plugin (Event List)

```python
# Plugin is an event list
reflection = [after_tools(_add_reflection)]  # Use after_tools for message injection
```

**That's it!** A plugin is just an event list.

### Step 4: Use Your Plugin

```python
agent = Agent("assistant", tools=[search], plugins=[reflection])
```

---

## Quick Custom Plugin Example

Build a simple plugin in 3 lines:

```python
from connectonion import Agent, after_each_tool

def log_tool(agent):
    trace = agent.current_session['trace'][-1]
    print(f"✓ {trace['tool_name']} completed in {trace['timing']}ms")

# Plugin is an event list
logger = [after_each_tool(log_tool)]  # per-tool logging

# Use it
agent = Agent("assistant", tools=[search], plugins=[logger])
```

---

## Example: Todo Plugin

```python
from connectonion import Agent, after_user_input, after_tools, llm_do
from pydantic import BaseModel
from typing import List

class TodoList(BaseModel):
    tasks: List[str]

# Store todos
todos = []

def create_todos(agent):
    prompt = agent.current_session['user_prompt']

    todo_list = llm_do(
        f"Break into 3-5 steps:\n{prompt}",
        output=TodoList,
        temperature=0.2
    )

    todos.clear()
    todos.extend(todo_list.tasks)

    print("📝 Todos:")
    for i, task in enumerate(todos, 1):
        print(f"  {i}. {task}")

def check_todos(agent):
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        result = trace['result']

        for task in todos:
            check = llm_do(
                f"Todo: {task}\nResult: {result[:200]}\n\nDone? (yes/no)",
                temperature=0
            )

            if 'yes' in check.lower():
                print(f"✅ {task}")

# Plugin is an event list
todo = [after_user_input(create_todos), after_tools(check_todos)]  # after_tools fires once per round

# Use it
agent = Agent("assistant", tools=[search, analyze], plugins=[todo])

agent.input("Research Python and summarize")
# 📝 Todos:
#   1. Search for Python
#   2. Analyze results
#   3. Summarize findings
# ✅ Search for Python
```

---

## Reusing Plugins

Use the same plugin across agents:

```python
# Define once
reflection = [after_tools(add_reflection)]  # message injection → after_tools
logger = [after_llm(log_llm), after_each_tool(log_tool)]  # per-tool logging → after_each_tool

# Use in multiple agents
researcher = Agent("researcher", tools=[search], plugins=[reflection, logger])
writer = Agent("writer", tools=[generate], plugins=[reflection])
analyst = Agent("analyst", tools=[calculate], plugins=[logger])
```

---

## Summary

**A plugin is an event list:**

```python
# Define a plugin (an event list)
my_plugin = [after_llm(handler1), after_tools(handler2)]  # Use after_tools for message injection

# Use it (plugins takes a list of event lists)
agent = Agent("assistant", tools=[search], plugins=[my_plugin])
```

**on_events vs plugins:**
- `on_events=[after_llm(h1), after_each_tool(h2)]` → one event list
- `plugins=[plugin1, plugin2]` → list of event lists

**Event naming:**
- `after_each_tool` → fires for EACH tool (per-tool logging/monitoring)
- `after_tools` → fires ONCE after all tools (safe for message injection)

---

## Built-in Plugins Reference

See [useful_plugins/](useful_plugins/) for detailed documentation on each plugin.

| Plugin | Purpose | Documentation |
|--------|---------|---------------|
| `re_act` | ReAct reasoning (plan + reflect) | [re_act.md](useful_plugins/re_act.md) |
| `eval` | Task evaluation/debugging | [eval.md](useful_plugins/eval.md) |
| `image_result_formatter` | Format images for vision | [image_result_formatter.md](useful_plugins/image_result_formatter.md) |
| `shell_approval` | Shell command approval | [shell_approval.md](useful_plugins/shell_approval.md) |
| `gmail_plugin` | Gmail OAuth flow | [gmail_plugin.md](useful_plugins/gmail_plugin.md) |
| `calendar_plugin` | Calendar OAuth flow | [calendar_plugin.md](useful_plugins/calendar_plugin.md) |

---

## What's Next?

- [Event System](/on_events) - Learn about events
- [llm_do](/llm_do) - Use `llm_do` in handlers
- [Examples](/examples) - More examples
