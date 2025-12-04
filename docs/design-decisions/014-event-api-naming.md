# Design Decision: Event API Naming for Tool Lifecycle

**Status:** Decided
**Date:** 2025-12-03
**Related:** [010-hook-system-design.md](./010-hook-system-design.md)

---

## The Problem

Our event system had asymmetric naming that confused users:

```python
# Old API (confusing)
@before_tool     # Fires before EACH tool (per-tool)
@after_tool      # Fires after ALL tools complete (batch) - NOT symmetric!
```

Users expected `before_tool` and `after_tool` to behave symmetrically, but they didn't:
- `before_tool` fired **once per tool**
- `after_tool` fired **once per batch** (after all tools in one LLM response)

This caused bugs and confusion when users wanted to add a message after tool execution - they'd use `@after_tool` expecting per-tool behavior.

---

## Real-World Problems That Drove This Decision

### Problem 1: Anthropic Claude Message Ordering

Anthropic's Claude API has a strict requirement: **tool results must immediately follow the assistant message containing tool_calls**. You cannot insert any message between them.

```python
# Valid message sequence for Claude:
[
    {"role": "assistant", "tool_calls": [{"id": "1", "name": "search"}]},
    {"role": "tool", "tool_call_id": "1", "content": "results..."},  # Must be next!
]

# INVALID - Claude API rejects this:
[
    {"role": "assistant", "tool_calls": [{"id": "1", "name": "search"}]},
    {"role": "assistant", "content": "Let me think..."},  # ERROR! Can't insert here
    {"role": "tool", "tool_call_id": "1", "content": "results..."},
]
```

**The Implication:** If you use `@after_each_tool` to inject a message, it breaks Claude compatibility because the message appears between `tool_calls` and `tool` results.

**Solution:** Use `@after_tool_round` to inject messages - it fires AFTER all tool results are recorded, so the message sequence is valid:

```python
[
    {"role": "assistant", "tool_calls": [{"id": "1"}, {"id": "2"}]},
    {"role": "tool", "tool_call_id": "1", "content": "..."},
    {"role": "tool", "tool_call_id": "2", "content": "..."},
    {"role": "assistant", "content": "Reflection..."},  # Safe! After all tools
]
```

### Problem 2: ReAct Pattern Message Injection

The ReAct (Reasoning + Acting) pattern requires the agent to "think" after observing tool results:

```
Thought: I need to search for Python docs
Action: search("python documentation")
Observation: [search results]
Thought: Now I should summarize these results  ← Need to inject this!
Action: summarize(...)
```

To implement ReAct, we need to inject an assistant message (the "Thought") after tool execution. But **when** exactly?

**Wrong approach (breaks with multiple tools):**
```python
@after_each_tool  # Fires after EACH tool
def inject_thought(agent):
    agent.current_session['messages'].append({
        'role': 'assistant',
        'content': 'Thinking...'
    })
# Result: Thought injected BETWEEN tool results - breaks Claude!
```

**Correct approach:**
```python
@after_tool_round  # Fires ONCE after ALL tools
def inject_thought(agent):
    agent.current_session['messages'].append({
        'role': 'assistant',
        'content': 'Thinking...'
    })
# Result: Thought injected AFTER all tool results - works everywhere!
```

### Problem 3: The Reflection Plugin Bug

Our built-in `reflect` plugin uses an LLM to generate a reflection after tool execution. Initially it used `@after_tool` (the old name), which was actually batch behavior - so it worked.

But the name suggested per-tool behavior, leading to:
1. Confusion when reading the code
2. Users copying the pattern incorrectly for their own plugins
3. Bugs when users assumed `@after_tool` meant "after each tool"

The rename to `@after_tool_round` makes the batch behavior explicit and prevents these misunderstandings.

### Problem 4: Provider Compatibility Matrix

Different LLM providers have different message ordering requirements:

| Provider | Can inject between tool_calls and results? |
|----------|-------------------------------------------|
| OpenAI | Yes (flexible) |
| Anthropic Claude | **No** (strict ordering) |
| Google Gemini | Yes (flexible) |
| Local models | Varies |

By using `@after_tool_round`, plugins work across ALL providers. Using `@after_each_tool` for message injection only works with OpenAI.

**Design Principle:** Events that modify messages should default to the most compatible timing (`after_tool_round`).

