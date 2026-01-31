# Design Decision: Event API Naming for Tool Lifecycle

**Status:** Decided (Updated 2025-12-07)
**Date:** 2025-12-03, Updated 2025-12-07
**Related:** [010-hook-system-design.md](./010-hook-system-design.md)

---

## TL;DR - Final Event Names

| Event | When It Fires | Use Case |
|-------|---------------|----------|
| `@after_user_input` | After user message added | Input preprocessing |
| `@before_llm` | Before LLM call | Context injection |
| `@after_llm` | After LLM response | Response logging |
| `@before_tools` | Once before tool batch | User approval, setup |
| `@before_each_tool` | Before each individual tool | Per-tool validation |
| `@after_each_tool` | After each individual tool | Per-tool logging |
| `@after_tools` | Once after tool batch | Reflection, message injection |
| `@on_error` | On tool error | Error handling |
| `@on_complete` | Task finished | Cleanup, metrics |

**Key insight:** Plural (`tools`) = batch, Singular + "each" (`each_tool`) = per-item.

---

## What is a "Tools Batch"?

When the LLM responds, it can request **multiple tools at once**:

```
User: "Compare Python and JavaScript popularity and save to a file"

LLM Response:
  tool_calls = [
    search("python popularity 2024"),
    search("javascript popularity 2024"),
    write_file("comparison.md", "...")
  ]
```

This group of 3 tools from **ONE LLM response** is called a **"tools batch"**.

### The Agent Loop Visualized

```
User Input: "Compare Python and JavaScript"
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                      ITERATION 1                             │
│                                                              │
│  LLM Call → "I'll search for both and save results"         │
│           → tool_calls: [search, search, write_file]        │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │               TOOLS BATCH                               │ │
│  │                                                         │ │
│  │  @before_tools  ← fires ONCE                           │ │
│  │       │                                                 │ │
│  │       ▼                                                 │ │
│  │  ┌──────────────────────────────────────┐              │ │
│  │  │  Tool 1: search("python...")         │              │ │
│  │  │    @before_each_tool                 │              │ │
│  │  │    execute                           │              │ │
│  │  │    @after_each_tool                  │              │ │
│  │  └──────────────────────────────────────┘              │ │
│  │       │                                                 │ │
│  │       ▼                                                 │ │
│  │  ┌──────────────────────────────────────┐              │ │
│  │  │  Tool 2: search("javascript...")     │              │ │
│  │  │    @before_each_tool                 │              │ │
│  │  │    execute                           │              │ │
│  │  │    @after_each_tool                  │              │ │
│  │  └──────────────────────────────────────┘              │ │
│  │       │                                                 │ │
│  │       ▼                                                 │ │
│  │  ┌──────────────────────────────────────┐              │ │
│  │  │  Tool 3: write_file(...)             │              │ │
│  │  │    @before_each_tool                 │              │ │
│  │  │    execute                           │              │ │
│  │  │    @after_each_tool                  │              │ │
│  │  └──────────────────────────────────────┘              │ │
│  │       │                                                 │ │
│  │       ▼                                                 │ │
│  │  @after_tools  ← fires ONCE (safe to add messages!)    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                      ITERATION 2                             │
│                                                              │
│  LLM Call → "Here's the comparison..." (no tools)           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
@on_complete
```

**Key Points:**
- One LLM response = one tools batch (0 or more tools)
- `@before_tools` / `@after_tools` fire once per batch
- `@before_each_tool` / `@after_each_tool` fire for each individual tool

---

## The Original Problem

Our event system had asymmetric naming that confused users:

```python
# Old API (confusing)
@before_tool     # Fires before EACH tool (per-tool)
@after_tool      # Fires after ALL tools complete (batch) - NOT symmetric!
```

Users expected `before_tool` and `after_tool` to behave symmetrically, but they didn't.

---

## Why This Naming Matters: Anthropic Claude

Anthropic's Claude API has a strict requirement: **tool results must immediately follow the assistant message containing tool_calls**.

