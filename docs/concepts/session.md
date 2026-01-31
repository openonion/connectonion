# Session

> The runtime state of your agent. Access it via `agent.current_session` to inspect messages, trace execution, and build plugins.

---

## Quick Start (60 Seconds)

```python
from connectonion import Agent, after_each_tool

def log_tool_result(agent):
    """Access session data in your event handler."""
    trace = agent.current_session['trace'][-1]
    print(f"Tool: {trace['name']} -> {trace['status']}")

agent = Agent("bot", tools=[search], on_events=[after_each_tool(log_tool_result)])
agent.input("Search for Python")
```

**That's it.** `current_session` gives you everything about the current execution.

---

## What's in a Session?

When you call `agent.input()`, a session is created (or continued):

```python
agent.current_session = {
    'messages': [...],       # OpenAI-format conversation history
    'trace': [...],          # Execution log (what happened)
    'user_prompt': '...',    # Current turn's input
    'iteration': 1,          # Current loop iteration (1 to max_iterations)
    'turn': 1,               # Conversation turn number
}
```

| Field | Type | Description |
|-------|------|-------------|
| `messages` | `list[dict]` | Full conversation in OpenAI format |
| `trace` | `list[dict]` | Sequential log of all execution events |
| `user_prompt` | `str` | The current user input |
| `iteration` | `int` | Current iteration within this turn (1-10 by default) |
| `turn` | `int` | Which conversation turn (increments on each `input()`) |

---

## Messages

