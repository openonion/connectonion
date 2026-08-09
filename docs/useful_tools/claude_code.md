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

## Direct use

```python
import json

from connectonion import claude_code

first = json.loads(claude_code(
    "Find the failing test",
    cwd="./my-project",
    permission_mode="plan",
))

second = json.loads(claude_code(
    "Now implement the fix",
    session_id=first["session_id"],
    cwd="./my-project",
    permission_mode="acceptEdits",
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

`permission_mode="default"` is the safe default and maps to Claude Code's
current `manual` CLI spelling. Supported explicit modes are `manual`,
`acceptEdits`, `plan`, `auto`, `dontAsk`, and `bypassPermissions`.

`bypassPermissions` is never selected automatically. It disables Claude Code's
permission protection and should only be used in an isolated environment.

The tool does not use Claude Code's `--bare` mode by default. This preserves the
user's normal Claude Code authentication and project instructions such as
`CLAUDE.md`.

## Installation and testing

The `claude` executable must be on `PATH`. For a custom installation or test
wrapper, set `CLAUDE_CODE_CMD` to a quoted command string.

On Windows, the adapter rejects `.cmd` and `.bat` launchers because Windows may
reparse their arguments through `cmd.exe`, which is unsafe for arbitrary prompt
text. Use Claude Code's native executable, or point `CLAUDE_CODE_CMD` at a
native `node.exe` followed by the CLI script path. Timed-out runs terminate the
launched process tree rather than leaving tool subprocesses running.

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
