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

## History

Automatic behavior tracking for agents.

### Properties

- **save_dir** (`Path`): Directory where history is saved
- **records** (`List[Dict]`): List of behavior records

### Methods

#### `summary() -> str`

Get a summary of agent behavior.

```python
print(agent.history.summary())
# Agent: assistant
# Total tasks: 5
# Tools used: calculator (3), search (2)
```

#### `clear() -> None`

Clear the behavior history.

```python
agent.history.clear()
```

## LLM

Abstract base class for language models.

### OpenAILLM

Default implementation using OpenAI's API.

```python
from connectonion.llm import OpenAILLM

llm = OpenAILLM(
    api_key="your-key",
    model="gpt-4",
    temperature=0.7
)

agent = Agent("bot", llm=llm)
```

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