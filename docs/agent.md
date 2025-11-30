# Agent

> The heart of ConnectOnion. Give it tools, and it figures out the rest.

---

## Quick Start (60 Seconds)

```python
from connectonion import Agent

# Define what your agent can do
def calculate(expression: str) -> str:
    """Do math calculations."""
    return str(eval(expression))

# Create agent
agent = Agent("math_bot", tools=[calculate])

# Use it
result = agent.input("What is 42 * 17?")
```

**Output:**
```
To calculate 42 * 17, I'll use the calculator tool.
The result is 714.
```

**That's it.** Your first AI agent in 5 lines.

---

## What Agent Can Do - Full API Overview

After that simple example, here's **everything** an Agent can do:

### Creating an Agent

```python
Agent(
    name="my_bot",                        # Required: agent identifier
    tools=[func1, func2],                 # Optional: functions agent can call
    system_prompt="You are helpful",      # Optional: personality/behavior
    model="o4-mini",                      # Optional: LLM model (OpenAI/Claude/Gemini)
    max_iterations=10,                    # Optional: how many tool calls allowed
    api_key="sk-...",                     # Optional: override environment variable
    llm=custom_llm,                       # Optional: bring your own LLM instance
    trust="tested",                       # Optional: security verification
    log=True                              # Optional: logging configuration
)
```

### Using Your Agent

```python
# Give it a task
result = agent.input("Do something")

# Override iterations for complex tasks
result = agent.input("Complex task", max_iterations=20)

# Execute a tool directly (for testing)
result = agent.execute_tool("tool_name", {"arg": "value"})
```

### Managing Tools

```python
# Add tools after creation
agent.add_tool(new_function)

# Remove tools
agent.remove_tool("function_name")

# See what tools are available
tools = agent.list_tools()
```

### Conversations & State

```python
# Multi-turn conversations work automatically
agent.input("What is 10 + 5?")       # Turn 1: "15"
agent.input("Multiply that by 2")    # Turn 2: "30" (remembers context)

# Start fresh
agent.reset_conversation()

# Access internal state (advanced)
session = agent.current_session      # Messages, trace, turn count
```

### Attributes You Can Access

```python
agent.name                  # str: Agent identifier
agent.tools                 # ToolRegistry: All available tools
agent.tools.names()         # list[str]: Tool names
agent.tools.get("name")     # Tool: Get tool by name
agent.tools.tool_name       # Tool: Attribute access to tools
agent.system_prompt         # str: Agent's personality
agent.max_iterations        # int: Default iteration limit
agent.current_session       # dict | None: Runtime state

# Token usage tracking
agent.last_usage            # TokenUsage | None: From last LLM call
agent.total_cost            # float: Cumulative cost in USD
agent.context_percent       # float: Context window usage (0-100%)
```

**That's the complete API.** Now let's dive into each feature.

---

## Table of Contents