---

## The Agent Execution Lifecycle

Understanding the lifecycle is critical to understanding the naming:

```
User Input
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    LLM ITERATION                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  @before_llm                                     │    │
│  │       │                                          │    │
│  │       ▼                                          │    │
│  │  LLM Call → Response with tool_calls[]           │    │
│  │       │                                          │    │
│  │       ▼                                          │    │
│  │  @after_llm                                      │    │
│  └─────────────────────────────────────────────────┘    │
│                         │                                │
│                         ▼                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │              TOOL ROUND                          │    │
│  │                                                  │    │
│  │  @before_tool_round (fires ONCE)                 │    │
│  │       │                                          │    │
│  │       ▼                                          │    │
│  │  ┌─────────────────────────────────────┐        │    │
│  │  │  Tool 1                              │        │    │
│  │  │  @before_each_tool                   │        │    │
│  │  │  execute(search, {query: "python"})  │        │    │
│  │  │  @after_each_tool                    │        │    │
│  │  └─────────────────────────────────────┘        │    │
│  │       │                                          │    │
│  │       ▼                                          │    │
│  │  ┌─────────────────────────────────────┐        │    │
│  │  │  Tool 2                              │        │    │
│  │  │  @before_each_tool                   │        │    │
│  │  │  execute(read_file, {path: "..."})   │        │    │
│  │  │  @after_each_tool                    │        │    │
│  │  └─────────────────────────────────────┘        │    │
│  │       │                                          │    │
│  │       ▼                                          │    │
│  │  @after_tool_round (fires ONCE)                  │    │
│  │  ← Safe to add messages here                     │    │
│  └─────────────────────────────────────────────────┘    │
│                         │                                │
│                         ▼                                │
│              (loop back to LLM if more tools)            │
└─────────────────────────────────────────────────────────┘
    │
    ▼
@on_complete
```

**Key Insight:** One LLM response can contain multiple tool calls. We call this group a "tool round."

---

## The Naming Challenge

We needed names that clearly convey:
1. **Per-tool events** - fire for each individual tool
2. **Batch events** - fire once for the entire group of tools

### The Asymmetry Problem

```python
# These look symmetric but aren't:
@before_tool   # Per-tool
@after_tool    # Batch (!)
```

This violated the Principle of Least Surprise.

---

## Options We Explored

### Option 1: `after_tools` (Plural)

```python
@before_tool   # Per-tool
@after_tools   # Batch (plural = batch)
```

**Pros:**
- Simple change
- Plural suggests "all"

**Cons:**
- Too subtle - easy to miss the 's'
- Typo-prone
- `@after_tools` doesn't tell you it's per-round

---

### Option 2: `after_all_tools`

```python
@before_tool       # Per-tool
@after_all_tools   # Batch
```

**Pros:**
- Very explicit

**Cons:**
- Verbose (14 characters)
- Doesn't include domain context

---

### Option 3: `after_tool_batch`

```python
@before_tool_batch   # Batch (new!)
@after_tool_batch    # Batch
```

**Pros:**
- Clear batch semantics

**Cons:**
- "Batch" is technical jargon
- Not intuitive for users unfamiliar with batch processing
- Sounds like MapReduce, not agent execution

---

### Option 4: `after_tool_round` (CHOSEN)

```python
@before_tool_round   # Batch - fires ONCE before all tools
@after_tool_round    # Batch - fires ONCE after all tools
```

**Pros:**
- "Round" is everyday language (game rounds, poker rounds, boxing rounds)
- Includes domain noun ("tool round")
- Matches how users think: "after this round of tool calls"
- Framework precedent: SQLAlchemy's `after_flush`, Django's `request_finished`

**Why "round"?**
- Users naturally think in rounds: "The LLM made a round of tool calls"
- "Round" implies a bounded group of related actions
- Intuitive for both technical and non-technical users

---

## Framework Research

We studied how other frameworks name similar concepts:

| Framework | Event Name | Pattern |
|-----------|------------|---------|
| SQLAlchemy | `after_flush` | domain_noun |
| Django | `request_finished` | domain_noun |
| Unity | `FixedUpdate` | timing + action |
| Flask | `before_request` | timing + domain |
| Express.js | `afterEach` | timing + scope |

