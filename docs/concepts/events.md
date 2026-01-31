# Event System (on_events)

ConnectOnion's event system lets you hook into the agent lifecycle to add custom behavior like logging, performance monitoring, or adding reasoning steps between tool uses.

---

## Quick Start (60 seconds)

```python
from connectonion import Agent, after_llm

def log_llm_call(agent):
    """Log LLM calls"""
    last_trace = agent.current_session['trace'][-1]
    if last_trace['type'] == 'llm_call':
        print(f"LLM call took {last_trace['duration_ms']:.0f}ms")

agent = Agent(
    "assistant",
    tools=[search],
    on_events=[
        after_llm(log_llm_call)
    ]
)
```

**Group multiple handlers:**

```python
from connectonion import Agent, before_each_tool

def check_shell(agent):
    ...

def check_email(agent):
    ...

agent = Agent(
    "assistant",
    on_events=[
        before_each_tool(check_shell, check_email),  # both handlers for same event
    ]
)
```

**That's it!** Your events run automatically at the right lifecycle points.

> **Note: Alternative Decorator Syntax**
>
> You can also use decorator syntax: `@before_each_tool` instead of `before_each_tool(fn)`.
> ```python
> @before_each_tool
> def check_shell(agent):
>     ...
>
> on_events=[check_shell]  # works!
> ```
> We recommend the wrapper style `before_each_tool(fn)` because it's easier for LLMs to understand when reading your code. But if you find decorators more elegant, feel free to use them.

---

## Event Types

| Event | When It Runs | Fires | Use For |
|-------|--------------|-------|---------|
| `after_user_input` | After user provides input | Once per turn | Add context, timestamps, initialize turn state |
| `before_llm` | Before each LLM call | Multiple per turn | Modify messages for each LLM call |
| `after_llm` | After LLM responds | Multiple per turn | Log LLM calls, analyze responses |
| `before_tools` | Before ALL tools in round | Once per round | Prepare shared context for all tools |
| `before_each_tool` | Before tool execution | Per tool call | Validate args, approval checks (no message changes!) |
| `after_each_tool` | After each tool completes | Per tool call | Log performance, side effects (no message changes!) |
| `after_tools` | After ALL tools in round | Once per round | Add reflection, **ONLY place safe to modify messages** |
| `on_error` | When tool fails | Per tool error | Custom error handling, retries |
| `on_complete` | After agent finishes | Once per input() | Metrics, cleanup, final summary |

> **Note on message injection:** Use `after_tools` (not `after_each_tool`) when adding messages to ensure compatibility with all LLM providers. Anthropic Claude requires tool results to immediately follow tool_calls.

---

## Your Event Function

**All events receive the `agent` instance:**

```python
def my_event(agent):
    # Access everything:
    agent.current_session['messages']  # Full conversation
    agent.current_session['trace']     # Execution history
    agent.current_session['iteration'] # Current iteration (1-10)
    agent.current_session['turn']      # Current turn number
    agent.current_session['user_prompt'] # Current user input

    # Only in before_each_tool events:
    agent.current_session['pending_tool']  # Tool about to execute
    # {'name': 'bash', 'arguments': {'command': 'ls'}, 'id': 'call_123'}

    # Modify the agent:
    agent.current_session['messages'].append({
        'role': 'system',
        'content': 'Added by my event!'
    })
```

**What's in the trace?**

The most recent trace entry shows what just happened:

```python
def my_event(agent):
    trace = agent.current_session['trace'][-1]

    # For user_input:
    trace['type']           # 'user_input'
    trace['content']        # "Search for Python"
    trace['turn']           # 1

    # For llm_call:
    trace['type']           # 'llm_call'
    trace['model']          # 'gpt-4o-mini'
    trace['duration_ms']    # 234.5
    trace['tool_calls_count'] # 2
    trace['iteration']      # 1

    # For tool_result:
    trace['type']           # 'tool_result'
    trace['name']           # 'search'
    trace['args']           # {'query': 'Python'}
    trace['result']         # "Python is a programming language..."
    trace['status']         # 'success' | 'error' | 'not_found'
    trace['timing_ms']      # 123.4
    trace['call_id']        # 'call_abc123'

    # For error status:
    trace['error']          # "Division by zero"
    trace['error_type']     # "ZeroDivisionError"
```

> See [Session](session.md) for complete trace documentation.

---

## Examples

### Approve Dangerous Commands (before_each_tool)

Use `before_each_tool` to intercept and approve tool calls before execution:

