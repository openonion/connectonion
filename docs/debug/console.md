# Console Output

ConnectOnion shows you what's happening by default - just like FastAPI, npm, and cargo.

## No Configuration Needed

```python
# Console output is always visible
agent = Agent("assistant", tools=[my_tool])
result = agent.input("Do something")
```

## What You See

When you run an agent, you'll see the onion stack banner and execution flow:

```
  ○
 ◎    my-assistant
●     ────────────────────
      connectonion v0.5.1
      co/o4-mini · 3 tools
      .co/logs/ · .co/evals/
      ────────────────────

[co] > "Generate a Python function"

[co] ○ o4-mini                                    1/10
[co] ● o4-mini · 1 tool · 150 tok · $0.0012       ⚡ 1.2s
[co]   ▸ generate_code(language="python")         ✓ 0.12s

[co] ═══════════════════════════════════════════════
[co] ✓ complete · 150 tokens · $0.0012 · 2.3s
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

## File Logging

ConnectOnion automatically logs to three places:

```python
# Default: console + plain text + session YAML
agent = Agent("assistant")

# Custom log file path
agent = Agent("assistant", log="agent.log")

# Or use environment variable (highest priority)
# CONNECTONION_LOG=agent.log python agent.py
```

Log locations:
- Plain text: `.co/logs/{name}.log`
- Session YAML: `.co/evals/{name}.yaml`

## Quiet Mode

For eval/testing, suppress console but keep session logging:

```python
# Quiet mode: no console, but sessions recorded for replay
agent = Agent("assistant", quiet=True)
```

| quiet | log | Console | Plain Text | Sessions | Use Case |
|-------|-----|---------|------------|----------|----------|
| False | True/None | ✓ | ✓ | ✓ | Development (default) |
| True | True/None | ✗ | ✗ | ✓ | Eval/testing |
| False | False | ✓ | ✗ | ✗ | Benchmarking |

## Why Console is On by Default

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
- Console is on by default (use `quiet=True` to suppress)
- Shows what's happening (like FastAPI, npm, cargo)
- `@xray` decorator adds enhanced Rich tables for specific tools
- Session YAML logging for eval and replay

**Rationale:** The console output isn't "debug" information - it's useful operation visibility that users expect. Hiding it by default created confusion and poor developer experience.