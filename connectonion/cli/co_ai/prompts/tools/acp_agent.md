# acp_agent

Use `acp_agent` when the task specifically needs a generic ACP-speaking child
instead of the preferred native `codex` or `claude_code` tools.

- Pass an explicit `engine`: `claude-code`, `codex`, or `gemini`.
- Pass the project directory explicitly as `cwd`.
- Keep the returned `session_id` and pass it back to continue that child.
- Do not wrap this tool in `run_background`; it already owns one bounded child
  process and timeout.

The current co ai permission profile owns approval; command, approval, and
workspace are not tool arguments. With `codex-acp@1.1.14`, Codex ACP is allowed
only during explicit Full Access because that adapter cannot enforce per-action
manual or deny policy for shell and network commands. In ordinary modes, use
the native `codex` tool instead. Hosted non-admin requesters cannot start local
ACP child processes.

```python
first = acp_agent(
    prompt="Inspect this project and explain the failing test",
    engine="claude-code",
    cwd="/absolute/project/path",
)

follow_up = acp_agent(
    prompt="Now propose the smallest fix",
    engine="claude-code",
    cwd="/absolute/project/path",
    session_id="session-id-from-first-result",
)
```
