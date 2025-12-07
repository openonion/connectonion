# Design Decision: Agent Lifecycle Design

**Status:** Implemented
**Date:** 2025-12-03
**Related:** [009-tool-execution-separation.md](./009-tool-execution-separation.md), [014-event-api-naming.md](./014-event-api-naming.md)

---

## Overview

This document describes the complete lifecycle of an Agent from initialization through task completion. Understanding this lifecycle is essential for:
- Implementing event handlers correctly
- Debugging agent behavior
- Building plugins that work reliably

---

## The Complete Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT INITIALIZATION                         │
│  Agent(name, tools, system_prompt, model, trust, ...)           │
│                                                                  │
│  1. Load system prompt (from string, file, or prompts/ folder)  │
│  2. Create Logger (terminal + .co/logs/ + .co/sessions/)        │
│  3. Create trust agent (if trust parameter provided)            │
│  4. Initialize event registry                                    │
│  5. Register plugins and on_events handlers                      │
│  6. Process tools → ToolRegistry                                 │
│  7. Create LLM via factory (based on model prefix)              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        agent.input(prompt)                       │
│                                                                  │
│  Entry point for task execution. Can be called multiple times   │
│  for multi-turn conversations.                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SESSION MANAGEMENT                           │
│                                                                  │
│  First call:                                                     │
│    - Create current_session with messages, trace, turn=0        │
│    - Add system prompt as first message                          │
│    - Start YAML session logging                                  │
│                                                                  │
│  Subsequent calls:                                               │
│    - Reuse existing session (multi-turn conversation)            │
│    - Preserve message history                                    │
│                                                                  │
│  Always:                                                         │
│    - Add user message to conversation                            │
│    - Increment turn counter                                      │
│    - Add user_input trace entry                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                  ┌───────────────────────┐
                  │  @after_user_input    │
                  │                       │
                  │  Use cases:           │
                  │  - Input validation   │
                  │  - Preprocessing      │
                  │  - Logging            │
                  └───────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ITERATION LOOP                              │
