# Design Decision: Console Output Always On (0.0.7)

*Date: 2025-01-06*
*Status: Implemented (Supersedes previous debug design)*
*Previous: 010-debug-and-logging-design.md (0.0.6)*

## The Problem: "Debug" Mode Isn't Debugging

After shipping ConnectOnion 0.0.6 with `debug=True/False`, we discovered a fundamental UX issue:

**The console output wasn't "debugging" - it was normal operation visibility.**

Users were confused:
- "Why is my agent silent by default?"
- "Do I need debug=True in production?"
- "Is debug mode slower or unsafe?"

The output wasn't debug information - it was what users **expected to see**.

## The Insight: Learn from FastAPI, npm, cargo

Look at successful developer tools:

```bash
# FastAPI
$ fastapi dev
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete

# npm
$ npm install react
added 42 packages in 3s

# cargo
$ cargo build
   Compiling my-project v0.1.0
    Finished dev [unoptimized] in 2.34s
```

They ALL show output by default. Why should agents be silent?

## The Design Change: Console Always On

### Before (0.0.6):
```python
# Silent by default
agent = Agent("assistant")

# Need debug=True to see anything
agent = Agent("assistant", debug=True)
```

### After (0.0.7+):
```python
# Console output always visible
agent = Agent("assistant")

# That's it. No configuration needed.
```

## The New Architecture

### Console (Not DebugConsole)

```python
class Console:
    """Console for agent output and optional file logging.

    Always shows output to help users understand what's happening.
    Similar to FastAPI, npm, cargo - always visible by default.
    """

    def __init__(self, log_file: Optional[Path] = None):
        # Console always outputs to terminal
        # Optional file logging
```

Key changes:
1. Renamed `DebugConsole` → `Console` (it's not debug, it's the console)
2. Removed `enabled` flag (always on)
3. Removed `debug` parameter from Agent

### Two Output Methods

```python
# Basic console output (always visible)
console.print("[green]→[/green] Tool: search(query='python')")

# Enhanced @xray output (opt-in)
console.print_xray_table(
    tool_name="search",
    tool_args={"query": "python"},
    result="Found 10 results",
    timing=340.2,
    agent=agent
)
```

## Progressive Enhancement

Users get **visibility by default**, with opt-in details:

### Level 1: Basic (Always On)
```
14:32:14 → Tool: search({'query': 'python'})
14:32:14 ← Result (340ms): Found 10 results
```

### Level 2: Enhanced (@xray decorator)
```python
@xray
def search(query: str) -> str:
    return find_results(query)
```

Adds Rich table with detailed context:
```
╭──────────────────── @xray: search ────────────────────╮
│  agent       assistant                                │
│  task        Find Python documentation                │
│  iteration   1                                        │
│  ─────────────────────────────────────────────────    │
│  query       python                                   │
│  result      Found 10 results                         │
│  timing      340.2ms                                  │
╰───────────────────────────────────────────────────────╯
```

## What We Removed

1. **`debug` parameter** - Console output isn't debugging
2. **`DebugConsole` class** - Just "Console" now
3. **`enabled` flag** - Console is always on
4. **Confusion** - Users now see what's happening

## What We Kept

```python
# Optional file logging still works
agent = Agent("assistant", log="agent.log")

# Environment variable override
# CONNECTONION_LOG=agent.log python agent.py
```

## Implementation Philosophy: Always Collect, Always Display

### Before (0.0.6):
```python
if self.console.enabled:  # Conditional display
    console.print(f"Tool: {tool_name}")
```

### After (0.0.7):
```python
if console:  # If console exists (always true for Agent)
    console.print(f"Tool: {tool_name}")
```

The console is part of the agent's core functionality, not an optional debug feature.

## Breaking Changes (0.0.6 → 0.0.7)

### Removed:
- `debug` parameter from `Agent.__init__()`
- `DebugConsole` class (renamed to `Console`)
- `console.enabled` property

### Migration Guide:

```python
# 0.0.6 (OLD)
agent = Agent("assistant", debug=True)
agent = Agent("assistant", debug=False)

# 0.0.7 (NEW)
agent = Agent("assistant")  # Console always on
# If you really want silence, redirect stderr:
# python agent.py 2>/dev/null
```

## The Trade-offs

### We Chose: Visibility Over Silence

**Pro:**
- Better developer experience (see what's happening)
- Matches user expectations (like FastAPI, npm, cargo)
- Removes confusion about "debug" vs "production"
- Makes debugging easier (output already visible)

**Con:**
- Cannot disable console output via parameter
- Always writes to stderr (by design)

**If you need silence:**
```bash
# Redirect stderr
python agent.py 2>/dev/null

# Or capture programmatically
import sys
from io import StringIO
sys.stderr = StringIO()  # Capture console output
```

But honestly, if you need silence, ask yourself: **Why?**

The output is useful. Embrace it.

## Lessons Learned

1. **"Debug" was the wrong abstraction** - Output visibility isn't debugging
2. **Users want to see what's happening** - Silence creates confusion
3. **Learn from successful tools** - FastAPI, npm, cargo all show output
4. **Progressive enhancement works** - Basic output always, @xray for details
5. **Naming matters** - "Console" is clearer than "DebugConsole"

## Future Possibilities

This design enables:
- Different output formats (JSON mode for CI/CD)
- Log levels per tool (keep console simple, enrich logs)
- Remote logging without changing interface
- Custom output renderers (TUI, web UI, etc.)

But we'll only add these if genuinely needed. For now, simplicity wins.

## The Core Principle

**Console output isn't a feature to toggle - it's part of good UX.**

Just like FastAPI shows server logs, npm shows install progress, and cargo shows build status - ConnectOnion shows agent operation.

It's not debugging. It's just being helpful.

## Conclusion

By removing the `debug` parameter and making console output always visible, we:
- Eliminated confusion about "debug mode"
- Improved developer experience
- Aligned with successful tool design patterns
- Made the framework more helpful by default

**The principle remains: Keep simple things simple, make complicated things possible.**

Console output is simple. @xray enhancement is possible.

---

*"The best interface is no interface - but the second best is the one that shows you what's happening."*

*We chose visibility over silence.*