```python
from connectonion import Agent, before_each_tool

def approve_dangerous_commands(agent):
    """Ask for approval before dangerous bash commands"""
    pending = agent.current_session.get('pending_tool')
    if not pending:
        return

    # Only check bash commands
    if pending['name'] != 'bash':
        return

    command = pending['arguments'].get('command', '')

    # Check for dangerous patterns
    if 'rm ' in command or 'sudo ' in command:
        print(f"\n⚠️ Dangerous command: {command}")
        response = input("Execute? (y/N): ")
        if response.lower() != 'y':
            raise ValueError("Command rejected by user")

agent = Agent(
    "assistant",
    tools=[bash],
    on_events=[before_each_tool(approve_dangerous_commands)]
)
```

**Note:** `pending_tool` is only available during `before_each_tool` events. It contains:
- `name`: Tool name (e.g., "bash")
- `arguments`: Tool arguments (e.g., `{'command': 'rm -rf /tmp'}`)
- `id`: Tool call ID

---

### Add Context Once Per Turn

Use `after_user_input` to add context that should only be set once per turn:

```python
from connectonion import Agent, after_user_input
from datetime import datetime

def add_timestamp(agent):
    """Add current time once when user provides input"""
    agent.current_session['messages'].append({
        'role': 'system',
        'content': f'Current time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
    })

agent = Agent("assistant", tools=[search], on_events=[after_user_input(add_timestamp)])
```

### Add Reflection After Tools

Use `llm_do` to make the agent reflect on tool results and plan next steps. **Important:** Use `after_tools` when adding messages to ensure compatibility with all LLM providers:

```python
from connectonion import Agent, after_tools, llm_do

def add_reflection(agent):
    """Add reasoning after all tools in a round complete"""
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_result' and trace['status'] == 'success':
        tool_name = trace['name']
        tool_args = trace['args']
        result = trace['result']

        # Use llm_do to generate reflection
        reflection_prompt = f"""
You just used the {tool_name} tool with arguments {tool_args}.
Result: {result[:200]}

Provide a brief reflection:
1. What did we learn?
2. What should we do next?
3. Are we making progress toward the goal?
"""

        reflection = llm_do(
            reflection_prompt,
            system_prompt="You are a thoughtful analyst. Be concise.",
            temperature=0.3
        )

        # Add reflection to conversation (safe in after_tools)
        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"🤔 Reflection: {reflection}"
        })

        print(f"💭 Reflection: {reflection[:100]}...")

agent = Agent(
    "researcher",
    tools=[search, analyze],
    on_events=[after_tools(add_reflection)]  # Use after_tools for message injection
)

# Now the agent will reflect after each round of tool use!
agent.input("Research the latest AI trends and analyze their impact")
# 💭 Reflection: We learned about transformer models. Next, we should analyze...
```

### Performance Monitoring

```python
from connectonion import Agent, after_llm, after_each_tool

def monitor_llm_performance(agent):
    """Track LLM call performance"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'llm_call':
        duration = trace['duration_ms']
        model = trace['model']
        if duration > 5000:  # More than 5 seconds
            print(f"⚡ Slow LLM call: {model} took {duration/1000:.1f}s")

def monitor_tool_performance(agent):
    """Track slow tool executions"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_result':
        timing = trace.get('timing_ms', 0)
        tool_name = trace['name']

        if timing > 1000:  # More than 1 second
            print(f"⚡ Slow tool: {tool_name} took {timing:.0f}ms")

agent = Agent(
    "assistant",
    tools=[search],
    on_events=[
        after_llm(monitor_llm_performance),
        after_each_tool(monitor_tool_performance)  # per-tool monitoring
    ]
)
```

### Custom Error Handling

```python
from connectonion import Agent, on_error

def handle_tool_error(agent):
    """Log and handle tool failures"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_result' and trace['status'] == 'error':
        tool_name = trace['name']
        error = trace.get('error', 'Unknown error')
        error_type = trace.get('error_type', 'Unknown')

        print(f"⚠️ {tool_name} failed with {error_type}: {error}")

        # Could send to logging service, retry, etc.
        # Note: If this event raises an exception, the agent stops

agent = Agent("assistant", tools=[search], on_events=[on_error(handle_tool_error)])
```

### Task Completion Handler (on_complete)

Use `on_complete` to run logic after the agent finishes a task:

```python
from connectonion import Agent, on_complete

def log_completion(agent):
    """Log when task completes"""
    trace = agent.current_session['trace']

    llm_calls = sum(1 for t in trace if t['type'] == 'llm_call')
    tool_calls = sum(1 for t in trace if t['type'] == 'tool_result')
    errors = sum(1 for t in trace if t.get('status') == 'error')

    print(f"✅ Task complete: {llm_calls} LLM calls, {tool_calls} tools, {errors} errors")

agent = Agent(
    "assistant",
    tools=[search],
    on_events=[on_complete(log_completion)]
)

agent.input("Search for Python")
# ✅ Task complete: 2 LLM calls, 1 tools, 0 errors
```

**Use cases for `on_complete`:**
- Final metrics and statistics
- Cleanup temporary resources
- Send task completion notifications
- Log total execution time
- Update external systems

