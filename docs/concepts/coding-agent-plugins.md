# Coding-agent plugins

`CodexPlugin` and `ClaudeCodePlugin` let any ConnectOnion Agent delegate one
task to a locally installed coding agent while keeping authority in operator
configuration.

```python
from connectonion import Agent, ClaudeCodePlugin, CodexPlugin

agent = Agent(
    "developer",
    plugins=[
        CodexPlugin(permission_mode="manual", workspace="."),
        ClaudeCodePlugin(permission_mode="manual", workspace="."),
    ],
)
```

Each plugin registers one model-callable tool:

- `codex(prompt?, cwd?, session_id?, model?, timeout?)`
- `claude_code(prompt, cwd, session_id?, model?, timeout?)`

The model cannot select the permission mode, provider command, or workspace
root. Relative `cwd` values resolve below the configured root; traversal and
symlink escapes fail closed.

## Permission modes

| Mode | Boundary |
| --- | --- |
| `manual` | The provider asks when its automation interface supports the action; unsupported prompts fail closed. |
| `auto_approve` | Work may proceed within the configured workspace and provider sandbox. |
| `full_access` | Per-action prompts are disabled inside the explicit Host launch ceiling. Configure this only for a trusted workspace. |

The compatibility names `:read-only`, `:workspace`, and
`:danger-full-access` normalize to these three modes. Resuming a provider
session reapplies the plugin's current operator-owned mode.

## Live invocation contract

The parent tool call becomes one `provider_invocation` with a stable
`invocationId` and `parentToolCallId`. Provider tool/file/command activity
carries the same correlation and is nested by compatible clients. Every
invocation ends as `completed`, `failed`, or `cancelled`; bounded result and
error text remain available after reconnect/replay. Unknown providers and old
clients retain the generic tool-card fallback.

The provider session ID can be passed back to the tool to resume work. It is
not a browser or navigation API.

For Codex, omitting `prompt` creates or resumes the native provider thread
without starting a model turn. This is the backend half of O Chat's “Open Work
Room” behavior: the room can exist before it has a task.

`co ai` also installs a routing interceptor. Explicit run/use/start/open Codex
intent receives a hidden native-route reminder, and any attempt to execute the
Codex CLI through bash, shell, command substitution, a background wrapper, or a
package runner is rejected with `codex()` as the required next action. The
interceptor parses command positions, so documentation searches and strings
that merely contain “codex” are not blocked.