```python
# VALID message sequence:
[
    {"role": "assistant", "tool_calls": [{"id": "1"}, {"id": "2"}]},
    {"role": "tool", "tool_call_id": "1", "content": "..."},
    {"role": "tool", "tool_call_id": "2", "content": "..."},
    {"role": "assistant", "content": "Reflection..."},  # Safe! After all tools
]

# INVALID - Claude API rejects this:
[
    {"role": "assistant", "tool_calls": [{"id": "1"}]},
    {"role": "assistant", "content": "Thinking..."},  # ERROR! Can't insert here
    {"role": "tool", "tool_call_id": "1", "content": "..."},
]
```

**Rule:** Only add messages in `@after_tools`, never in `@after_each_tool`.

---

## Naming Evolution

### Version 1: Confusing (Old)
```python
@before_tool   # Per-tool
@after_tool    # Batch (!)  ← Asymmetric!
```

### Version 2: Explicit "round" (2025-12-03)
```python
@before_each_tool   # Per-tool
@after_each_tool    # Per-tool
@before_tool_round  # Batch
@after_tool_round   # Batch
```

**Problem:** "round" is framework jargon. Users need to learn what a "tool round" means.

### Version 3: Natural plural (2025-12-07) ✓
```python
@before_each_tool   # Per-tool (singular + "each")
@after_each_tool    # Per-tool (singular + "each")
@before_tools       # Batch (plural)
@after_tools        # Batch (plural)
```

**Why this is best:**
1. **Natural language:** "before tools" vs "before tool round"
2. **No new concepts:** Plural = all, singular + "each" = individual
3. **Shorter:** 13 chars vs 17 chars
4. **Universal pattern:** Singular/plural is familiar to all programmers

---

## Usage Examples

### Batch: User Approval Before Execution

```python
from connectonion import Agent, before_tools

@before_tools
def require_approval(agent):
    """Ask for approval before executing any tools."""
    pending = agent.current_session.get('pending_tools', [])
    print(f"\nAbout to execute {len(pending)} tool(s)")
    if input("Proceed? [y/n]: ").lower() != 'y':
        raise Exception("User cancelled")

agent = Agent("careful", tools=[delete_file], on_events=[require_approval])
```

### Batch: Reflection After All Tools (ReAct Pattern)

```python
from connectonion import Agent, after_tools

@after_tools
def reflect(agent):
    """Add a reflection message after all tools complete."""
    # Safe to add messages here - all tool results are recorded
    agent.current_session['messages'].append({
        'role': 'assistant',
        'content': "Let me analyze these results..."
    })

agent = Agent("thinker", tools=[search], on_events=[reflect])
```

### Per-Tool: Logging Each Execution

```python
from connectonion import Agent, before_each_tool, after_each_tool

@before_each_tool
def log_start(agent):
    tool = agent.current_session['pending_tool']
    print(f"Starting: {tool['name']}")

@after_each_tool
def log_end(agent):
    trace = agent.current_session['trace'][-1]
    print(f"Completed: {trace['tool_name']} in {trace['timing']:.0f}ms")

agent = Agent("logged", tools=[search], on_events=[log_start, log_end])
```

---

## Migration Guide

If upgrading from version 2 (tool_round naming):

| Old Name | New Name |
|----------|----------|
| `@before_tool_round` | `@before_tools` |
| `@after_tool_round` | `@after_tools` |

```python
# Old code
from connectonion import before_tool_round, after_tool_round

@after_tool_round
def my_handler(agent): ...

# New code
from connectonion import before_tools, after_tools

@after_tools
def my_handler(agent): ...
```

---

## Summary

The naming pattern is now consistent and intuitive:

- **Plural = Batch:** `before_tools`, `after_tools` fire once per LLM response
- **"each" = Per-item:** `before_each_tool`, `after_each_tool` fire for each tool

No framework jargon to learn. Just natural English.

---

*"Make the common case clear, and the advanced case possible."*
