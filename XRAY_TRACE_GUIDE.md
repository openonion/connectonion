# xray.trace() Guide

## Overview

`xray.trace()` is a powerful debugging tool that displays a visual trace of tool execution flow in ConnectOnion agents. It shows the complete sequence of tool calls with inputs, outputs, and execution timing in a clear, terminal-friendly format.

## Key Features

- **Visual execution flow**: See all tool calls in sequence with timing
- **Smart truncation**: Long strings, images, and DataFrames are intelligently abbreviated
- **Error tracking**: Failed tool calls are clearly marked with error details
- **Performance insights**: Execution time for each tool and total runtime
- **Flexible usage**: Works both during and after agent execution

## Installation

```python
from connectonion import Agent
from connectonion.decorators import xray
```

## Usage Examples

### 1. Basic Usage - Trace After Execution

```python
# Create and run an agent
agent = Agent("my_agent", tools=[analyze_text, generate_summary])
result = agent.run("Analyze this text and summarize it")

# View the execution trace
xray.trace(agent)
```

Output:
```
Task: "Analyze this text and summarize it"

[1] • 45ms  analyze_text(text="Analyze this text and summarize it")
      IN  → text: "Analyze this text and summarize it"
      OUT ← {'word_count': 7, 'char_count': 34}

[2] • 23ms  generate_summary(text="Analyze this text and summarize it", max_words=10)
      IN  → text: "Analyze this text and summarize it"
      IN  → max_words: 10
      OUT ← "Text analysis and summary requested"

Total: 68ms • 2 steps • 1 iterations
```

### 2. Usage Within @xray Decorated Tools

```python
@xray
def debug_tool():
    """Tool that shows execution trace during runtime."""
    # Access trace from within tool execution
    xray.trace()
    return "Debug complete"
```

### 3. Handling Long Content

When dealing with large inputs/outputs, xray.trace() automatically truncates:

```python
# Long text input
long_text = "Lorem ipsum..." * 1000  # 15,000+ characters

# Trace output will show:
[1] • 89ms  analyze_document(text="Lorem ipsum dolor sit amet...")
      IN  → text: <string: 15,234 chars> "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia des..."
      OUT ← {sentiment: "neutral", word_count: 2539}
```

### 4. Error Handling

Errors are clearly marked in the trace:

```python
[3] • ERROR calculate_score(data={...}, model="advanced")
      IN  → data: {valid: 950, invalid: 50}
      IN  → model: "advanced"
      ERR ✗ ModelNotFoundError: Model 'advanced' not available
```

### 5. Special Data Types

xray.trace() handles various data types intelligently:

```python
# DataFrame
[1] • 2.3s  fetch_records(query="SELECT * FROM users", limit=10000)
      IN  → query: "SELECT * FROM users"
      IN  → limit: 10000
      OUT ← <DataFrame: 10,000 rows × 25 columns>

# Image
[2] • 340ms process_image(image=<...>, enhance=true)
      IN  → image: <Image: JPEG 1920x1080, 2.3MB>
      IN  → enhance: true
      OUT ← <Image: JPEG 1920x1080, 1.8MB, enhanced>

# Large dictionary
[3] • 15ms  analyze_data(config={...})
      IN  → config: {api_key: ..., endpoint: ..., timeout: ..., ... (7 more)}
      OUT ← {"status": "success", "processed": 1000}
```

## Visual Format Reference

### Status Indicators
- `•` - Successful execution
- `ERROR` - Failed execution
- `...` - Pending/in-progress

### Timing Display
- `0.03ms` - Sub-millisecond precision for fast operations
- `45ms` - Milliseconds for typical operations
- `2.3s` - Seconds for longer operations

### Data Flow
- `IN  →` - Input parameters
- `OUT ←` - Return values
- `ERR ✗` - Error messages

## Performance Considerations

- xray.trace() has minimal performance impact
- Timing data is collected during normal execution
- Formatting happens only when trace() is called
- No overhead when not using @xray decorator

## Integration with Agent History

xray.trace() seamlessly integrates with ConnectOnion's History system:

```python
# Access last execution from history
agent.history.get_recent(1)  # Raw history data
xray.trace(agent)            # Visual trace of same execution
```

## Best Practices

1. **Use for debugging**: Enable @xray decorator during development
2. **Production considerations**: Remove @xray decorators in production for optimal performance
3. **Combine with replay**: Use alongside @replay for comprehensive debugging
4. **Custom tools**: Always use @xray on custom tools during development

## Troubleshooting

### "No tool execution history available"
- Ensure at least one tool has @xray decorator
- Check that agent.run() was called before trace()
- Pass agent instance if calling from outside tool context

### Timing shows 0ms
- Very fast operations may show as 0.00ms
- This is normal for simple operations
- Look at total time for aggregate performance

## Advanced Usage

### Custom Formatting

While xray.trace() handles most cases automatically, you can influence formatting by how you structure return values:

```python
@xray
def custom_tool():
    # Return structured data for better trace output
    return {
        "status": "success",
        "data": large_dataset,  # Will be truncated intelligently
        "summary": "Processed 1000 items"  # Will be shown in full
    }
```

### Debugging Multi-Agent Systems

```python
# Trace multiple agents
for agent in [agent1, agent2, agent3]:
    print(f"\n=== Agent: {agent.name} ===")
    xray.trace(agent)
```

## Related Features

- `@xray` decorator: Enable context access and tracing
- `@replay` decorator: Re-run tools with different parameters
- `agent.history`: Persistent behavior tracking
- `xray.agent`, `xray.task`, etc.: Access execution context

For more information, see the main ConnectOnion documentation.