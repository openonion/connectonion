# Claude Code

Run or resume the installed Claude Code CLI as a function tool.

```python
from connectonion import Agent, claude_code

agent = Agent("lead", tools=[claude_code])
agent.input("Ask Claude Code to review this repository")
```

The adapter uses Claude Code's documented headless `stream-json` interface. It
keeps one normal ConnectOnion tool call around the delegated turn while
forwarding Claude's inner tool starts and results through the Agent's live IO.
Provider-specific parsing stays outside the ConnectOnion Agent loop, and the
final return value remains one stable JSON envelope.

The default `claude_code` function tool always starts Claude Code in its manual
permission mode. Permission policy is deliberately not a tool argument, so the
model cannot weaken it through a prompt or tool call.

## Direct use

```python
import json

from connectonion import ClaudeCode

claude = ClaudeCode(permission_mode="plan", workspace="./my-project")

first = json.loads(claude.claude_code(
    "Find the failing test",
    cwd=".",
))

editor = ClaudeCode(permission_mode="acceptEdits", workspace="./my-project")
second = json.loads(editor.claude_code(
    "Now implement the fix",
    session_id=first["session_id"],
    cwd=".",
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

## Live tool activity

When the function receives its injected `agent` argument, every Claude Code
`tool_use` becomes an ordinary live ConnectOnion tool card such as
`Claude Code › Bash` or `Claude Code › Read`. The matching `tool_result`
completes or fails that same card. This works automatically in `co ai` web chat;
callers do not need a second protocol or a separate Claude UI.

The forwarded event also carries `provider=claude_code`, the Claude session ID,
and any parent tool-use ID. Current clients can render a flat card immediately;
future clients can use the parent ID for nested sub-agent presentation. Tool
arguments and results are bounded before they reach live IO, and common
credential-shaped argument keys are redacted. Provider-controlled IDs, names,
event counts, stream lines, and active tool state are bounded as well.

Only tool activity is forwarded in this release. Claude's intermediate text is
not added to the parent transcript, so the final answer still has one owner:
the enclosing ConnectOnion agent.

## Permissions

The public `claude_code(...)` function always maps to Claude Code's current
`manual` CLI mode. For an advanced mode, the operator binds policy before the
tool reaches the Agent:

```python
from connectonion import Agent, ClaudeCode

claude = ClaudeCode(permission_mode="acceptEdits", workspace="./my-project")
agent = Agent("lead", tools=[claude])
```

The generated `claude_code` schema still contains only task, session, working
directory, model, and timeout fields. Supported constructor modes are
`default`, `manual`, `acceptEdits`, `plan`, `auto`, `dontAsk`, and
`bypassPermissions`.

`bypassPermissions` disables Claude Code's permission protection. Bind it only
in operator-written code running inside an isolated environment; a model can
never select it through the tool schema.

Headless Claude Code cannot open its own interactive permission prompt inside
O Chat. The adapter uses Claude's `--safe-mode`, which disables `CLAUDE.md`,
skills, plugins, hooks, MCP servers, custom commands and agents, and related
customizations. This preserves installed authentication but prevents ordinary
user, project, and local configuration from raising this delegated turn's
authority. Include relevant project instructions in the delegated prompt.
Admin-managed policy still applies and may be stricter. Actions allowed by the
operator-bound mode can run and appear as live cards; an unmatched permission
request fails closed.

The subprocess receives only a small process/locale environment and
Claude-specific authentication variables. Unrelated API keys and cloud/GitHub
credentials from the parent process are not copied into Claude's environment.

The operator-bound workspace becomes the launch root. A model may choose that
directory or a resolved descendant; paths and symlinks outside it fail closed.
This is not an operating-system sandbox, so run hostile tasks inside a
container or other OS isolation boundary.

Pass back only the canonical UUID returned in `session_id`. Fuzzy Claude CLI
session search is intentionally unavailable through this tool.

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

The Codex adapter uses its app-server JSON-RPC protocol for both live inner-step
events and per-action approval callbacks. Claude Code uses its documented
`stream-json` subprocess contract for live inner tool cards and session resume.
It does not yet translate Claude's unmatched permission requests into
ConnectOnion approval cards.