### Session Statistics

```python
from connectonion import Agent, after_llm

def session_stats(agent):
    """Print session statistics after each LLM call"""
    trace = agent.current_session['trace']

    llm_calls = sum(1 for t in trace if t['type'] == 'llm_call')
    tool_calls = sum(1 for t in trace if t['type'] == 'tool_result')
    errors = sum(1 for t in trace if t.get('status') == 'error')

    print(f"📊 Stats: {llm_calls} LLM calls | {tool_calls} tool calls | {errors} errors")

agent = Agent("assistant", tools=[search], on_events=[after_llm(session_stats)])
```

### Smart Tool Selection with Reflection

Help the agent think about which tool to use next:

```python
from connectonion import Agent, after_tools, llm_do
from pydantic import BaseModel

class ToolRecommendation(BaseModel):
    next_tool: str
    reasoning: str
    confidence: float

def suggest_next_tool(agent):
    """Suggest which tool to use next based on current progress"""
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_result' and trace['status'] == 'success':
        tool_name = trace['name']
        result = trace['result']

        # Get list of available tools
        available_tools = agent.list_tools()

        suggestion_prompt = f"""
We just used: {tool_name}
Result: {result[:200]}

Available tools: {', '.join(available_tools)}

What tool should we use next and why?
"""

        suggestion = llm_do(
            suggestion_prompt,
            output=ToolRecommendation,
            system_prompt="You are a strategic planner. Consider the goal and current progress.",
            temperature=0.2
        )

        # Add suggestion as a system message (safe in after_tools)
        agent.current_session['messages'].append({
            'role': 'system',
            'content': f"Suggestion: Use {suggestion.next_tool}. {suggestion.reasoning}"
        })

        print(f"💡 Suggested next tool: {suggestion.next_tool} (confidence: {suggestion.confidence})")

agent = Agent(
    "strategist",
    tools=[search, analyze, summarize],
    on_events=[after_tools(suggest_next_tool)]  # Use after_tools for message injection
)
```

---

## Organizing Event Code

### Keep Each Function Focused

Each helper function should do one thing:

```python
# my_events.py

def log_llm_timing(agent):
    """Single job: Log LLM timing"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'llm_call':
        duration = trace['duration_ms']
        print(f"💬 LLM: {duration:.0f}ms")

def log_tool_timing(agent):
    """Single job: Log tool timing"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_execution':
        timing = trace['timing']
        print(f"🔧 Tool: {timing:.0f}ms")

def add_reflection(agent):
    """Single job: Add reflection after tools"""
    from connectonion import llm_do

    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_result' and trace['status'] == 'success':
        tool_name = trace['name']
        result = trace['result']

        # Use llm_do for quick reflection
        reflection = llm_do(
            f"Tool: {tool_name}\nResult: {result[:200]}\n\nWhat did we learn? What's next?",
            system_prompt="You are concise and strategic.",
            temperature=0.3
        )

        # Add to conversation
        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"💭 {reflection}"
        })

def suggest_next_action(agent):
    """Suggest what to do next"""
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_result':
        available_tools = agent.list_tools()

        suggestion = llm_do(
            f"We just used {trace['name']}. Available tools: {available_tools}. What next?",
            system_prompt="Be strategic and brief.",
            temperature=0.2
        )

        print(f"💡 Suggestion: {suggestion}")
```

### Example: `events/handlers.py`

```python
"""Main event handlers - compose helpers here"""
from .logging import log_llm_call, log_tool_execution, log_errors
from .reflection import add_tool_reflection

def handle_after_llm(agent):
    """Handle all after_llm concerns"""
    log_llm_call(agent)        # 1. Log LLM calls
    # Order is explicit and easy to modify

def handle_after_each_tool(agent):
    """Handle per-tool concerns (no message injection)"""
    log_tool_execution(agent)  # Log execution timing
    # Clear execution order

def handle_after_tools(agent):
    """Handle batch concerns (safe for message injection)"""
    add_tool_reflection(agent) # Add reflection after all tools
    # Safe to add messages here

def handle_on_error(agent):
    """Handle all error concerns"""
    log_errors(agent)          # 1. Log the error
    # Could add: send_alert(agent), retry_logic(agent), etc.
```

### Example: `events/__init__.py`

```python
"""Export event handlers for easy import"""
from .handlers import handle_after_llm, handle_after_each_tool, handle_after_tools, handle_on_error

__all__ = ['handle_after_llm', 'handle_after_each_tool', 'handle_after_tools', 'handle_on_error']
```

### Example: `main.py`