│              (max_iterations times, default=10)                  │
│                                                                  │
│  Each iteration:                                                 │
│    1. Increment iteration counter                                │
│    2. Get LLM decision                                           │
│    3. If no tool_calls → return response (exit loop)            │
│    4. Execute tools and record results                           │
│    5. Continue to next iteration                                 │
│                                                                  │
│  Exit conditions:                                                │
│    - LLM returns content without tool_calls → return content    │
│    - Max iterations reached → return "Task incomplete" message  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │
              ┌───────────────┴───────────────┐
              │       LLM CALL PHASE          │
              │                               │
              │  ┌─────────────────────────┐  │
              │  │     @before_llm         │  │
              │  │                         │  │
              │  │  Use cases:             │  │
              │  │  - Modify messages      │  │
              │  │  - Add context          │  │
              │  │  - Rate limiting        │  │
              │  └─────────────────────────┘  │
              │              │                │
              │              ▼                │
              │  ┌─────────────────────────┐  │
              │  │      LLM.complete()     │  │
              │  │                         │  │
              │  │  - Send messages        │  │
              │  │  - Include tool schemas │  │
              │  │  - Receive response     │  │
              │  │  - Track token usage    │  │
              │  └─────────────────────────┘  │
              │              │                │
              │              ▼                │
              │  ┌─────────────────────────┐  │
              │  │  Add llm_call to trace  │  │
              │  │                         │  │
              │  │  Records:               │  │
              │  │  - model, timestamp     │  │
              │  │  - duration_ms          │  │
              │  │  - tool_calls_count     │  │
              │  │  - usage (tokens/cost)  │  │
              │  └─────────────────────────┘  │
              │              │                │
              │              ▼                │
              │  ┌─────────────────────────┐  │
              │  │      @after_llm         │  │
              │  │                         │  │
              │  │  Use cases:             │  │
              │  │  - Log LLM response     │  │
              │  │  - Modify tool_calls    │  │
              │  │  - Analytics            │  │
              │  └─────────────────────────┘  │
              │              │                │
              └──────────────┬────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌─────────────────┐          ┌────────────────────┐
    │  No tool_calls  │          │  Has tool_calls    │
    │                 │          │                    │
    │  Return content │          │  Execute tools     │
    │  → @on_complete │          │                    │
    └─────────────────┘          └────────────────────┘
                                           │
                                           ▼
              ┌────────────────────────────────────────────────┐
              │                 TOOL ROUND                      │
              │                                                 │
              │  One LLM response can contain multiple tools.   │
              │  We call this group a "tool round."             │
              │                                                 │
              │  ┌─────────────────────────────────────────┐   │
              │  │  Add assistant message with tool_calls  │   │
              │  │  to conversation messages               │   │
              │  └─────────────────────────────────────────┘   │
              │                      │                          │
              │                      ▼                          │
              │  ┌─────────────────────────────────────────┐   │
              │  │         @before_tools              │   │
              │  │         (fires ONCE)                    │   │
              │  │                                         │   │
              │  │  Use cases:                             │   │
              │  │  - User approval before execution       │   │
              │  │  - Batch setup/preparation              │   │
              │  │  - Resource allocation                  │   │
              │  └─────────────────────────────────────────┘   │
              │                      │                          │
              │                      ▼                          │
              │  ┌─────────────────────────────────────────┐   │
              │  │          FOR EACH TOOL                  │   │
              │  │                                         │   │
              │  │  ┌───────────────────────────────────┐ │   │
              │  │  │      @before_each_tool            │ │   │
              │  │  │                                   │ │   │
              │  │  │  pending_tool available:          │ │   │
              │  │  │  - name, arguments, id            │ │   │
              │  │  │                                   │ │   │
              │  │  │  Use cases:                       │ │   │
              │  │  │  - Per-tool logging               │ │   │
              │  │  │  - Argument validation            │ │   │
              │  │  │  - Per-tool approval              │ │   │
              │  │  └───────────────────────────────────┘ │   │
              │  │                  │                      │   │
              │  │                  ▼                      │   │
              │  │  ┌───────────────────────────────────┐ │   │
              │  │  │      TOOL EXECUTION              │ │   │
              │  │  │                                   │ │   │
              │  │  │  1. Inject xray context           │ │   │
              │  │  │  2. Start timing                  │ │   │
              │  │  │  3. Execute tool_func(**args)     │ │   │
              │  │  │  4. Record duration               │ │   │
              │  │  │  5. Create trace entry            │ │   │
              │  │  │  6. Clear xray context            │ │   │
              │  │  └───────────────────────────────────┘ │   │
              │  │                  │                      │   │
              │  │                  ▼                      │   │
              │  │  ┌───────────────────────────────────┐ │   │
              │  │  │  Add tool result message          │ │   │
              │  │  │  {"role": "tool", ...}            │ │   │
              │  │  └───────────────────────────────────┘ │   │
              │  │                  │                      │   │
              │  │                  ▼                      │   │
              │  │  ┌───────────────────────────────────┐ │   │
              │  │  │  (if error) @on_error             │ │   │
              │  │  └───────────────────────────────────┘ │   │
              │  │                  │                      │   │
              │  │                  ▼                      │   │
              │  │  ┌───────────────────────────────────┐ │   │
              │  │  │      @after_each_tool             │ │   │
              │  │  │                                   │ │   │
              │  │  │  WARNING: Do NOT add messages     │ │   │
              │  │  │  here - breaks Anthropic API!     │ │   │
              │  │  │                                   │ │   │
              │  │  │  Use cases:                       │ │   │
              │  │  │  - Per-tool logging               │ │   │
              │  │  │  - Metrics collection             │ │   │
              │  │  │  - Result caching                 │ │   │
              │  │  └───────────────────────────────────┘ │   │
              │  │                  │                      │   │
              │  │         (repeat for next tool)          │   │
              │  └─────────────────────────────────────────┘   │
              │                      │                          │
              │                      ▼                          │
              │  ┌─────────────────────────────────────────┐   │
              │  │         @after_tools               │   │
              │  │         (fires ONCE)                    │   │
              │  │                                         │   │
              │  │  SAFE to add messages here!             │   │
              │  │  All tool results are recorded.         │   │
              │  │                                         │   │
              │  │  Use cases:                             │   │
              │  │  - Reflection/reasoning injection       │   │
              │  │  - ReAct pattern implementation         │   │
              │  │  - Batch cleanup                        │   │
              │  └─────────────────────────────────────────┘   │
              │                      │                          │
              └──────────────────────┼──────────────────────────┘
                                     │
                                     ▼
                        (back to ITERATION LOOP)
                                     │
                                     ▼
              ┌─────────────────────────────────────────────────┐
              │                  COMPLETION                      │
              │                                                  │
              │  When LLM returns without tool_calls:            │
              │    1. Calculate turn duration                    │
              │    2. Aggregate turn data for YAML session       │
              │    3. Log turn to .co/sessions/                  │
              │    4. Fire @on_complete event                    │
              │    5. Return final response string               │
              └─────────────────────────────────────────────────┘
                                     │
                                     ▼
                        ┌───────────────────────┐
                        │     @on_complete      │
                        │                       │
                        │  Use cases:           │
                        │  - Final logging      │
                        │  - Cleanup            │
                        │  - Notifications      │
                        │  - Analytics          │
                        └───────────────────────┘
