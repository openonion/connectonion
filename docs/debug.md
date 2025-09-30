# Console Output

ConnectOnion shows you what's happening by default - just like FastAPI, npm, and cargo.

## No Configuration Needed

```python
# Console output is always visible
agent = Agent("assistant", tools=[my_tool])
result = agent.input("Do something")
```

## What You See

```
[10:32:14] INPUT: Generate a Python function
[10:32:14] → LLM Request (gpt-4)
[10:32:15] ← LLM Response (850ms): 1 tool calls
[10:32:15] → Tool: generate_code({'language': 'python'})
[10:32:15] ← Result (120ms): def sort_numbers...
[10:32:16] ✓ Complete (2.3s)
```

Console output helps you understand:
- What the agent is doing
- Which tools are being called
- How long operations take
- When errors occur

## Enhanced Output with @xray

Want more details? Use the `@xray` decorator:

```python
from connectonion import Agent, xray

@xray
def my_tool(query: str) -> str:
    """This tool shows a Rich table with detailed info."""
    return process(query)

agent = Agent("assistant", tools=[my_tool])
result = agent.input("Search for python")
```

Output includes a beautiful table:
```
╭──────────────────── @xray: my_tool ────────────────────╮
│  agent       assistant                                 │
│  task        Search for python                         │
│  iteration   1                                         │
│  ───────────────────────────────────────────────────   │
│  query       python                                    │
│  result      Found 10 results...                       │
│  timing      340.2ms                                   │
╰────────────────────────────────────────────────────────╯
```

## Optional File Logging

Want to keep logs? Use the `log` parameter:

```python
# Log to file (console still shows output)
agent = Agent("assistant", log="agent.log")

# Or use environment variable
# CONNECTONION_LOG=agent.log python agent.py
```

## Why Console is Always On

**Design Philosophy:** Good UX means showing what's happening by default.

When you run:
- `npm install` - you see packages being installed
- `cargo build` - you see compilation progress
- `fastapi dev` - you see server logs

Why should agents be silent? ConnectOnion follows the same principle - **visibility by default**.

## What Changed?

**Previous design (0.0.6 and earlier):**
- Console was off by default
- Required `debug=True` to see output
- Confusing - output wasn't "debugging", it was normal operation

**Current design (0.0.7+):**
- Console is always on
- Shows what's happening (like FastAPI, npm, cargo)
- `@xray` decorator adds enhanced Rich tables for specific tools
- No `debug` parameter - it's not debugging, it's just good UX

**Rationale:** The console output isn't "debug" information - it's useful operation visibility that users expect. Hiding it by default created confusion and poor developer experience.