**Key Insight:** The best framework APIs include the **domain noun** in event names. "after_tool_round" includes "tool round" - the domain concept.

---

## Final Decision

### The API

```python
# Per-tool events (fire for EACH tool)
@before_each_tool   # Before each individual tool executes
@after_each_tool    # After each individual tool completes

# Batch events (fire ONCE per round)
@before_tool_round  # Before the first tool in the round
@after_tool_round   # After the last tool in the round completes
```

### Why No Aliases?

We considered keeping `before_tool` as an alias for `before_each_tool`:

```python
# Rejected: aliases create confusion
before_tool = before_each_tool  # Which one should I use?
after_tool = after_each_tool    # Cognitive overhead
```

**Decision:** No aliases. Explicit is better than implicit.

Users should use one name, documented clearly:
- `before_each_tool` / `after_each_tool` for per-tool
- `before_tool_round` / `after_tool_round` for batch

---

## Usage Examples

### Per-Tool: Logging Each Tool

```python
from connectonion import Agent, before_each_tool, after_each_tool

@before_each_tool
def log_start(agent):
    tool = agent.current_session['trace'][-1]
    print(f"Starting: {tool['tool_name']}")

@after_each_tool
def log_end(agent):
    tool = agent.current_session['trace'][-1]
    print(f"Completed: {tool['tool_name']} in {tool['duration_ms']}ms")

agent = Agent("logger", tools=[search, read_file], on_events=[log_start, log_end])
```

### Batch: Reflection After All Tools

```python
from connectonion import Agent, after_tool_round

@after_tool_round
def reflect(agent):
    """Add a reflection message after all tools complete."""
    messages = agent.current_session['messages']
    # Safe to add messages here - all tools are done
    messages.append({
        'role': 'assistant',
        'content': f"I've completed {len(agent.current_session['trace'])} tool calls."
    })

agent = Agent("reflector", tools=[search], on_events=[reflect])
```

### Batch: Approval Before Tool Round

```python
from connectonion import Agent, before_tool_round

@before_tool_round
def require_approval(agent):
    """Ask user approval before executing tools."""
    trace = agent.current_session.get('pending_tools', [])
    print(f"About to execute {len(trace)} tools. Continue? [y/n]")
    if input().lower() != 'y':
        raise Exception("User cancelled tool execution")

agent = Agent("careful", tools=[delete_file], on_events=[require_approval])
```

---

## Breaking Change Migration

Users with existing code need to update:

| Old Name | New Name | Behavior |
|----------|----------|----------|
| `@before_tool` | `@before_each_tool` | Per-tool (unchanged) |
| `@after_tool` | `@after_tool_round` | Batch (renamed!) |
| - | `@after_each_tool` | Per-tool (use this for symmetry) |
| - | `@before_tool_round` | Batch (new!) |

**Migration example:**
```python
# Old code
from connectonion import before_tool, after_tool

@before_tool
def my_hook(agent): ...

@after_tool
def my_batch_hook(agent): ...

# New code
from connectonion import before_each_tool, after_tool_round

@before_each_tool
def my_hook(agent): ...

@after_tool_round
def my_batch_hook(agent): ...
```

---

## Lessons Learned

### 1. Symmetry Matters

If `before_X` and `after_X` look symmetric, they should behave symmetrically. Breaking this expectation causes bugs.

### 2. Include the Domain Noun

`after_tool_round` is better than `after_round` because it includes "tool" - the domain concept. Users immediately know what kind of round.

### 3. Use Everyday Language

"Round" is intuitive. "Batch" is technical jargon. Choose words that non-experts understand.

### 4. Explicit Over Clever

We rejected aliases because they create cognitive overhead. One name, one behavior, clearly documented.

### 5. Study Other Frameworks

SQLAlchemy, Django, and Flask have solved similar problems. Their patterns (domain noun + timing) guided our design.

---

## Summary

| Event | When It Fires | Use Case |
|-------|---------------|----------|
| `@before_each_tool` | Before each tool | Logging, validation |
| `@after_each_tool` | After each tool | Result processing, caching |
| `@before_tool_round` | Once before all tools | Approval, setup |
| `@after_tool_round` | Once after all tools | Reflection, message injection |

The naming now clearly communicates scope:
- `each` = per-tool
- `round` = batch

---

*"Make the common case clear, and the advanced case possible."*