The `messages` list follows [OpenAI's message format](https://platform.openai.com/docs/api-reference/chat/create):

```python
agent.current_session['messages'] = [
    {'role': 'system', 'content': 'You are a helpful assistant...'},
    {'role': 'user', 'content': 'Search for Python tutorials'},
    {'role': 'assistant', 'content': None, 'tool_calls': [...]},
    {'role': 'tool', 'content': 'Found 10 results...', 'tool_call_id': 'call_abc'},
    {'role': 'assistant', 'content': 'I found some Python tutorials...'},
]
```

**Message roles:**
- `system` - Agent's personality/instructions
- `user` - User input
- `assistant` - LLM responses (may include `tool_calls`)
- `tool` - Tool execution results (includes `tool_call_id`)

### Modify Messages in Events

You can inject messages in your event handlers:

```python
from connectonion import Agent, after_tools

def add_context(agent):
    """Add context after tools complete."""
    agent.current_session['messages'].append({
        'role': 'system',
        'content': f'Current time: {datetime.now()}'
    })

agent = Agent("bot", tools=[search], on_events=[after_tools(add_context)])
```

> **Important:** Only modify messages in `after_tools` events. Other events may cause issues with some LLM providers (e.g., Anthropic requires tool results immediately after tool_calls).

---

## Trace

The `trace` is a sequential log of everything that happened during execution. This is your primary tool for understanding agent behavior.

### Trace Entry Types

| Type | When Created | Key Fields |
|------|--------------|------------|
| `user_input` | User provides input | `content`, `turn` |
| `thinking` | Agent plans or reflects | `content`, `kind` |
| `llm_call` | LLM API call completes | `model`, `duration_ms`, `usage` |
| `tool_result` | Tool execution completes | `name`, `args`, `result`, `status` |
| `assistant` | Final response ready | `content` |
| `error` | System/LLM error occurs | `error`, `error_type` |

### Common Fields

Every trace entry has:

```python
{
    'id': 1,              # Sequential ID (1, 2, 3...)
    'type': 'tool_result', # Entry type
    'ts': 1234567890.123,  # Unix timestamp
}
```

### user_input

Created when user calls `agent.input()`:

```python
{
    'id': 1,
    'type': 'user_input',
    'content': 'Search for Python tutorials',
    'turn': 1,
    'ts': 1234567890.123,
}
```

### thinking

Created by planning/reflection plugins (ReAct, Reflect):

```python
{
    'id': 2,
    'type': 'thinking',
    'content': 'I should search for tutorials first, then summarize...',
    'kind': 'plan',      # 'plan' or 'reflection'
    'ts': 1234567890.456,
}
```

### llm_call

Created after each LLM API call:

```python
{
    'id': 3,
    'type': 'llm_call',
    'model': 'gpt-4o-mini',
    'duration_ms': 234.5,
    'tool_calls_count': 2,
    'iteration': 1,
    'usage': TokenUsage(...),  # Token usage object
    'timestamp': 1234567890.789,
}
```

### tool_result

Created after each tool execution:

```python
{
    'id': 4,
    'type': 'tool_result',
    'name': 'search',
    'args': {'query': 'Python tutorials'},
    'result': 'Found 10 results for Python tutorials...',
    'status': 'success',   # 'success', 'error', or 'not_found'
    'timing_ms': 45.2,
    'tool_id': 'call_abc123',  # LLM's tool call ID for matching
    'ts': 1234567891.234,
}

# On error:
{
    'id': 5,
    'type': 'tool_result',
    'name': 'database',
    'args': {'query': 'SELECT *'},
    'result': 'Connection refused',
    'status': 'error',
    'error': 'Connection refused',
    'error_type': 'ConnectionError',
    'timing_ms': 1023.4,
    'tool_id': 'call_def456',  # LLM's tool call ID for matching
    'ts': 1234567892.567,
}
```

### assistant

Created when LLM provides final response (no more tool calls):

```python
{
    'id': 6,
    'type': 'assistant',
    'content': 'I found several Python tutorials. Here are the top results...',
    'ts': 1234567893.890,
}
```

### error

Created on system/LLM errors:

```python
{
    'id': 7,
    'type': 'error',
    'error': 'Rate limit exceeded',
    'error_type': 'RateLimitError',
    'ts': 1234567894.123,
}
```

---

## Reading Trace in Events

Access the latest trace entry:

```python
def my_event(agent):
    last = agent.current_session['trace'][-1]
    
    if last['type'] == 'tool_result':
        print(f"Tool {last['name']} returned: {last['status']}")
```

Filter trace by type:

```python
def count_tools(agent):
    trace = agent.current_session['trace']
    tool_calls = [t for t in trace if t['type'] == 'tool_result']
    print(f"Tools used so far: {len(tool_calls)}")
```

Aggregate statistics:

```python
def session_stats(agent):
    trace = agent.current_session['trace']
    
    llm_calls = [t for t in trace if t['type'] == 'llm_call']
    tool_calls = [t for t in trace if t['type'] == 'tool_result']
    errors = [t for t in trace if t.get('status') == 'error']
    
    total_llm_time = sum(t['duration_ms'] for t in llm_calls)
    total_tool_time = sum(t.get('timing_ms', 0) for t in tool_calls)
    
    print(f"LLM: {len(llm_calls)} calls, {total_llm_time:.0f}ms")
    print(f"Tools: {len(tool_calls)} calls, {total_tool_time:.0f}ms")
    print(f"Errors: {len(errors)}")
```

---

## Pending Tool (before_each_tool only)

During `before_each_tool` events, you can access the tool about to execute:

```python
from connectonion import Agent, before_each_tool

def approve_dangerous(agent):
    pending = agent.current_session.get('pending_tool')
    if not pending:
        return
    
    # Inspect before execution
    print(f"About to call: {pending['name']}")
    print(f"With args: {pending['arguments']}")
    print(f"Tool ID: {pending['id']}")
    
    # Block if needed
    if pending['name'] == 'delete_all':
        raise ValueError("Blocked dangerous operation")

agent = Agent("bot", tools=[...], on_events=[before_each_tool(approve_dangerous)])
```

`pending_tool` structure:

```python
{
    'name': 'bash',
    'arguments': {'command': 'rm -rf /tmp/*'},
    'id': 'call_xyz789',  # LLM's tool call ID
}
```

---

## Streaming Trace to Frontend

When connected to a frontend (via `agent.connection`), trace entries are automatically streamed as WebSocket events:

```python
# Backend emits these events:
{'type': 'user_input', 'content': '...', 'id': 1, 'ts': ...}
{'type': 'thinking', 'content': '...', 'kind': 'plan', 'id': 2, 'ts': ...}
{'type': 'tool_call', 'tool_id': '...', 'name': '...', 'args': {...}, 'id': 3, 'ts': ...}
{'type': 'tool_result', 'tool_id': '...', 'name': '...', 'status': 'success', 'id': 4, 'ts': ...}
{'type': 'assistant', 'content': '...', 'id': 4, 'ts': ...}
{'type': 'complete', 'tools_used': [...], 'llm_calls': 2, 'iterations': 3}
```

Frontend can render these in real-time to show agent activity.

---

## Session Lifecycle

```
agent.input("prompt")
    |
    v
[Session Created/Continued]
    |
    +-- messages: [system, user]
    +-- trace: [{user_input}]
    +-- turn: 1
    +-- iteration: 1
    |
    v
[LLM Call]
    |
    +-- trace: [..., {llm_call}]
    |
    v
[Tool Execution] (if tool_calls)
    |
    +-- trace: [..., {tool_result}]
    +-- messages: [..., assistant, tool]
    +-- iteration: 2
    |
    v
[Loop until done or max_iterations]
    |
    v
[Final Response]
    |
    +-- trace: [..., {assistant}]
    +-- messages: [..., assistant]
    |
    v
[Session Persists for Next Turn]
```

---

## Resetting Session

Clear conversation history and start fresh:

```python
agent.reset_conversation()

# Next input() starts with clean session
agent.input("New conversation")
```

After reset:
- `messages` cleared (only system prompt remains)
- `trace` cleared
- `turn` reset to 1
- Token usage preserved (for cost tracking)

---

## Best Practices

### 1. Check trace type before accessing fields

```python
def safe_handler(agent):
    last = agent.current_session['trace'][-1]
    
    # Different types have different fields
    if last['type'] == 'tool_result':
        print(last['name'], last['result'])
    elif last['type'] == 'llm_call':
        print(last['model'], last['duration_ms'])
```

### 2. Use .get() for optional fields

```python
def handle_error(agent):
    last = agent.current_session['trace'][-1]
    
    # 'error' only exists on error status
    error = last.get('error', 'Unknown error')
    error_type = last.get('error_type', 'Error')
```

### 3. Don't modify trace directly

Trace is append-only. Add entries via proper channels (tools, LLM calls), not by modifying the list.

### 4. Use after_tools for message injection

```python
# Good - after_tools is safe for all providers
@after_tools
def add_reflection(agent):
    agent.current_session['messages'].append({...})

# Risky - may break Anthropic compatibility
@after_each_tool  
def add_reflection(agent):
    agent.current_session['messages'].append({...})  # Don't do this
```

---

## What's Next?

- [Events](events.md) - Hook into agent lifecycle
- [Agent](agent.md) - Full agent API reference
- [Tools](tools.md) - Build powerful tools
