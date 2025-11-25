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
        model = last_trace['model']
        duration = last_trace['duration_ms']
        print(f"💬 LLM call to {model} took {duration:.0f}ms")

agent = Agent(
    "assistant",
    tools=[search, calculate],
    on_events=[
        after_llm(log_llm_call)
    ]
)

agent.input("Search for Python and calculate 2+2")
# 💬 LLM call to gpt-4o-mini took 234ms
# 💬 LLM call to gpt-4o-mini took 189ms
```

**That's it!** Your event runs automatically after every LLM call.

---

## Event Types

| Event | When It Runs | Fires | Use For |
|-------|--------------|-------|---------|
| `after_user_input` | After user provides input | Once per turn | Add context, timestamps, initialize turn state |
| `before_llm` | Before each LLM call | Multiple per turn | Modify messages for each LLM call |
| `after_llm` | After LLM responds | Multiple per turn | Log LLM calls, analyze responses |
| `before_tool` | Before tool execution | Per tool call | Validate args, add logging |
| `after_tool` | After tool succeeds | Per tool call | Add reflection, log performance |
| `on_error` | When tool fails | Per tool error | Custom error handling, retries |

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

    # Only in before_tool events:
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
    last_trace = agent.current_session['trace'][-1]

    # For user_input events:
    last_trace['type']           # 'user_input'
    last_trace['prompt']         # "Search for Python"
    last_trace['turn']           # 1
    last_trace['timestamp']      # 1234567890.123

    # For llm_call events:
    last_trace['type']           # 'llm_call'
    last_trace['model']          # 'gpt-4o-mini'
    last_trace['duration_ms']    # 234.5
    last_trace['tool_calls_count'] # 2
    last_trace['iteration']      # 1
    last_trace['timestamp']      # 1234567890.123

    # For tool_execution events:
    last_trace['type']           # 'tool_execution'
    last_trace['tool_name']      # 'search'
    last_trace['arguments']      # {'query': 'Python'}
    last_trace['result']         # "Python is a programming language..."
    last_trace['status']         # 'success' | 'error' | 'not_found'
    last_trace['timing']         # 123.4 (milliseconds)
    last_trace['call_id']        # 'call_abc123'
    last_trace['iteration']      # 1
    last_trace['timestamp']      # 1234567890.456

    # For error status:
    last_trace['error']          # "Division by zero"
    last_trace['error_type']     # "ZeroDivisionError"
```

---

## Examples

### Approve Dangerous Commands (before_tool)

Use `before_tool` to intercept and approve tool calls before execution:

```python
from connectonion import Agent, before_tool

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
    on_events=[before_tool(approve_dangerous_commands)]
)
```

**Note:** `pending_tool` is only available during `before_tool` events. It contains:
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

Use `llm_do` to make the agent reflect on tool results and plan next steps:

```python
from connectonion import Agent, after_tool, llm_do

def add_reflection(agent):
    """Add reasoning after each tool execution"""
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        tool_name = trace['tool_name']
        tool_args = trace['arguments']
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

        # Add reflection to conversation
        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"🤔 Reflection: {reflection}"
        })

        print(f"💭 Reflection: {reflection[:100]}...")

agent = Agent(
    "researcher",
    tools=[search, analyze],
    on_events=[after_tool(add_reflection)]
)

# Now the agent will reflect after each tool use!
agent.input("Research the latest AI trends and analyze their impact")
# 💭 Reflection: We learned about transformer models. Next, we should analyze...
# 💭 Reflection: The analysis shows strong growth. We should search for...
```

### Performance Monitoring

```python
from connectonion import Agent, after_llm, after_tool

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
    if trace['type'] == 'tool_execution':
        timing = trace.get('timing', 0)
        tool_name = trace['tool_name']

        if timing > 1000:  # More than 1 second
            print(f"⚡ Slow tool: {tool_name} took {timing:.0f}ms")

agent = Agent(
    "assistant",
    tools=[search],
    on_events=[
        after_llm(monitor_llm_performance),
        after_tool(monitor_tool_performance)
    ]
)
```

### Custom Error Handling

```python
from connectonion import Agent, on_error

def handle_tool_error(agent):
    """Log and handle tool failures"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_execution' and trace['status'] == 'error':
        tool_name = trace['tool_name']
        error = trace.get('error', 'Unknown error')
        error_type = trace.get('error_type', 'Unknown')

        print(f"⚠️ {tool_name} failed with {error_type}: {error}")

        # Could send to logging service, retry, etc.
        # Note: If this event raises an exception, the agent stops

agent = Agent("assistant", tools=[search], on_events=[on_error(handle_tool_error)])
```

### Session Statistics

```python
from connectonion import Agent, after_llm

def session_stats(agent):
    """Print session statistics after each LLM call"""
    trace = agent.current_session['trace']

    llm_calls = sum(1 for t in trace if t['type'] == 'llm_call')
    tool_calls = sum(1 for t in trace if t['type'] == 'tool_execution')
    errors = sum(1 for t in trace if t.get('status') == 'error')

    print(f"📊 Stats: {llm_calls} LLM calls | {tool_calls} tool calls | {errors} errors")

agent = Agent("assistant", tools=[search], on_events=[after_llm(session_stats)])
```

