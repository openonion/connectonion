# tool_approval

Web-based approval for dangerous tools via WebSocket. Requires user confirmation before executing tools that can modify files or run commands.

## Quick Start

```python
from connectonion import Agent, bash
from connectonion.useful_plugins import tool_approval

agent = Agent("assistant", tools=[bash], plugins=[tool_approval])
agent.io = my_websocket_io  # Required for web mode

agent.input("Install dependencies")
# → Client receives: {"type": "approval_needed", "tool": "bash", "arguments": {"command": "npm install"}}
# → Client responds: {"approved": true, "scope": "session"}
# ✓ bash approved (session)
```

## How It Works

1. Before each tool executes, check if it's dangerous
2. If dangerous, send `approval_needed` event via WebSocket
3. Wait for client response (blocks until received)
4. If approved: execute tool, optionally remember for session
5. If rejected: stop batch, return feedback to LLM

## Tool Classification

### Safe Tools (No Approval)

Read-only operations that never modify state:

```
read, read_file, glob, grep, search
list_files, get_file_info, task, load_guide
enter_plan_mode, exit_plan_mode, write_plan
task_output, ask_user
```

### Dangerous Tools (Require Approval)

Operations that can modify files or have side effects:

```
bash, shell, run, run_in_dir
write, edit, multi_edit
run_background, kill_task
send_email, post, delete, remove
```

## Client Protocol

### Receive from server

```json
{
  "type": "approval_needed",
  "tool": "bash",
  "arguments": {"command": "npm install"}
}
```

### Send response

```json
// Approve for this session (no re-prompting)
{"approved": true, "scope": "session"}

// Approve once only
{"approved": true, "scope": "once"}

// Reject with feedback
{"approved": false, "feedback": "Use yarn instead"}
```

## Approval Scopes

| Scope | Behavior |
|-------|----------|
| `once` | Approve this call only |
| `session` | Approve for rest of session (stored in memory) |

## Rejection Behavior

When user rejects a tool:

1. Raises `ValueError` with feedback message
2. Stops the entire tool batch (remaining tools skipped)
3. LLM receives the error and can adjust approach

```python
# Example error message
"User rejected tool 'bash'. Feedback: Use yarn instead"
```

## Terminal Logging

The plugin logs all approval decisions:

```
✓ bash approved (session)    # Approved with session scope
✓ edit approved (once)       # Approved for single use
⏭ bash (session-approved)    # Skipped (already approved)
✗ bash rejected: Use yarn    # Rejected with feedback
✗ bash - connection closed   # WebSocket closed
```

## Events

| Handler | Event | Purpose |
|---------|-------|---------|
| `check_approval` | `before_each_tool` | Check approval and prompt client |

## Session Data

```python
# Approval state stored in session
agent.current_session['approval'] = {
    'approved_tools': {
        'bash': 'session',   # Approved for session
        'write': 'session'   # Approved for session
    }
}
```

## Non-Web Mode

When `agent.io` is None (not web mode), all tools execute without approval. This is the default behavior for CLI usage.

## Unknown Tools

Tools not in SAFE_TOOLS or DANGEROUS_TOOLS are treated as safe and execute without approval.

## See Also

- [shell_approval](shell_approval.md) - Terminal-based approval for shell commands
- [Events](../concepts/events.md) - Available event hooks
- [Plugins](../concepts/plugins.md) - Plugin system overview
