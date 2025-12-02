# API Reference

## Agent

The main class for creating AI agents that can use tools.

### Constructor

```python
Agent(
    name: str,
    llm: Optional[LLM] = None,
    tools: Optional[List[Callable]] = None,
    system_prompt: Union[str, Path, None] = None,
    api_key: Optional[str] = None,
    model: str = "gpt-5-mini"
)
```

#### Parameters

- **name** (`str`): Unique identifier for the agent
- **llm** (`Optional[LLM]`): Custom LLM instance (defaults to OpenAILLM)
- **tools** (`Optional[List[Callable]]`): List of functions the agent can use
- **system_prompt** (`Union[str, Path, None]`): Agent's personality and behavior definition
  - `str`: Can be either a direct prompt text or a file path (auto-detected)
  - `Path`: Path object pointing to a prompt file
  - `None`: Uses default prompt
- **api_key** (`Optional[str]`): OpenAI API key (if not using custom LLM)
- **model** (`str`): Model name for OpenAI (default: "gpt-5-mini")
  - Available models: `gpt-5-nano`, `gpt-5-mini`, `gpt-5`

### System Prompt Options

The `system_prompt` parameter accepts multiple input types:

```python
# 1. Direct string
agent = Agent(name="bot", system_prompt="You are helpful")

# 2. File path as string (auto-detected if file exists)
agent = Agent(name="bot", system_prompt="prompts/assistant.md")

# 3. Path object (must point to existing file)
from pathlib import Path
agent = Agent(name="bot", system_prompt=Path("prompts/assistant.txt"))

# 4. None (uses default)
agent = Agent(name="bot")  # Default: "You are a helpful assistant..."
```

**File Loading Rules:**
- Any text file can be used (no extension restrictions)
- Files must be valid UTF-8 encoded text
- Empty files raise `ValueError`
- Non-existent Path objects raise `FileNotFoundError`
- Strings that don't exist as files are treated as literal prompts

### Methods

#### `input(prompt: str) -> str`

Provide input to the agent and get response.

```python
result = agent.input("Calculate 2 + 2")
```

#### `add_tool(tool: Callable) -> None`

Add a new tool to the agent.

```python
def new_tool(param: str) -> str:
    return f"Processed {param}"

agent.add_tool(new_tool)
```

#### `remove_tool(tool_name: str) -> None`

Remove a tool from the agent.

```python
agent.remove_tool("calculator")
```

#### `list_tools() -> List[str]`

Get list of available tool names.

```python
tools = agent.list_tools()
# ['calculator', 'search', 'get_time']
```

## Tools

### Function-Based Tools

Any Python function can be used as a tool:

```python
def my_tool(param: str, optional: int = 10) -> str:
    """Tool description from docstring."""
    return f"Result: {param} with {optional}"

agent = Agent("bot", tools=[my_tool])
```

**Requirements:**
- Must have a docstring (becomes tool description)
- Type hints recommended (improves schema generation)
- Return value should be serializable to string

### Tool Conversion

The `create_tool_from_function` utility converts functions to tools:

```python
from connectonion import create_tool_from_function

def simple_function(x: int) -> int:
    """Double a number."""
    return x * 2

tool = create_tool_from_function(simple_function)
# tool now has: .name, .description, .run(), .to_function_schema()
```

## Logging

Automatic activity logging for agents. Three output destinations:
- **Console**: Rich-formatted terminal output
- **Plain text**: `.co/logs/{name}.log`
- **Session YAML**: `.co/sessions/{name}_{timestamp}.yaml`

### Configuration

Control logging via `quiet` and `log` parameters:

```python
# Default: everything on (console + logs + sessions)
agent = Agent("assistant")

# Quiet mode: suppress console, keep sessions for eval
agent = Agent("assistant", quiet=True)

# Disable all file logging (console only)
agent = Agent("assistant", log=False)

# Custom log file path
agent = Agent("assistant", log="my_logs/custom.log")
```

### Logging Modes

| quiet | log | Console | Plain Text | Sessions | Use Case |
|-------|-----|---------|------------|----------|----------|
| False | True/None | ✓ | ✓ | ✓ | Development (default) |
| True | True/None | ✗ | ✗ | ✓ | Eval/testing |
| False | False | ✓ | ✗ | ✗ | Benchmarking |
| False | "path" | ✓ | custom | ✓ | Custom log path |

### Log Format

Plain text logs include:
- Timestamp
- User input
- LLM calls with timing, tokens, cost
- Tool executions with parameters and results
- Final agent responses

Example log output:
```
[10:30:15] INPUT: Calculate 2 + 2
[10:30:15] -> LLM Request (gpt-4o-mini) • 2 msgs • 1 tools
[10:30:16] <- LLM Response (234ms) • 1 tools • 156 tokens • $0.0001
[10:30:16] -> Tool: calculator({"expression": "2+2"})
[10:30:16] <- Result (1ms): 4
[10:30:16] [OK] Complete (1.2s)
```

### Session YAML Format

Sessions are saved for replay and eval:

```yaml
name: assistant
timestamp: 2024-12-02 10:30:15

turns:
  - input: "Calculate 2 + 2"
    model: "gpt-4o-mini"
    duration_ms: 1200
    tokens: 156
    cost: 0.0001
    tools_called: [calculator]
    result: "The answer is 4"
    messages: '[{"role":"system",...}]'
```

## LLM

Abstract base class for language models. ConnectOnion supports multiple LLM providers through a unified interface.

