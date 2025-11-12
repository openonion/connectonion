# ConnectOnion Framework - Complete Reference

## What is ConnectOnion?

ConnectOnion is a simple Python framework for creating AI agents that can use tools and track their behavior.

**Key Principles:**
- Keep simple things simple, make hard things possible
- Function-based tools are preferred over classes
- Activity logging to .co/logs/ (Python SDK only)
- Default settings work for most use cases

## Quick Start

```python
from connectonion import Agent

# Define tools as regular functions
def search(query: str) -> str:
    '''Search for information.'''
    return f"Found information about {query}"

# Create agent
agent = Agent(
    name="my_assistant",
    system_prompt="prompt.md",  # Always use markdown files for prompts
    tools=[search]
)

# Use agent
result = agent.input("Search for Python tutorials")
```

## Core Concepts

### Tools
Tools are just Python functions with type hints:
```python
def my_tool(param: str, optional: int = 10) -> str:
    '''This docstring becomes the tool description.'''
    return f"Result: {param}"
```

### System Prompts
Always use markdown files for system prompts:
```python
agent = Agent(
    name="assistant",
    system_prompt="prompt.md",  # Best practice
    tools=[...]
)
```

### max_iterations
Controls how many tool calls the agent can make:
- Simple tasks: 3-5 iterations
- Standard workflows: 10-15 iterations
- Complex analysis: 20-40 iterations

## Common Patterns

### Calculator Bot
```python
def calculate(expression: str) -> float:
    '''Perform math calculations.'''
    return eval(expression)  # Use safely

agent = Agent("calc", tools=[calculate], max_iterations=5)
```

### Research Assistant
```python
def web_search(query: str) -> str:
    '''Search the web.'''
    return f"Results for {query}"

def summarize(text: str) -> str:
    '''Summarize text.'''
    return f"Summary: {text[:100]}..."

agent = Agent("researcher", tools=[web_search, summarize], max_iterations=20)
```

## Debugging with @xray

See inside your agent's mind:
```python
from connectonion.decorators import xray

@xray
def my_tool(text: str) -> str:
    print(xray.agent.name)    # Agent name
    print(xray.task)          # Original request
    print(xray.iteration)     # Current iteration
    return "Done"
```

## Best Practices

1. **Use type hints** - Required for all tools
2. **Write clear docstrings** - They become tool descriptions
3. **Handle errors gracefully** - Return error messages, don't raise
4. **Use markdown for prompts** - Keep prompts separate from code
5. **Set appropriate iterations** - Match complexity of task

## Activity Logging

All agent activities are automatically logged to `.co/logs/{name}.log`:
```python
# Logs are written to .co/logs/ directory by default
# Each agent gets its own log file: .co/logs/{agent_name}.log

# You can customize logging:
agent = Agent("assistant", log=False)  # Disable logging
agent = Agent("assistant", log=True)   # Log to {name}.log in current dir
agent = Agent("assistant", log="custom.log")  # Custom log path
```

## Full Documentation

For complete documentation, visit: https://github.com/connectonion/connectonion

This embedded reference helps your agent understand and use ConnectOnion effectively.