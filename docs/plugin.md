# Plugin System

Plugins are reusable event lists. Package capabilities like reflection and reuse them across agents.

---

## Quick Start (60 seconds)

```python
from connectonion import Agent, after_llm

def log_llm(agent):
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'llm_call':
        print(f"💬 {trace['model']}: {trace['duration_ms']:.0f}ms")

# A plugin is an event list
simple_logger = [after_llm(log_llm)]

# Use it (plugins takes a list of event lists)
agent = Agent("assistant", tools=[search], plugins=[simple_logger])

agent.input("Search for Python")
# 💬 gpt-4o-mini: 234ms
```

That's it!

---

## What is a Plugin?

**A plugin is an event list:**

```python
from connectonion import after_llm, after_tool

# This is a plugin (one event list)
reflection = [after_tool(add_reflection)]

# This is also a plugin (one event list with multiple events)
logger = [after_llm(log_llm), after_tool(log_tool)]

# Use them (plugins takes a list of plugins)
agent = Agent("assistant", tools=[search], plugins=[reflection, logger])
```

**Just like tools:**
- Tools: `Agent(tools=[search, calculate])`
- Plugins: `Agent(plugins=[reflection, logger])`

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
    plugins=[logger],                                          # List of event lists
    on_events=[after_llm(add_timestamp), after_tool(log_tool)] # One event list
)
```

---

## Example: Reflection Plugin

```python
from connectonion import Agent, after_tool, llm_do

def add_reflection(agent):
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        result = trace['result']

        reflection = llm_do(
            f"Result: {result[:200]}\n\nWhat did we learn?",
            system_prompt="Be concise.",
            temperature=0.3
        )

        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"🤔 {reflection}"
        })

        print(f"💭 {reflection}")

# Plugin is an event list
reflection = [after_tool(add_reflection)]

# Use it
agent = Agent("researcher", tools=[search], plugins=[reflection])

agent.input("Search for Python")
# 💭 We learned Python is a popular programming language...
```

---

## Example: Todo Plugin

```python
from connectonion import Agent, after_user_input, after_tool, llm_do
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
todo = [after_user_input(create_todos), after_tool(check_todos)]

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
reflection = [after_tool(add_reflection)]
logger = [after_llm(log_llm), after_tool(log_tool)]

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
my_plugin = [after_llm(handler1), after_tool(handler2)]

# Use it (plugins takes a list of event lists)
agent = Agent("assistant", tools=[search], plugins=[my_plugin])
```

**on_events vs plugins:**
- `on_events=[after_llm(h1), after_tool(h2)]` → one event list
- `plugins=[plugin1, plugin2]` → list of event lists

---

## What's Next?

- [Event System](/on_events) - Learn about events
- [llm_do](/llm_do) - Use `llm_do` in handlers
- [Examples](/examples) - More examples