### Model Routing

The `create_llm()` factory function routes models to the appropriate provider:

```python
from connectonion.llm import create_llm

# OpenAI models
llm = create_llm("gpt-4o-mini")      # → OpenAILLM
llm = create_llm("o4-mini")          # → OpenAILLM

# Anthropic models
llm = create_llm("claude-3-5-sonnet") # → AnthropicLLM

# Google Gemini models
llm = create_llm("gemini-2.5-flash")  # → GeminiLLM

# ConnectOnion managed keys (co/ prefix)
llm = create_llm("co/gpt-4o-mini")    # → OpenOnionLLM
llm = create_llm("co/gemini-2.5-flash") # → OpenOnionLLM
```

### co/ Models (Managed Keys)

Models prefixed with `co/` use ConnectOnion's managed API keys through the OpenOnion proxy:

```python
from connectonion import Agent

# Uses OpenOnion managed keys - no API key needed
agent = Agent(name="bot", model="co/gemini-2.5-flash")
```

**How it works:**
1. Client detects `co/` prefix → routes to `OpenOnionLLM`
2. Prefix is stripped before sending to server
3. Server routes to appropriate provider (OpenAI, Anthropic, Gemini)
4. Response returned in OpenAI-compatible format

**Available co/ models:**
- `co/gpt-4o-mini`, `co/gpt-4o`, `co/gpt-5`, `co/gpt-5-mini`, `co/gpt-5-nano`, `co/o4-mini`
- `co/gemini-2.5-pro`, `co/gemini-2.5-flash`, `co/gemini-2.5-flash-lite`, `co/gemini-2.0-flash`

**Environment variable:** `OPENONION_API_KEY` (auto-loaded from `.env`)

### OpenAILLM

OpenAI API implementation.

```python
from connectonion.llm import OpenAILLM

llm = OpenAILLM(
    api_key="your-key",  # or OPENAI_API_KEY env var
    model="gpt-4o-mini",
    temperature=0.7
)

agent = Agent("bot", llm=llm)
```

### AnthropicLLM

Anthropic Claude API implementation.

```python
from connectonion.llm import AnthropicLLM

llm = AnthropicLLM(
    api_key="your-key",  # or ANTHROPIC_API_KEY env var
    model="claude-3-5-sonnet-20241022"
)

agent = Agent("bot", llm=llm)
```

### GeminiLLM

Google Gemini API implementation (uses OpenAI-compatible endpoint).

```python
from connectonion.llm import GeminiLLM

llm = GeminiLLM(
    api_key="your-key",  # or GEMINI_API_KEY env var
    model="gemini-2.5-flash"
)

agent = Agent("bot", llm=llm)
```

### OpenOnionLLM

ConnectOnion managed keys implementation.

```python
from connectonion.llm import OpenOnionLLM

llm = OpenOnionLLM(
    api_key="your-token",  # or OPENONION_API_KEY env var
    model="co/gemini-2.5-flash"
)

agent = Agent("bot", llm=llm)
```

**Base URLs:**
- Production: `https://oo.openonion.ai/v1`
- Development: `http://localhost:8000/v1` (when `ENVIRONMENT=development`)

## Prompts Module

Utilities for loading system prompts.

### `load_system_prompt(prompt: Union[str, Path, None]) -> str`

Load system prompt from various sources.

```python
from connectonion.prompts import load_system_prompt

# From string
prompt = load_system_prompt("You are helpful")

# From file
prompt = load_system_prompt("prompts/assistant.md")

# From Path
from pathlib import Path
prompt = load_system_prompt(Path("prompts/assistant.txt"))

# Default
prompt = load_system_prompt(None)
```

**Raises:**
- `FileNotFoundError`: If Path object points to non-existent file
- `ValueError`: If file is empty or not valid UTF-8
- `TypeError`: If invalid type provided

## Decorators

### `@xray`

Enable detailed execution tracing.

```python
from connectonion import xray

@xray
def my_agent_function():
    agent = Agent("tracer")
    return agent.input("task")

# After execution:
xray.trace()  # Shows detailed execution flow
```

### `@replay`

Record and replay agent interactions.

```python
from connectonion import replay

@replay
def workflow():
    agent = Agent("bot")
    return agent.input("task")

# Replay the recorded interaction
replay.last()
```

## Examples

### Basic Agent

```python
from connectonion import Agent

# Simple calculator agent
def calculate(expression: str) -> str:
    """Evaluate mathematical expressions."""
    return str(eval(expression))

agent = Agent("calculator", tools=[calculate])
result = agent.input("What is 15 * 4?")
```

### Agent with Custom Prompt File

```python
# prompts/expert.md
"""
You are an expert Python developer with 10 years of experience.
Focus on clean code, best practices, and performance.
"""

# main.py
agent = Agent(
    name="python_expert",
    system_prompt="prompts/expert.md",
    tools=[code_review, suggest_improvement]
)
```

### Multi-Tool Agent

```python
def search(query: str) -> str:
    """Search the web."""
    # Implementation
    
def calculate(expr: str) -> str:
    """Do math."""
    # Implementation
    
def get_time() -> str:
    """Get current time."""
    # Implementation

agent = Agent(
    name="assistant",
    system_prompt="You are a helpful research assistant.",
    tools=[search, calculate, get_time]
)

# Agent can use multiple tools in one request
result = agent.input("Search for Python tutorials, calculate 42*17, and tell me the time")
```