# Claude Code

Run or resume the installed Claude Code CLI as a function tool.

```python
from connectonion import Agent, claude_code

agent = Agent("lead", tools=[claude_code])
agent.input("Ask Claude Code to review this repository")
```

The adapter uses Claude Code's headless JSON interface. It does not add an SDK
dependency, and provider-specific parsing stays outside the ConnectOnion Agent
loop. It accepts both the documented single result object and Claude Code
versions that wrap the result as the final item of a JSON event array.

The default `claude_code` function tool always starts Claude Code in its manual
permission mode. Permission policy is deliberately not a tool argument, so the
model cannot weaken it through a prompt or tool call.

## Direct use

```python
import json

from connectonion import ClaudeCode

claude = ClaudeCode(permission_mode="plan")

first = json.loads(claude.claude_code(
    "Find the failing test",
    cwd="./my-project",
))

editor = ClaudeCode(permission_mode="acceptEdits")
second = json.loads(editor.claude_code(
    "Now implement the fix",
    session_id=first["session_id"],
    cwd="./my-project",
))
```

Every call returns the same required fields:

```json
{
  "provider": "claude_code",
  "session_id": "...",
  "resumed": false,
  "status": "completed",
  "result": "...",
  "error": "",
  "exit_code": 0,
  "usage": {},
  "total_cost_usd": null
}
```

Missing binaries, invalid arguments, timeouts, authentication errors, malformed
output, and non-zero exits use the same envelope with `status` set to `error` or
`timeout`.

## Permissions

The public `claude_code(...)` function always maps to Claude Code's current
`manual` CLI mode. For an advanced mode, the operator binds policy before the
tool reaches the Agent:

```python
from connectonion import Agent, ClaudeCode

claude = ClaudeCode(permission_mode="acceptEdits")
agent = Agent("lead", tools=[claude])
```

The generated `claude_code` schema still contains only task, session, working
directory, model, and timeout fields. Supported constructor modes are
`default`, `manual`, `acceptEdits`, `plan`, `auto`, `dontAsk`, and
`bypassPermissions`.

`bypassPermissions` disables Claude Code's permission protection. Bind it only
in operator-written code running inside an isolated environment; a model can
never select it through the tool schema.

The tool does not use Claude Code's `--bare` mode by default. This preserves the
user's normal Claude Code authentication and project instructions such as
`CLAUDE.md`.

## Installation and testing

The `claude` executable must be on `PATH`. For a custom installation or test
wrapper, set `CLAUDE_CODE_CMD` to a quoted command string.

On Windows, the adapter rejects `.cmd` and `.bat` launchers because Windows may
reparse their arguments through `cmd.exe`, which is unsafe for arbitrary prompt
text. Use Claude Code's native executable, or point `CLAUDE_CODE_CMD` at a
native `node.exe` followed by the CLI script path. Timed-out runs make a
best-effort attempt to terminate the launched Windows process tree or POSIX
process group. A descendant that deliberately detaches into another process
group is outside that guarantee; the adapter's own timeout return remains
bounded.

Unit tests mock the subprocess and do not need Claude Code. Real CLI checks are
opt-in:

```bash
pytest -m real_api tests/e2e/real_api/test_real_claude_code.py
```

## Difference from the Codex tool

The Codex adapter uses its app-server JSON-RPC protocol for live inner-step
events and per-action approval callbacks. Claude Code's adapter intentionally
uses one documented headless JSON subprocess per turn. It provides native
session resume and an explicit baseline permission mode, but does not claim live
approval-card streaming.