1. [Creating Agents](#creating-agents)
2. [Using Your Agent](#using-your-agent)
3. [Managing Tools](#managing-tools)
4. [Conversations & Multi-Turn](#conversations--multi-turn)
5. [Iteration Control](#iteration-control)
6. [Models & LLMs](#models--llms)
7. [Token Usage & Cost Tracking](#token-usage--cost-tracking)
8. [Logging & Debugging](#logging--debugging)
9. [Trust & Security](#trust--security)
10. [Common Patterns](#common-patterns)
11. [Testing Your Agents](#testing-your-agents)
12. [Architecture & Internals](#architecture--internals)

---

## Creating Agents

### Minimal Agent

```python
agent = Agent("my_bot")  # Just conversation, no tools
```

### Agent with Tools

```python
def search(query: str) -> str:
    """Search for information."""
    return f"Found results for '{query}'"

def get_time() -> str:
    """Get current time."""
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")

agent = Agent(
    "assistant",
    tools=[search, get_time]
)
```

### Agent with Personality

```python
agent = Agent(
    "expert",
    tools=[search],
    system_prompt="You are a thorough researcher. Always cite sources."
)
```

### Load Prompt from File

```python
# Automatically detects if it's a file path
agent = Agent(
    "bot",
    system_prompt="prompts/assistant.md"  # Loads from file
)

# Or use Path object
from pathlib import Path
agent = Agent(
    "bot",
    system_prompt=Path("prompts/expert.txt")
)
```

**System prompt rules:**
- Can be a direct string
- Can be a file path (auto-detected if file exists)
- Can be a Path object
- Defaults to "You are a helpful assistant that can use tools to complete tasks."

---

## Using Your Agent

### Basic Usage

```python
agent = Agent("helper", tools=[search, calculate])

# Give it a task
result = agent.input("Search for Python docs and calculate 2+2")
```

### Console Output

When you run `agent.input()`, you'll see:

```
INPUT: Search for Python docs and calculate 2+2

  Iteration 1/10
  → LLM Request (gpt-4o-mini)
  ← LLM Response (234ms): 2 tool calls
  → Tool: search({"query": "Python docs"})
  ← Result (1ms): Found results for 'Python docs'
  → Tool: calculate({"expression": "2+2"})
  ← Result (0ms): 4

  Iteration 2/10
  → LLM Request (gpt-4o-mini)
  ← LLM Response (189ms)

✓ Complete (0.4s)
```

### How It Works

```
User Input
    ↓
LLM Decision (should I use a tool?)
    ↓
Tool Execution (if needed)
    ↓
LLM sees results → Repeat
    ↓
Final Response (when LLM is done)
```

The agent loops until:
- LLM provides a final answer (no more tool calls), OR
- Max iterations reached (default: 10)

---

## Managing Tools

### Add Tools Dynamically

```python
agent = Agent("bot")  # No tools initially

def new_feature(x: str) -> str:
    """Process something."""
    return f"Processed {x}"

agent.add_tool(new_feature)  # Now agent can use it
```

### Remove Tools

```python
removed = agent.remove_tool("calculator")
# Returns True if found and removed, False otherwise
```

### List Available Tools

```python
tools = agent.list_tools()
# ['search', 'calculate', 'get_time']
```

### Execute Tool Directly

Useful for testing and debugging:

```python
result = agent.execute_tool("calculator", {"expression": "2+2"})

# Returns:
{
  "name": "calculator",
  "arguments": {"expression": "2+2"},
  "result": "4",
  "status": "success",      # or "error", "not_found"
  "timing": 1.23            # milliseconds
}
```

### Stateful Tools (Class Instances)

You can pass a class instance as tools, and the agent will extract all public methods:

```python
class Browser:
    def __init__(self):
        self.page = None

    def start(self) -> str:
        """Start browser."""
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.page = self.playwright.chromium.launch().new_page()
        return "Browser started"

    def navigate(self, url: str) -> str:
        """Navigate to URL."""
        self.page.goto(url)
        return f"Navigated to {url}"

    def screenshot(self, filename: str) -> str:
        """Take screenshot."""
        self.page.screenshot(path=filename)
        return f"Saved {filename}"

# Browser state persists across tool calls!
browser = Browser()
agent = Agent("web_bot", tools=browser, max_iterations=20)

agent.input("Go to wikipedia.org and take a screenshot")
# Agent calls: start() → navigate() → screenshot()
# All share the same browser instance
```

See [tools.md](tools.md) for complete tool guide.

---

## Conversations & Multi-Turn

### Automatic Context

Agents remember conversation history by default:

```python
agent = Agent("bot", tools=[calculator])

# Turn 1
response1 = agent.input("What is 10 + 5?")
# "The result is 15"

# Turn 2 - agent remembers "15" from previous turn
response2 = agent.input("Multiply that by 2")
# "The result is 30"
```

### Reset Conversation

```python
agent.reset_conversation()
# Next input starts fresh, no memory of previous turns
```

### Session State (Advanced)

Each conversation creates a session:

```python
agent.input("Hello")

# Inspect the session
session = agent.current_session
{
    'messages': [
        {'role': 'system', 'content': 'You are...'},
        {'role': 'user', 'content': 'Hello'},
        {'role': 'assistant', 'content': 'Hi!'},
    ],
    'trace': [
        {'type': 'user_input', 'prompt': 'Hello', 'timestamp': ...},
        {'type': 'llm_call', 'model': 'gpt-4o-mini', 'duration_ms': 234},
        {'type': 'tool_execution', 'tool_name': 'search', 'result': '...'},
    ],
    'turn': 1,              # Number of user inputs
    'iteration': 1,         # Current iteration within this turn
    'user_prompt': 'Hello'  # Latest user input
}
```

**Trace types:**
- `user_input` - User provided input
- `llm_call` - LLM API request/response
- `tool_execution` - Tool call and result

---

## Iteration Control

Each tool call is one iteration. Control how many times an agent can call tools:

### Set Default for Agent

```python
# Simple tasks need fewer iterations
agent = Agent("calc", tools=[calculate], max_iterations=5)

# Complex workflows need more
agent = Agent("researcher", tools=[search, analyze], max_iterations=20)
```

### Override Per Task

```python
agent = Agent("bot", tools=[...], max_iterations=10)

# Simple task uses default (10)
agent.input("What is 2+2?")

# Complex task needs more
agent.input(
    "Research AI trends, analyze data, write report",
    max_iterations=25  # Override just for this task
)
```

### Choosing the Right Limit

| Task Type | Recommended | Example |
|-----------|-------------|---------|
| Simple (1-2 tools) | **3-5** | "Calculate 2+2" |
| Standard | **8-10** | "Search and summarize" |
| Data analysis | **10-15** | "Load, process, visualize data" |
| Web automation | **15-25** | Browser workflows, scraping |
| Research | **20-30** | Multi-step analysis |
| Complex workflows | **30-50** | Full automation pipelines |

### What Happens at Max Iterations

```python
agent = Agent("bot", tools=[tool], max_iterations=3)

# If agent can't complete in 3 iterations:
result = agent.input("Impossible task")
# "Task incomplete: Maximum iterations (3) reached."
```

**Rule of thumb:** Start low, increase if you see "Maximum iterations reached" messages.

See [max_iterations_guide.md](max_iterations_guide.md) for detailed guide.

---

## Models & LLMs

### Supported Providers

Default model is `o4-mini`. You can use:

```python
# OpenAI models
agent = Agent("bot", model="gpt-4o-mini")
agent = Agent("bot", model="gpt-4o")
agent = Agent("bot", model="o1-mini")
agent = Agent("bot", model="o1")

# Anthropic Claude
agent = Agent("bot", model="claude-3-5-sonnet-20241022")
agent = Agent("bot", model="claude-3-5-haiku-20241022")
agent = Agent("bot", model="claude-opus-4")

# Google Gemini
agent = Agent("bot", model="gemini-1.5-pro")
agent = Agent("bot", model="gemini-1.5-flash")
agent = Agent("bot", model="gemini-2.0-flash-exp")
```

### Managed Keys (After `co auth`)

```python
# Use managed keys instead of your own
agent = Agent("bot", model="co/gpt-4o-mini")
agent = Agent("bot", model="co/claude-3-5-sonnet")
```

### API Keys

```python
# From environment (recommended)
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...

# Or pass directly
agent = Agent("bot", api_key="sk-...", model="gpt-4o-mini")
```

### Custom LLM Instance (Advanced)

```python
from connectonion.llm import AnthropicLLM

custom_llm = AnthropicLLM(
    model="claude-3-5-sonnet-20241022",
    api_key="sk-ant-..."
)

agent = Agent("bot", llm=custom_llm)
```

See [models.md](models.md) for complete model list and details.

---

## Token Usage & Cost Tracking

Track token consumption and API costs across LLM calls.

### Basic Usage

```python
agent = Agent("assistant", tools=[search])
result = agent.input("Search for Python tutorials")

# Check usage after any LLM call
print(f"Last call used {agent.last_usage.input_tokens} input tokens")
print(f"Total cost so far: ${agent.total_cost:.4f}")
print(f"Context window used: {agent.context_percent:.1f}%")
```

### TokenUsage Object

After each LLM call, `agent.last_usage` contains:

```python
from connectonion.usage import TokenUsage

# TokenUsage fields:
agent.last_usage.input_tokens      # Total input tokens
agent.last_usage.output_tokens     # Output/completion tokens
agent.last_usage.cached_tokens     # Tokens from cache (cheaper)
agent.last_usage.cache_write_tokens # Tokens written to cache (Anthropic)
agent.last_usage.cost              # Cost for this call in USD
```

### Multi-Turn Cost Tracking

```python
agent = Agent("chat", tools=[calculator])

agent.input("What is 10 + 5?")
print(f"After turn 1: ${agent.total_cost:.4f}")

agent.input("Multiply that by 2")
print(f"After turn 2: ${agent.total_cost:.4f}")

agent.input("Now divide by 3")
print(f"Total spent: ${agent.total_cost:.4f}")
```

### Context Window Monitoring

Monitor how much context you're using to avoid hitting limits:

```python
agent = Agent("researcher", tools=[search, analyze])

for topic in topics:
    result = agent.input(f"Research {topic}")

    # Warn if context is getting full
    if agent.context_percent > 80:
        print(f"Warning: {agent.context_percent:.0f}% context used")
        agent.reset_conversation()  # Start fresh
```

### Cache Pricing

Different providers handle caching differently:

| Provider | Cache Read | Cache Write |
|----------|-----------|-------------|
| OpenAI | 50% of input price | N/A |
| Anthropic | 10% of input price | 125% of input price |
| Google Gemini | 25% of input price | N/A |

Cached tokens save money on repeated context (e.g., system prompts, previous messages).

### Console Output

Token usage is automatically shown in console logs after each LLM call:

```
→ LLM Request (gpt-4o-mini) • 5 msgs • 2 tools
← LLM Response (0.8s) • 1,234 in • 156 out • $0.0003
```

### Supported Models

Cost tracking works with all supported providers:
- OpenAI (gpt-4o, gpt-4o-mini, o1, o3-mini, o4-mini)
- Anthropic Claude (claude-3-5-sonnet, claude-3-5-haiku, claude-opus-4)
- Google Gemini (gemini-2.5-pro, gemini-2.5-flash, gemini-1.5-pro)

Unknown models use default pricing estimates.

---

## Logging & Debugging

### Automatic Logging

All agent activity is automatically logged to two places:

**1. Console (always on):**
```
INPUT: What is 2+2?
  Iteration 1/10
  → LLM Request (gpt-4o-mini)
  ← LLM Response (234ms): 1 tool calls
  → Tool: calculator({"expression": "2+2"})
  ← Result (1ms): 4
✓ Complete (0.4s)
```

**2. File (configurable):**

```python
# Default: .co/logs/{name}.log
agent = Agent("bot")  # Logs to .co/logs/bot.log

# Current directory: bot.log
agent = Agent("bot", log=True)

# Disable file logging (console only)
agent = Agent("bot", log=False)

# Custom path
agent = Agent("bot", log="logs/my-agent.log")
```

### Environment Override

```bash
# All agents log to same file
export CONNECTONION_LOG=/var/logs/all-agents.log
```

### Debug with @xray

See what your agent is thinking inside tool execution:

```python
from connectonion.decorators import xray

@xray
def search(query: str) -> str:
    """Search for information."""

    # Access agent context!
    print(f"User asked: {xray.task}")
    print(f"Iteration: {xray.iteration}")
    print(f"Previous tools: {xray.previous_tools}")

    return f"Results for {query}"

agent = Agent("bot", tools=[search])
agent.input("Find Python docs")

# Automatically prints Rich table with full context
```

The `@xray` decorator provides:
- `xray.agent` - The Agent instance
- `xray.task` - Original user request
- `xray.messages` - Full conversation history
- `xray.iteration` - Current iteration number
- `xray.previous_tools` - Tools called before this one

See [xray.md](xray.md) for complete debugging guide and [debug.md](debug.md) for more options.

---

## Trust & Security

Add verification before risky tools execute:

### Trust Levels

```python
agent = Agent(
    "bot",
    tools=[delete_database],
    trust="tested"  # Requires manual approval before execution
)
```

**Trust levels:**
- `"open"` - No verification (default)
- `"tested"` - Manual approval required
- `"strict"` - Both manual approval + verification logic

### Trust Policies (Natural Language)

```python
agent = Agent(
    "bot",
    tools=[deploy_code],
    trust="policies/production.md"  # Checks against policy file
)
```

### Custom Trust Agent

```python
# Create a verifier agent
verifier = Agent("security", tools=[scan_code, check_safety])

# Use it to verify tools
agent = Agent(
    "bot",
    tools=[risky_tool],
    trust=verifier  # Custom verification logic
)
```

See [trust.md](trust.md) for complete security guide.

---

## Common Patterns

### Quick One-Off Task

```python
def quick_task(prompt: str, tools: list) -> str:
    """Execute a one-off task without conversation state."""
    agent = Agent("temp", tools=tools, log=False)
    return agent.input(prompt)

result = quick_task("Search for Python", [search])
```

### Stateful Chatbot

```python
class ChatBot:
    def __init__(self):
        self.agent = Agent(
            "chatbot",
            tools=[search, calculate],
            system_prompt="You are friendly and helpful"
        )

    def chat(self, message: str) -> str:
        return self.agent.input(message)

    def reset(self):
        self.agent.reset_conversation()

bot = ChatBot()
bot.chat("Hello!")
bot.chat("What's 2+2?")  # Remembers context
bot.reset()              # Fresh start
```

### Agent Factory

```python
def create_analyst(name: str, tools: list) -> Agent:
    """Create analysts with shared configuration."""
    return Agent(
        name=name,
        tools=tools,
        system_prompt=Path("prompts/analyst.md"),
        model="claude-3-5-sonnet-20241022",
        max_iterations=15,
        log=f"logs/{name}.log"
    )

sales_agent = create_analyst("sales", [sql_query, chart])
finance_agent = create_analyst("finance", [sql_query, forecast])
```

### Multi-Agent Workflow

```python
# Create specialized agents
researcher = Agent("researcher", tools=[search, scrape])
writer = Agent("writer", tools=[format_text, save_file])
reviewer = Agent("reviewer", tools=[check_grammar, fact_check])

# Orchestrate workflow
def content_pipeline(topic: str):
    research = researcher.input(f"Research {topic}")
    draft = writer.input(f"Write article: {research}")
    final = reviewer.input(f"Review and improve: {draft}")
    return final

result = content_pipeline("AI trends 2025")
```

### Browser Automation

```python
class Browser:
    """Stateful browser automation."""
    def __init__(self):
        self.page = None

    def start(self) -> str:
        """Start browser."""
        # Browser initialization
        return "Browser started"

    def navigate(self, url: str) -> str:
        """Navigate to URL."""
        self.page.goto(url)
        return f"Navigated to {url}"

    def screenshot(self, filename: str) -> str:
        """Take screenshot."""
        self.page.screenshot(path=filename)
        return f"Saved {filename}"

browser = Browser()
agent = Agent(
    "web_bot",
    tools=browser,
    max_iterations=20  # Browser automation needs more iterations
)

agent.input("Go to wikipedia.org, search for 'Python', take screenshot")
```

---

## Testing Your Agents

### Mock the LLM

```python
from unittest.mock import Mock
from connectonion import Agent
from connectonion.llm import LLMResponse

def test_agent():
    agent = Agent("test", tools=[calculate])

    # Mock LLM response
    agent.llm.complete = Mock(return_value=LLMResponse(
        content="The answer is 4",
        tool_calls=[],
        raw_response=None
    ))

    result = agent.input("What is 2+2?")
    assert result == "The answer is 4"
```

### Test Tool Execution

```python
def test_tool_execution():
    agent = Agent("test", tools=[calculator])

    result = agent.execute_tool("calculator", {"expression": "2+2"})

    assert result["status"] == "success"
    assert result["result"] == "4"
```

### Integration Tests

```python
import pytest

@pytest.mark.real_api
def test_real_agent():
    """Requires OPENAI_API_KEY in environment."""
    agent = Agent("test", tools=[search], model="gpt-4o-mini")
    result = agent.input("Search for Python")
    assert "Python" in result

# Run tests:
# pytest -m "not real_api"  # Skip real API tests
# pytest -m real_api         # Only integration tests
```

---

## Architecture & Internals

### How Agent Works Internally

```
agent.input("prompt")
    ↓
1. Initialize/Continue Session
    - First call: Create new session
    - Subsequent: Continue existing session
    ↓
2. Add User Message to History
    ↓
3. Iteration Loop (up to max_iterations):
   ├─ Call LLM with tools and messages
   ├─ If no tool calls → Return final response
   ├─ Execute all tool calls in sequence
   ├─ Add tool results to messages
   └─ Repeat
    ↓
4. Return Final Response or "Maximum iterations reached"
```

### File References

If you want to explore the source code:

- **Agent core**: `connectonion/agent.py:32` (Agent class definition)
- **Tool execution**: `connectonion/tool_executor.py:24` (Tool execution logic)
- **LLM interface**: `connectonion/llm.py:41` (LLM abstraction)
- **Tool factory**: `connectonion/tool_factory.py:26` (Function → Tool conversion)
- **Console**: `connectonion/console.py:15` (Logging)

### Error Handling Philosophy

Tool errors are **returned to the LLM** as messages, allowing it to retry or adapt:

```python
def risky_tool(data: str) -> str:
    if not data:
        raise ValueError("data required")
    return f"Processed {data}"

agent = Agent("bot", tools=[risky_tool])

# If tool fails:
# 1. Error captured
# 2. Error message sent to LLM
# 3. LLM can retry with different arguments or choose different approach
agent.input("Use risky_tool")
```

This makes agents resilient to errors.

### Session State Structure

```python
{
    'messages': [
        {'role': 'system', 'content': '...'},
        {'role': 'user', 'content': '...'},
        {'role': 'assistant', 'content': '...', 'tool_calls': [...]},
        {'role': 'tool', 'content': '...', 'tool_call_id': '...'},
    ],
    'trace': [
        {
            'type': 'user_input',
            'prompt': '...',
            'timestamp': 1234567890.123,
            'turn': 1
        },
        {
            'type': 'llm_call',
            'model': 'gpt-4o-mini',
            'duration_ms': 234,
            'tool_calls_count': 2,
            'iteration': 1
        },
        {
            'type': 'tool_execution',
            'tool_name': 'search',
            'arguments': {'query': '...'},
            'result': '...',
            'status': 'success',
            'timing': 1.23,
            'iteration': 1
        }
    ],
    'turn': 1,
    'iteration': 1,
    'user_prompt': '...'
}
```

---

## Learn More

### Essential Documentation
- **[getting-started.md](getting-started.md)** - Installation and first steps
- **[tools.md](tools.md)** - How to create powerful tools
- **[models.md](models.md)** - All supported LLM providers

### Advanced Features
- **[xray.md](xray.md)** - Debug and inspect agent behavior
- **[trust.md](trust.md)** - Security and tool verification
- **[max_iterations_guide.md](max_iterations_guide.md)** - Detailed iteration control
- **[log.md](log.md)** - Logging configuration
- **[debug.md](debug.md)** - Debugging strategies

### Philosophy & Examples
- **[tutorials/001-ai-agent-is-just-prompt-plus-function.md](tutorials/001-ai-agent-is-just-prompt-plus-function.md)** - The core insight
- **[examples.md](examples.md)** - Real-world code examples
- **[api.md](api.md)** - Complete API reference

---

## Philosophy

**"Keep simple things simple, make complicated things possible"**

### Simple Case
```python
agent = Agent("bot", tools=[search])
agent.input("Find Python docs")
```

### Complex Case
```python
trust_agent = Agent("verifier", tools=[scan_code])

agent = Agent(
    name="production",
    llm=custom_llm,
    tools=[deploy, rollback, monitor],
    system_prompt=Path("prompts/ops.md"),
    max_iterations=30,
    trust=trust_agent,
    log="/var/log/agents/production.log"
)

result = agent.input("Deploy v2.0 to production", max_iterations=40)
```

**Both are valid.** Start simple, add complexity only when needed.

---

**ConnectOnion: AI Agent = Prompt + Function**

That's it. That's the framework. Now go build something useful.