```

---

## Key Concepts

### 1. Session Persistence

The `current_session` object persists across multiple `input()` calls, enabling multi-turn conversations:

```python
agent = Agent("assistant")

# Turn 1
agent.input("What is 2+2?")
# Session created: turn=1, messages=[system, user1, assistant1]

# Turn 2 - conversation continues
agent.input("And what is that times 3?")
# Session reused: turn=2, messages=[..., user2, assistant2]

# Reset for fresh conversation
agent.reset_conversation()
```

**Session Structure:**
```python
current_session = {
    'messages': [           # OpenAI-format conversation
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "...", "tool_calls": [...]},
        {"role": "tool", "tool_call_id": "...", "content": "..."},
    ],
    'trace': [              # Execution history for debugging
        {"type": "user_input", "turn": 1, "prompt": "..."},
        {"type": "llm_call", "model": "...", "duration_ms": 123},
        {"type": "tool_execution", "tool_name": "...", "timing": 45.2},
    ],
    'turn': 1,              # Conversation turn counter
    'iteration': 3,         # Current iteration within turn
    'user_prompt': "...",   # Current user prompt (for xray)
    'pending_tool': {...},  # Available during before_each_tool only
}
```

### 2. The Iteration Loop

Each `input()` call runs an iteration loop:

```
Turn 1 (input("task"))
├── Iteration 1: LLM → tool_calls[search] → execute
├── Iteration 2: LLM → tool_calls[read_file] → execute
├── Iteration 3: LLM → content (no tools) → return
└── Total: 3 iterations

Turn 2 (input("followup"))
├── Iteration 1: LLM → content (no tools) → return
└── Total: 1 iteration
```

**Why Iterations?**
The LLM decides what to do next. After executing tools, it may need more tools, or it may have enough information to respond.

### 3. Tool Rounds vs Individual Tools

A single LLM response can request multiple tools. We call this a "tool round":

```
Iteration 1:
  LLM Response: tool_calls = [search("python"), read_file("docs.md"), calculate(2+2)]

  Tool Round:
    @before_tools (once)
    ├── Tool 1: search("python")
    │   ├── @before_each_tool
    │   ├── execute
    │   └── @after_each_tool
    ├── Tool 2: read_file("docs.md")
    │   ├── @before_each_tool
    │   ├── execute
    │   └── @after_each_tool
    └── Tool 3: calculate(2+2)
        ├── @before_each_tool
        ├── execute
        └── @after_each_tool
    @after_tools (once)
```

### 4. XRay Context Injection

During tool execution, the `xray` global provides execution context:

```python
from connectonion import xray

