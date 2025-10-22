# Design Decision: Hook System for Agent Lifecycle Events

**Status:** RFC (Community Vote in Progress)
**Date:** 2025-10-22
**Decision Makers:** Core team + Community
**Related:** [Issue #31](https://github.com/openonion/connectonion/issues/31), [Discussion #33](https://github.com/openonion/connectonion/discussions/33)

---

## The Problem

Users needed a way to observe and modify agent behavior at key lifecycle points:

**Real Use Cases:**
- Track token usage and costs across LLM calls
- Cache expensive tool results to avoid re-execution
- Add timestamps or context to prompts before LLM sees them
- Custom logging and monitoring for production deployments
- Implement retry logic or rate limiting

**The Challenge:** How do we add this power without making the simple case complex?

---

## Our Design Journey

### Starting Point: "We Need Hooks"

The initial idea was simple: add a hook system like Flask or Express.js. But which API?

We explored **four fundamentally different approaches**, each with different trade-offs.

---

## The Options We Explored

### Option 1: Constructor Hooks (Dict Format)

**The Idea:** Pass hooks as a dictionary grouped by event type.

```python
agent = Agent(
    "assistant",
    tools=[search],
    hooks={
        'before_llm': [add_timestamp],
        'after_llm': [log_tokens, track_cost],
        'after_tool': [cache_results],
    }
)
```

**Why We Liked It:**
- ✅ All configuration in one place (declarative)
- ✅ Easy to see what hooks are active
- ✅ Reusable across agents (`common_hooks = {...}`)
- ✅ Perfect for "deploy once, runs everywhere" use case
- ✅ Familiar dict pattern - everyone knows `{key: [values]}`

**The Concern:**
- ❌ String keys can be misspelled (`'after_llm'` vs `'after-llm'`)
- ❌ No autocomplete for event names

---

### Option 2: Event Wrappers (List Format)

**The Idea:** Wrap functions to mark their timing, pass as a list.

```python
from connectonion import before_llm, after_llm, after_tool

agent = Agent(
    "assistant",
    tools=[search],
    hooks=[
        before_llm(add_timestamp),
        after_llm(log_tokens),
        after_tool(cache_results),
    ]
)
```

**Why We Liked It:**
- ✅ Autocomplete - IDE suggests `before_llm`, `after_llm`
- ✅ Can't misspell - it's a function import
- ✅ **Perfect for plugins:** "import and it works"
  ```python
  from connectonion.thinking import chain_of_thought
  hooks=[chain_of_thought()]  # Just works!
  ```

**The Struggle:** Should it be `on_event=[]` or `hooks=[]`?

Initially we thought `on_event` was more descriptive ("on event, do this"), but then we realized:

```python
# This reads weird:
on_event=[chain_of_thought()]  # "On event, chain of thought"??

# This reads naturally:
hooks=[chain_of_thought()]  # "These hooks: chain of thought" ✅
```

**Key Insight:** When passing noun-like things (plugins, features), `hooks` works better than `on_event`. Grammar matters!

---

### Option 3: Decorator Pattern

**The Idea:** Mark functions with `@hook('event_name')`, then pass to agent.

```python
from connectonion import hook

@hook('before_llm')
def add_timestamp(data):
    from datetime import datetime
    data['messages'].append({'role': 'system', 'content': f'{datetime.now()}'})
    return data

@hook('after_llm')
def log_tokens(data):
    print(f"Tokens: {data['usage']['total_tokens']}")

agent = Agent("assistant", tools=[search],
    hooks=[add_timestamp, log_tokens])
```

**Why We Liked It:**
- ✅ Familiar pattern (like `@xray`, `@replay`)
- ✅ Reusable across modules
- ✅ Self-documenting (decorator tells you when it runs)

**The Problem:**
- ❌ Two-step process: decorate + pass to agent
- ❌ Less obvious than Options 1 or 2

---

### Option 4: Event Emitter (Dynamic Methods)

**The Idea:** Add hooks after agent creation with `agent.on()`.

```python
agent = Agent("assistant", tools=[search])

# Simple lambda
agent.on('after_llm', lambda d: print(f"Tokens: {d['usage']}"))

# Decorator syntax
@agent.on('before_llm')
def add_timestamp(data):
    from datetime import datetime
    data['messages'].append({'role': 'system', 'content': f'{datetime.now()}'})
    return data
```

**Why We Liked It:**
- ✅ Familiar to JavaScript/Node.js developers
- ✅ Dynamic add/remove (`agent.off('after_llm', hook)`)
- ✅ Discoverable with autocomplete

**Why We Were Skeptical:**
- ❌ Hooks scattered throughout code (not declarative)
- ❌ Doesn't match "deploy once" philosophy
- ❌ Harder to track what hooks are active

---

## The Struggles

### Struggle #1: Too Many Parameters

Initial attempt at separate parameters per hook type:

```python
agent = Agent(
    "assistant",
    tools=[search],
    system_prompt="...",
    model="gpt-4",
    before_llm_calls=[...],      # Too many!
    after_llm_calls=[...],       # Too many!
    before_tool_calls=[...],     # Too many!
    after_tool_calls=[...],      # Too many!
    before_input_calls=[...],    # Too many!
    after_output_calls=[...],    # Too many!
    on_errors=[...],             # Too many!
)
# This is overwhelming! 😱
```

**Solution:** Group all hooks under a single parameter (`hooks`), let format (dict vs list) determine style.

---

### Struggle #2: Naming Ambiguity

**The Problem:**
```python
hooks={'after_tool': [my_func]}
```

Does this run after **each tool** or **all tools complete**?

**Solution:** Be explicit in documentation - "after_tool" means "after each tool execution".

We considered `after_each_tool` but decided the shorter name was clearer with good docs.

---

### Struggle #3: Discoverability vs Simplicity

**The Tension:**
- Option 1 (dict): Simple but no autocomplete
- Option 2 (wrappers): Autocomplete but requires imports
- Option 4 (methods): Discoverable but not declarative

**Our Conclusion:** Offer both Options 1 and 2, let users choose based on their needs.

---

## Key Insights

### Insight 1: Different Users, Different Needs

**Beginner users (80%):**
- Just want logging or token tracking
- Need simple, obvious API
- Don't want to learn "hooks" concept
- → **Option 1 (dict)** is perfect

**Power users (15%):**
- Building reusable plugins
- Want autocomplete and type safety
- Comfortable with imports
- → **Option 2 (wrappers)** is perfect

**Framework developers (5%):**
- Want dynamic control
- Need to add/remove hooks at runtime
- → **Option 4 (methods)** is perfect

### Insight 2: Deployment Patterns Matter

User quote: *"I want it deployed, each time will be same"*

This told us:
- Configuration should be declarative (visible upfront)
- Constructor-based (Options 1, 2) better than method-based (Option 4)
- Reusability is critical (`common_hooks` pattern)

### Insight 3: Grammar Reveals Intent

The `on_event` vs `hooks` debate taught us:
- Parameter names should work with **any** value, not just simple functions
- `hooks=[chain_of_thought()]` reads naturally
- `on_event=[chain_of_thought()]` reads awkwardly
- **Grammar matters for API design!**

### Insight 4: Format Auto-Detection is Powerful

Same parameter, different formats:

```python
# Agent detects format by type
hooks={'after_llm': [...]}  # Dict → Option 1
hooks=[after_llm(...)]      # List → Option 2
```

This gives us:
- Single parameter to learn (`hooks`)
- Multiple styles for different use cases
- No confusion (format is obvious from syntax)

---

## Our Recommendations

### Primary Recommendation: **Support Options 1 & 2**

**Option 1 for everyday use:**
```python
agent = Agent("assistant", tools=[search], hooks={
    'after_llm': [log_tokens],
    'after_tool': [cache_results],
})
```

**Option 2 for plugin ecosystem:**
```python
from connectonion.thinking import chain_of_thought

agent = Agent("assistant", tools=[search], hooks=[
    chain_of_thought()
])
```

**Why both?**
- Same parameter (`hooks`), different formats
- Serves different user needs
- Simple auto-detection by type
- Most flexible approach

### Secondary Options: Available but not primary

**Option 3 (decorators):** Useful for organizing code, but less intuitive than 1 & 2.

**Option 4 (methods):** Good for dynamic use cases, but doesn't fit "deploy once" pattern.

---

## What Hooks Receive

Each hook gets a `data` dictionary with relevant context:

### `before_llm(data)`
```python
{
    'messages': [...],      # Conversation history
    'tools': [...],         # Available tool schemas
    'iteration': 1,         # Current iteration
}
```

### `after_llm(data)`
```python
{
    'response': LLMResponse,
    'usage': {'total_tokens': 150, ...},
    'timing': 234.5,        # milliseconds
    'iteration': 1,
}
```

### `before_tool(data)`
```python
{
    'tool_name': 'search',
    'tool_args': {'query': '...'},
    'tool_id': 'call_abc123',
    'iteration': 1,
}
```

### `after_tool(data)`
```python
{
    'tool_name': 'search',
    'tool_args': {...},
    'result': '...',
    'status': 'success',    # success/error/not_found
    'timing': 123.4,
    'iteration': 1,
}
```

**For advanced use cases**, hooks can accept `(data, agent)` to get agent access:

```python
def advanced_hook(data, agent):
    # Can call agent.llm, access agent.current_session, etc.
    thinking = agent.llm.complete([...])
    agent.current_session['messages'].append({...})
```

---

## Implementation Principles

### Keep Simple Things Simple

```python
# No hooks needed for basic usage
agent = Agent("assistant", tools=[search])
agent.input("task")  # Just works!

# Add one hook when needed
agent = Agent("assistant", tools=[search], hooks={
    'after_llm': [lambda d: print(d['usage'])]
})
```

### Make Complicated Things Possible

```python
# Complex plugin with agent access
from connectonion.thinking import chain_of_thought
from connectonion.caching import smart_cache

agent = Agent("assistant", tools=[search], hooks=[
    chain_of_thought(depth=3),
    smart_cache(ttl=3600),
])
```

### No Breaking Changes

All existing code continues to work:
```python
# Still works without any hooks
agent = Agent("assistant", tools=[search])
```

### Minimal Performance Overhead

Hooks only add cost when used:
- Zero overhead if `hooks=None`
- Simple list iteration when active
- No complex event system needed

---

## Open Questions for Community

1. **Which options should we implement?**
   - Just Option 1? (simplest)
   - Options 1 & 2? (flexible)
   - All four? (maximum choice)

2. **Should hooks be able to modify data?**
   - Read-only (safer, simpler)
   - Read-write (more powerful)
   - Both, based on return value?

3. **What about async hooks?**
   - Not in MVP
   - Add later if needed
   - Support from day one?

4. **Error handling in hooks?**
   - Log warning, continue execution
   - Raise error, stop agent
   - Configurable per hook

---

## Community Feedback

We're gathering feedback through:
- **GitHub Issue #31:** Detailed RFC with technical discussion
- **GitHub Discussion #33:** Community vote with emoji reactions
- **Discord:** Casual discussion and use case sharing

**Vote here:** https://github.com/openonion/connectonion/discussions/33

---

## Lessons Learned

### 1. Start with User Problems, Not Solutions

We didn't start with "let's add hooks." We started with "users need to track costs, cache results, add logging."

### 2. Explore Widely, Then Narrow

We explored 4+ different approaches before converging on 2 primary ones. The exploration helped us understand trade-offs.

### 3. Real Use Cases Drive Design

The "chain of thought" plugin use case revealed the `on_event` vs `hooks` naming issue. Real examples expose hidden problems.

### 4. Grammar Tests

If a parameter name reads awkwardly with realistic values, it's the wrong name. "On event, chain of thought" failed the grammar test.

### 5. Community Input is Critical

We're not implementing until the community weighs in. Different users have different needs - we need to hear them all.

---

## Next Steps

1. ✅ Document all options with examples
2. ✅ Create community vote
3. ⏳ Gather feedback (1-2 weeks)
4. ⏳ Analyze votes and comments
5. ⏳ Make final decision
6. ⏳ Implement chosen approach(es)
7. ⏳ Write comprehensive documentation
8. ⏳ Build example plugins to validate design

---

## Conclusion

The hook system design is a balance between:
- **Simplicity** (for everyday use)
- **Power** (for advanced use cases)
- **Familiarity** (patterns users already know)
- **Extensibility** (plugin ecosystem)

We believe **Options 1 & 2** strike the best balance:
- Option 1 (dict) for simple, declarative configuration
- Option 2 (wrappers) for plugin ecosystem and autocomplete

But we're waiting for **your** input before making the final call.

**Join the discussion:** https://github.com/openonion/connectonion/discussions/33

---

*"Keep simple things simple, make complicated things possible."*
