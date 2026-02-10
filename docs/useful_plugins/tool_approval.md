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

## Lifecycle

```
User sends prompt
    ↓
Agent calls LLM
    ↓
LLM returns tool_calls batch: [bash("npm install"), write("config.json"), bash("npm build")]
    ↓
tool_executor iterates sequentially:
    ↓
┌─ Tool #1: bash("npm install")
│   before_each_tool fires → check_approval()
│   → Is it safe? No (bash is DANGEROUS)
│   → Already approved for session? No
│   → Send to client:
│       {
│         "type": "approval_needed",
│         "tool": "bash",
│         "arguments": {"command": "npm install"},
│         "batch_remaining": [
│           {"tool": "write", "arguments": "{...}"},
│           {"tool": "bash", "arguments": "{\"command\": \"npm build\"}"}
│         ]
│       }
│   → BLOCK — wait for client response
│   ↓
│   Client responds: {"approved": true, "scope": "session"}
│   → Execute bash("npm install")
│   → Save "bash" as session-approved
│
├─ Tool #2: write("config.json")
│   before_each_tool fires → check_approval()
│   → Is it safe? No (write is DANGEROUS)
│   → Send approval_needed (batch_remaining: [bash(...)])
│   → Client responds: {"approved": false, "mode": "reject_soft"}
│   → Skip this tool, continue to next
│
├─ Tool #3: bash("npm build")
│   before_each_tool fires → check_approval()
│   → bash is session-approved → skip approval, execute immediately
│
└─ Done. Return results to LLM.
```

## Rejection Modes

When the client rejects a tool, the `mode` field determines what happens next:

### reject_soft (Skip)

Skip this tool, agent loop continues. The LLM receives a hint to ask the user what they prefer.

```json
{"approved": false, "mode": "reject_soft", "feedback": "Don't write that file"}
```

- Current tool is skipped (raises ValueError)
- Next tool in the batch proceeds normally
- LLM gets: `"User rejected tool 'write'. Feedback: Don't write that file\n\n[System reminder: Ask the user...]"`

### reject_hard (Stop)

Skip this tool AND all remaining tools in the batch. The agent loop stops and waits for new user input.

```json
{"approved": false, "mode": "reject_hard", "feedback": "Wrong approach entirely"}
```

- Current tool is skipped (raises ValueError)
- `tool_rejected_hard` flag is set in session
- All remaining tools in the batch are auto-rejected
- Agent loop stops — LLM does NOT get another turn
- User must send a new message to continue

Default mode when `mode` is not provided: `reject_hard`.

## Batch Context

When a tool needs approval, the server includes `batch_remaining` — a list of tools that will execute after the current one. This gives the client an overview to make informed decisions.

```json
{
  "type": "approval_needed",
  "tool": "bash",
  "arguments": {"command": "npm install"},
  "batch_remaining": [
    {"tool": "write", "arguments": "{\"file_path\": \"config.json\", ...}"},
    {"tool": "bash", "arguments": "{\"command\": \"npm build\"}"}
  ]
}
```

`batch_remaining` is only present when there are more tools after the current one. For the last tool in a batch (or a single-tool call), it is omitted.

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

### Unknown Tools

Tools not in either list are treated as safe (no approval needed).

## Client Protocol

### Server sends

```json
{
  "type": "approval_needed",
  "tool": "bash",
  "arguments": {"command": "npm install"},
  "batch_remaining": [{"tool": "write", "arguments": "..."}]
}
```

### Client responds

```json
{"approved": true, "scope": "once"}
{"approved": true, "scope": "session"}
{"approved": false, "mode": "reject_soft", "feedback": "Use yarn instead"}
{"approved": false, "mode": "reject_hard", "feedback": "Wrong approach"}
```

## Approval Scopes

| Scope | Behavior |
|-------|----------|
| `once` | Approve this call only |
| `session` | Approve for rest of session (stored in memory) |

## Terminal Logging

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
        'bash': 'session',
        'write': 'session'
    }
}

# Set by reject_hard — remaining tools in batch see this and auto-reject
agent.current_session['tool_rejected_hard'] = "User rejected tool 'bash'."
```

## Non-Web Mode

When `agent.io` is None (not web mode), all tools execute without approval. This is the default behavior for CLI usage.

## See Also

- [shell_approval](shell_approval.md) - Terminal-based approval for shell commands
- [Events](../concepts/events.md) - Available event hooks
- [Plugins](../concepts/plugins.md) - Plugin system overview