@xray  # Decorator enables context access
def my_tool(query: str):
    # Access runtime context
    print(f"Agent: {xray.agent.name}")
    print(f"Task: {xray.task}")  # User's original prompt
    print(f"Iteration: {xray.iteration}")
    print(f"Previous tools: {xray.previous_tools}")

    # View execution history
    xray.trace()  # Prints Rich-formatted trace

    return "result"
```

The context lifecycle:
1. `inject_xray_context()` before tool execution
2. Tool runs with access to `xray.*`
3. `clear_xray_context()` after tool completes

### 5. Message Ordering Constraint

**Critical:** Anthropic Claude requires tool results immediately after assistant tool_calls:

```python
# VALID sequence:
[
    {"role": "assistant", "tool_calls": [{"id": "1"}, {"id": "2"}]},
    {"role": "tool", "tool_call_id": "1", "content": "..."},
    {"role": "tool", "tool_call_id": "2", "content": "..."},
    {"role": "assistant", "content": "Reflection..."},  # After ALL tools
]

# INVALID - breaks Claude API:
[
    {"role": "assistant", "tool_calls": [{"id": "1"}]},
    {"role": "assistant", "content": "Thinking..."},  # Can't insert here!
    {"role": "tool", "tool_call_id": "1", "content": "..."},
]
```

**Rule:** Only inject messages in `@after_tools`, never in `@after_each_tool`.

---

## Event Summary

| Event | When | Frequency | Safe to Add Messages? |
|-------|------|-----------|----------------------|
| `@after_user_input` | After user prompt added | Once per input() | Yes |
| `@before_llm` | Before LLM call | Each iteration | Yes |
| `@after_llm` | After LLM response | Each iteration | Yes |
| `@before_tools` | Before first tool in round | Once per round | Yes |
| `@before_each_tool` | Before each tool | Per tool | No* |
| `@after_each_tool` | After each tool | Per tool | No |
| `@after_tools` | After all tools in round | Once per round | Yes |
| `@on_error` | When tool fails | Per error | No |
| `@on_complete` | Task finished | Once per input() | Yes |

\* `pending_tool` is available in `@before_each_tool` for inspection/validation.

---

## Common Patterns

### Pattern 1: Reflection Plugin

Add reasoning after each tool round (ReAct pattern):

```python
from connectonion import Agent, after_tools, llm_do

@after_tools
def reflect(agent):
    """Generate reflection after tool execution."""
    trace = agent.current_session['trace']
    last_tools = [t for t in trace if t['type'] == 'tool_execution'][-3:]

    reflection = llm_do(
        f"What did we learn from: {last_tools}? One sentence.",
        model="co/gemini-2.5-flash"
    )

    agent.current_session['messages'].append({
        'role': 'assistant',
        'content': f"Observation: {reflection}"
    })

agent = Agent("researcher", tools=[search], on_events=[reflect])
```

### Pattern 2: Human-in-the-Loop Approval

Require approval before executing tools:

```python
from connectonion import Agent, before_tools

@before_tools
def require_approval(agent):
    """Ask for approval before tool execution."""
    pending = agent.current_session.get('pending_tools', [])
    print(f"\nAbout to execute {len(pending)} tool(s):")
    for t in pending:
        print(f"  - {t['name']}({t['arguments']})")

    response = input("Proceed? [y/n]: ")
    if response.lower() != 'y':
        raise Exception("User rejected tool execution")

agent = Agent("careful", tools=[delete_file], on_events=[require_approval])
```

### Pattern 3: Tool Execution Logging

Log every tool execution for debugging:

```python
from connectonion import Agent, before_each_tool, after_each_tool
import logging

logger = logging.getLogger('tools')

@before_each_tool
def log_start(agent):
    tool = agent.current_session['pending_tool']
    logger.info(f"START: {tool['name']}({tool['arguments']})")

