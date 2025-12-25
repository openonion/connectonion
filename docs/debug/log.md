# Logging

ConnectOnion automatically logs agent activity to files for debugging and analysis.

## Quick Start

```python
# Default: logs to .co/logs/{name}.log + .co/evals/{name}_{timestamp}.yaml
agent = Agent("assistant")

# Quiet mode: no console output, but sessions still recorded
agent = Agent("assistant", quiet=True)

# Disable all logging
agent = Agent("assistant", log=False)

# Custom log file path
agent = Agent("assistant", log="debug.log")
```

## Logging Modes

| quiet | log | Console | Plain Text | Sessions | Use Case |
|-------|-----|---------|------------|----------|----------|
| False | True/None | ✓ | ✓ | ✓ | Development (default) |
| True | True/None | ✗ | ✗ | ✓ | Eval/testing |
| False | False | ✓ | ✗ | ✗ | Benchmarking |
| False | "path" | ✓ | custom | ✓ | Custom log path |

## Log Locations

```
.co/
├── logs/
│   └── assistant.log        # Plain text logs
└── sessions/
    └── assistant_2024-12-02_10-30-00.yaml  # Session YAML
```

## Plain Text Format (.co/logs/)

```
============================================================
Session started: 2024-12-02 10:32:14
============================================================

[10:32:14] INPUT: Generate a Python function...
[10:32:14] -> LLM Request (co/o4-mini) • 2 msgs • 3 tools
[10:32:15] <- LLM Response (1.1s) • 1 tools • 1.2k tokens • $0.0012
[10:32:15] -> Tool: generate_code({"language": "python"})
[10:32:15] <- Result (0.05s): def hello(): print("Hi")...
[10:32:16] [OK] Complete (2.3s)
```

## Session YAML Format (.co/evals/)

Sessions are saved as YAML for replay and eval:

```yaml
name: assistant
timestamp: 2024-12-02 10:32:14

turns:
  - input: "Generate a Python function"
    model: "co/o4-mini"
    duration_ms: 2300
    tokens: 1234
    cost: 0.0012
    tools_called: [generate_code]
    result: "Here's a Python function..."
    messages: '[{"role":"system",...}]'
```

Use cases:
- **Session replay**: Restore context from saved sessions
- **Regression testing**: Compare expected vs actual results
- **Development comparison**: See what changed after prompt edits

## View Logs

```bash
# Watch plain text logs in real-time
tail -f .co/logs/assistant.log

# Search for errors
grep ERROR .co/logs/assistant.log

# See all tool calls
grep "Tool:" .co/logs/assistant.log

# List sessions
ls -la .co/evals/
```

## Environment Variable

```bash
# Override log file via environment (highest priority)
CONNECTONION_LOG=debug.log python agent.py
```

## Git Ignore

Add to `.gitignore`:
```
.co/logs/
.co/evals/
*.log
```

## Parameters

- **`quiet`** (bool): Suppress console output. Sessions still recorded. Default: `False`
- **`log`** (bool|str|Path): Control file logging
  - `None`/`True`: Default `.co/logs/{name}.log`
  - `False`: Disable all logging
  - `"path/to/file.log"`: Custom log path
