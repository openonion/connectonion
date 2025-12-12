# Debug with @xray

See what your AI agent is thinking.

## Quick Start

```python
from connectonion import xray

@xray
def my_tool(text: str) -> str:
    """Process some text."""
    
    # Now you can see inside the agent's mind!
    print(xray.agent.name)    # "my_assistant"
    print(xray.task)          # "Process this document"
    print(xray.iteration)     # 1, 2, 3...
    
    return f"Processed: {text}"
```

That's it! Add `@xray` to any tool to unlock debugging superpowers.

## What You Can Access

Inside any `@xray` decorated function:

```python
xray.agent         # The Agent instance calling this tool
xray.task          # Original request from user  
xray.messages      # Full conversation history
xray.iteration     # Which round of tool calls (1-10)
xray.previous_tools # Tools called before this one
```

## Real Example

```python
@xray
def search_database(query: str) -> str:
    """Search our database."""
    
    # See what led to this search
    print(f"User asked: {xray.task}")
    print(f"This is iteration {xray.iteration}")
    
    if xray.previous_tools:
        print(f"Already tried: {xray.previous_tools}")
    
    # Adjust behavior based on context
    if xray.iteration > 2:
        return "No results found, please refine your search"
    
    return f"Found 5 results for '{query}'"
```

## Visual Execution Trace

See the complete flow of your agent's work from inside a tool:

```python
@xray
def analyze_data(text: str) -> str:
    """Analyze data and show execution trace."""
    
    # Show what happened so far
    xray.trace()
    
    return "Analysis complete"
```

**Output:**
```
Task: "Find Python tutorials and summarize them"

[1] • 89ms  search_database(query="Python tutorials")
      IN  → query: "Python tutorials"
      OUT ← "Found 5 results for 'Python tutorials'"

[2] • 234ms summarize_text(text="Found 5 results...", max_words=50)
      IN  → text: "Found 5 results for 'Python tutorials'"
      IN  → max_words: 50
      OUT ← "5 Python tutorials found covering basics to advanced topics"

Total: 323ms • 2 steps • 1 iterations
```

## Debug in Your IDE

Set a breakpoint and explore:

```python
@xray
def analyze_sentiment(text: str) -> str:
    # 🎯 Set breakpoint on next line
    sentiment = "positive"  # When stopped here in debugger:
                           # >>> xray
                           # <XrayContext active>
                           #   agent: 'my_bot'
                           #   task: 'How do people feel about Python?'
                           # >>> xray.messages
                           # [{'role': 'user', 'content': '...'}, ...]
    
    return sentiment
```

## Practical Use Cases

### 1. Understand Why a Tool Was Called
```python
@xray
def emergency_shutdown():
    """Shutdown the system."""
    
    # Check why this drastic action was requested
    print(f"Shutdown requested because: {xray.task}")
    print(f"After trying: {xray.previous_tools}")
    
    # Maybe don't shutdown if it's the first try
    if xray.iteration == 1:
        return "Try restarting first"
    
    return "System shutdown complete"
```

### 2. Adaptive Tool Behavior
```python
@xray
def fetch_data(source: str) -> str:
    """Fetch data from a source."""
    
    # Use cache on repeated calls
    if "fetch_data" in xray.previous_tools:
        return "Using cached data"
    
    # Fresh fetch on first call
    return f"Fresh data from {source}"
```

### 3. Debug Complex Flows
```python
@xray
def process_order(order_id: str) -> str:
    """Process an order."""
    
    # See the full context when debugging
    if xray.agent:
        print(f"Processing for agent: {xray.agent.name}")
        print(f"Original request: {xray.task}")
        print(f"Conversation length: {len(xray.messages)}")
    
    return f"Order {order_id} processed"
```

## Tips

1. **Development Only** - Remove @xray in production for best performance
2. **Combine with IDE** - Set breakpoints for interactive debugging  
3. **Use trace()** - Call `xray.trace(agent)` after runs to see full flow
4. **Check context** - Always verify `xray.agent` exists before using

## Common Patterns

### Logging What Matters
```python
@xray
def important_action(data: str) -> str:
    # Log with context
    if xray.agent:
        logger.info(f"Agent {xray.agent.name} performing action")
        logger.info(f"Original task: {xray.task}")
        logger.info(f"Iteration: {xray.iteration}")
    
    return "Action completed"
```

### Conditional Logic
```python
@xray
def smart_search(query: str) -> str:
    # Different strategies based on context
    if xray.iteration > 1:
        # Broaden search on retry
        query = f"{query} OR related"
    
    if "analyze" in xray.previous_tools:
        # We already analyzed, search differently
        query = f"summary of {query}"
    
    return f"Results for: {query}"
```

## Next Steps

- Try [@replay](replay.md) for re-running tools with different parameters
- See [Examples](examples.md) for complete debugging workflows
- Check [API Reference](api.md) for all xray properties
