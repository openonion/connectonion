# Logging

Save agent activity to files with `log` parameter.

## Quick Start

```python
# No logging (default)
agent = Agent("assistant")

# Log to assistant.log
agent = Agent("assistant", log=True)

# Log to custom file
agent = Agent("assistant", log="debug.log")
```

## Log Format

```
[2025-09-25 10:32:14.123] INPUT: Generate a Python function
[2025-09-25 10:32:14.127] LLM_REQUEST: model=gpt-4 messages=2
[2025-09-25 10:32:15.235] LLM_RESPONSE: duration=1.1s
[2025-09-25 10:32:15.238] TOOL_CALL: generate_code(language="python")
[2025-09-25 10:32:15.286] TOOL_RESULT: success (0.05s)
[2025-09-25 10:32:16.458] RESULT: Task completed
[2025-09-25 10:32:16.461] DURATION: 2.3s
```

## View Logs

```bash
# Watch in real-time
tail -f assistant.log

# Search for errors
grep ERROR assistant.log

# See all tool calls
grep TOOL assistant.log
```

## Environment Variable

```bash
# Set log file via environment
CONNECTONION_LOG=debug.log python agent.py
```

## Auto Rotation

Logs rotate automatically when > 10MB:
```
assistant.log           # Current
assistant_20250925.log  # Rotated
```

## Git Ignore

Add to `.gitignore`:
```
*.log
```

That's it. Use `log=True` when you need persistent records.