### Smart Tool Selection with Reflection

Help the agent think about which tool to use next:

```python
from connectonion import Agent, after_tool, llm_do
from pydantic import BaseModel

class ToolRecommendation(BaseModel):
    next_tool: str
    reasoning: str
    confidence: float

def suggest_next_tool(agent):
    """Suggest which tool to use next based on current progress"""
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        tool_name = trace['tool_name']
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

        # Add suggestion as a system message
        agent.current_session['messages'].append({
            'role': 'system',
            'content': f"Suggestion: Use {suggestion.next_tool}. {suggestion.reasoning}"
        })

        print(f"💡 Suggested next tool: {suggestion.next_tool} (confidence: {suggestion.confidence})")

agent = Agent(
    "strategist",
    tools=[search, analyze, summarize],
    on_events=[after_tool(suggest_next_tool)]
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
    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        reflection = llm_do(
            f"Reflect on this tool result: {trace['result'][:200]}",
            system_prompt="Be concise. What did we learn?",
            temperature=0.3
        )
        agent.current_session['messages'].append({
            'role': 'assistant',
            'content': f"💭 {reflection}"
        })
```

### Compose Into Event Handlers

Then compose them in your event handler with explicit order:

```python
# main.py
from my_events import log_llm_timing, log_tool_timing, add_reflection
from connectonion import Agent, after_llm, after_tool

def handle_after_llm(agent):
    """Compose multiple concerns in explicit order"""
    log_llm_timing(agent)       # 1. Log timing
    # Order is clear and explicit!

def handle_after_tool(agent):
    """Compose tool event concerns"""
    log_tool_timing(agent)      # 1. Log timing
    add_reflection(agent)       # 2. Add reflection
    # Clear execution order

agent = Agent(
    "assistant",
    tools=[search],
    on_events=[
        after_llm(handle_after_llm),
        after_tool(handle_after_tool)
    ]
)
```

**Why this is better:**
- ✅ **Explicit order** - you see exactly what runs when
- ✅ **Single responsibility** - each function does one thing
- ✅ **Easy to test** - test each function independently
- ✅ **Easy to debug** - clear execution flow
- ✅ **Reusable** - compose functions differently for different agents

---

## Recommended Project Structure

For projects using events, organize your code like this:

```
my_project/
├── main.py                 # Main agent setup
├── tools/
│   ├── __init__.py
│   ├── search.py          # search() tool
│   └── calculate.py       # calculate() tool
└── events/
    ├── __init__.py        # Export event handlers
    ├── handlers.py        # Main event handler functions
    ├── logging.py         # Logging-related helpers
    └── reflection.py      # Reflection helpers
```

### Example: `events/logging.py`

```python
"""Logging helpers - each function does one thing"""

def log_llm_call(agent):
    """Log LLM call timing"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'llm_call':
        duration = trace['duration_ms']
        model = trace['model']
        print(f"💬 {model}: {duration:.0f}ms")

def log_tool_execution(agent):
    """Log tool execution details"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_execution':
        tool_name = trace['tool_name']
        status = trace['status']
        timing = trace['timing']
        print(f"🔧 {tool_name}: {status} ({timing:.0f}ms)")

def log_errors(agent):
    """Log tool errors"""
    trace = agent.current_session['trace'][-1]
    if trace['type'] == 'tool_execution' and trace['status'] == 'error':
        tool_name = trace['tool_name']
        error = trace['error']
        print(f"❌ {tool_name}: {error}")
```

### Example: `events/reflection.py`

```python
"""Reflection helpers - add thinking between steps"""
from connectonion import llm_do

def add_tool_reflection(agent):
    """Add reflection after each tool use"""
    trace = agent.current_session['trace'][-1]

    if trace['type'] == 'tool_execution' and trace['status'] == 'success':
        tool_name = trace['tool_name']
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

    if trace['type'] == 'tool_execution':
        available_tools = agent.list_tools()

        suggestion = llm_do(
            f"We just used {trace['tool_name']}. Available tools: {available_tools}. What next?",
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

def handle_after_tool(agent):
    """Handle all after_tool concerns"""
    log_tool_execution(agent)  # 1. Log execution
    add_tool_reflection(agent) # 2. Add reflection
    # Clear execution order

def handle_on_error(agent):
    """Handle all error concerns"""
    log_errors(agent)          # 1. Log the error
    # Could add: send_alert(agent), retry_logic(agent), etc.
```

### Example: `events/__init__.py`

```python
"""Export event handlers for easy import"""
from .handlers import handle_after_llm, handle_after_tool, handle_on_error

__all__ = ['handle_after_llm', 'handle_after_tool', 'handle_on_error']
```

### Example: `main.py`

```python
"""Main agent - clean and focused"""
from connectonion import Agent, after_llm, after_tool, on_error
from tools import search, calculate
from events import handle_after_llm, handle_after_tool, handle_on_error

agent = Agent(
    "assistant",
    tools=[search, calculate],
    on_events=[
        after_llm(handle_after_llm),
        after_tool(handle_after_tool),
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
    on_events=[after_tool(strict_validator)]
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