@after_each_tool
def log_end(agent):
    trace = agent.current_session['trace'][-1]
    logger.info(f"END: {trace['tool_name']} ({trace['timing']:.1f}ms) -> {trace['status']}")

agent = Agent("logged", tools=[search], on_events=[log_start, log_end])
```

### Pattern 4: Context Window Management

Monitor and handle context limits:

```python
from connectonion import Agent, before_llm

@before_llm
def check_context(agent):
    """Warn if context is getting full."""
    if agent.context_percent > 80:
        print(f"WARNING: Context {agent.context_percent:.1f}% full")
        # Could summarize old messages here

agent = Agent("context-aware", on_events=[check_context])
```

---

## Trace Entry Types

The trace records all execution events:

```python
# User input
{"type": "user_input", "turn": 1, "prompt": "...", "timestamp": 1701619200}

# LLM call
{
    "type": "llm_call",
    "model": "co/o4-mini",
    "timestamp": 1701619201,
    "duration_ms": 1234.5,
    "tool_calls_count": 2,
    "iteration": 1,
    "usage": TokenUsage(input_tokens=150, output_tokens=50, cost=0.002)
}

# Tool execution
{
    "type": "tool_execution",
    "tool_name": "search",
    "arguments": {"query": "python docs"},
    "call_id": "call_abc123",
    "result": "Found 5 results...",
    "status": "success",  # or "error", "not_found"
    "timing": 45.2,
    "iteration": 1,
    "timestamp": 1701619202
}

# Error case
{
    "type": "tool_execution",
    "tool_name": "failing_tool",
    "status": "error",
    "error": "Connection timeout",
    "error_type": "TimeoutError",
    ...
}
```

---

## Logging Architecture

The lifecycle integrates with the logging system:

```
Agent(name="my_agent")
     │
     ├─── Console (Rich terminal output)
     │    └── Only if quiet=False (default)
     │
     ├─── Plain Text Log
     │    └── .co/logs/my_agent.log (always, unless log=False)
     │
     └─── YAML Session Log
          └── .co/sessions/my_agent_2025-12-03T10-30-00.yaml

YAML Session Structure:
─────────────────────────
agent: my_agent
model: co/o4-mini
started: 2025-12-03T10:30:00Z
turns:
  - input: "Find Python tutorials"
    model: co/o4-mini
    duration_ms: 5234
    tokens: 450
    cost: 0.0045
    tools_called: [search, read_file]
    result: "Here are the top tutorials..."
    messages: "[{...}, {...}]"
```

---

## Design Principles

### 1. Single Source of Truth

`current_session` is the only mutable state during execution. All components read/write to it:
- Messages accumulate in `current_session['messages']`
- Trace entries append to `current_session['trace']`
- Events access context via `agent.current_session`

### 2. Events Over Subclassing

Rather than subclassing Agent, use events:

```python
# Good: Use events
@after_tools
def my_logic(agent): ...

agent = Agent("name", on_events=[my_logic])

# Avoid: Subclassing
class MyAgent(Agent):
    def _execute_and_record_tools(self, ...):
        super()._execute_and_record_tools(...)
        # my logic
```

### 3. Fail Fast

Events propagate exceptions. No silent swallowing:

```python
@before_llm
def validate(agent):
    if not agent.current_session['messages']:
        raise ValueError("No messages!")  # Propagates to caller
```

### 4. Always Collect, Conditionally Display

The trace always records everything. Display is controlled by `quiet` parameter:

```python
# Always recorded in trace and session
agent = Agent("name", quiet=True)  # No console output
agent = Agent("name", quiet=False) # Console output (default)
```

---

## Summary

The Agent lifecycle follows a clear pattern:
1. **Initialize** - Load config, create LLM, process tools
2. **Input** - Create/continue session, add user message
3. **Iterate** - LLM call → tool execution → repeat until done
4. **Complete** - Log session, fire on_complete, return result

Events provide hooks at every stage without requiring subclassing. The `current_session` object is the single source of truth, and the trace provides complete execution history for debugging and analytics.

---

*"The best architectures are those where you can predict what happens next."*