```python
"""Main agent - clean and focused"""
from connectonion import Agent, after_llm, after_each_tool, after_tools, on_error
from tools import search, calculate
from events import handle_after_llm, handle_after_each_tool, handle_after_tools, handle_on_error

agent = Agent(
    "assistant",
    tools=[search, calculate],
    on_events=[
        after_llm(handle_after_llm),
        after_each_tool(handle_after_each_tool),        # per-tool
        after_tools(handle_after_tools),      # batch
        on_error(handle_on_error)
    ]
)

result = agent.input("Search for Python and calculate 2+2")
print(result)
```

**Benefits of this structure:**
- 🎯 **Clear separation** - tools, events, and main logic are separate
- 🔧 **Single responsibility** - each file/function has one job
- 🧪 **Easy to test** - test each helper independently
- 📖 **Easy to read** - anyone can understand the flow
- 🔄 **Reusable** - helpers can be used across different agents
- 🏗️ **Scalable** - easy to add new event helpers

---

## Simple vs Complex Projects

### For Simple Projects

Just put everything in one file:

```python
# simple_agent.py
from connectonion import Agent, after_llm

def log_llm(agent):
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'llm_call':
        print(f"LLM: {trace['duration_ms']:.0f}ms")

agent = Agent("assistant", tools=[search], on_events=[after_llm(log_llm)])
```

### For Complex Projects

Use the folder structure above when you have:
- Multiple event handlers
- Multiple concerns (logging, reflection, analytics, etc.)
- Multiple agents sharing event logic
- Need for testing and maintenance

---

## Error Handling

**Events fail fast.** If your event raises an exception, the agent stops immediately:

```python
def strict_validator(agent):
    trace = agent.current_session['trace'][-1]
    if trace.get('status') == 'error':
        raise ValueError("Tool execution failed - stopping agent")
        # ☝️ This stops the entire agent

agent = Agent(
    "assistant",
    tools=[search],
    on_events=[after_each_tool(strict_validator)]  # per-tool validation
)
```

This ensures events are reliable and bugs don't get silently ignored.

---

## Reusable Events

Create event factories for common patterns:

```python
# my_events.py
from connectonion import after_llm

def llm_timer(threshold_ms=1000):
    """Factory function for LLM timing alerts"""

    def check_timing(agent):
        trace = agent.current_session['trace'][-1]
        if trace['type'] == 'llm_call':
            duration = trace['duration_ms']
            if duration > threshold_ms:
                print(f"⚠️ Slow LLM call: {duration:.0f}ms (threshold: {threshold_ms}ms)")

    return check_timing  # Return the function, will be wrapped by after_llm()

# Use it:
from my_events import llm_timer
from connectonion import after_llm

agent = Agent(
    "assistant",
    tools=[search],
    on_events=[
        after_llm(llm_timer(threshold_ms=2000))
    ]
)
```

---

## Testing Your Events

With single-responsibility functions, testing is easy:

```python
# tests/test_events.py
from unittest.mock import Mock
from events.logging import log_llm_call
from events.reflection import add_tool_reflection

def test_log_llm_call(capsys):
    """Test LLM logging"""
    mock_agent = Mock()
    mock_agent.current_session = {
        'trace': [{'type': 'llm_call', 'model': 'gpt-4o-mini', 'duration_ms': 234.5}]
    }

    log_llm_call(mock_agent)

    captured = capsys.readouterr()
    assert "234ms" in captured.out

def test_add_tool_reflection():
    """Test reflection adding"""
    mock_agent = Mock()
    mock_agent.current_session = {
        'trace': [{
            'type': 'tool_execution',
            'status': 'success',
            'tool_name': 'search',
            'result': 'Python is a programming language'
        }],
        'messages': []
    }

    add_tool_reflection(mock_agent)

    # Check that a message was added
    assert len(mock_agent.current_session['messages']) == 1
    assert 'assistant' in mock_agent.current_session['messages'][0]['role']
```

---

## Common Use Cases

- **🧠 Reflection**: Add thinking steps between tool uses with `llm_do`
- **📝 Logging**: Custom logging to files, databases, or external services
- **🔍 Debugging**: Print detailed trace information
- **⚡ Performance**: Measure and optimize execution time
- **🛡️ Validation**: Enforce constraints on tool arguments or results
- **🔄 Retry Logic**: Automatically retry failed operations
- **📊 Analytics**: Send metrics to monitoring systems
- **🎯 Context Injection**: Add dynamic context once per turn with `after_user_input`
- **⏰ Timeouts**: Monitor and enforce time limits
- **🚨 Alerting**: Send notifications on errors or slow operations
- **💡 Strategy**: Suggest next tools or actions using `llm_do`

---

## What's Next?

- [llm_do](/llm_do) - Learn how to use `llm_do` for one-shot LLM calls in events
- [Examples](/examples) - See real-world event implementations
- [API Reference](/api/events) - Detailed API documentation
- [Trust System](/trust) - Learn about combining events with trust