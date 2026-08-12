# Tool: Claude Code delegation

Delegate a scoped coding task to the user's installed Claude Code CLI when a
separate coding agent is better suited to implement or investigate it.

## Contract

- Always pass an explicit `cwd` for the target repository.
- Save the returned `session_id`. Pass the exact same ID on follow-up calls so
  Claude Code resumes its existing session instead of starting over.
- Give Claude Code a bounded task with the requirements and constraints. You
  remain responsible for planning, checking the diff, and reviewing the code.
- Read the structured `status`, `result`, and `error` fields. A missing CLI,
  authentication failure, unavailable Auto mode/model, timeout, or non-zero
  exit is a result to handle; never claim the delegated work completed.
- Claude Code runs headlessly here. Its inner tool starts and results appear
  automatically as live cards in co ai, so do not narrate or duplicate them.
  Read only can use actions allowed by its bound provider mode, but it cannot
  open an unmatched Claude permission prompt in the co ai UI. Auto can
  edit in-scope files; other actions that need a prompt fail closed. Claude may
  describe a denied action in a successful JSON result, so inspect the diff and
  test output instead of trusting status alone.
- In a hosted session, Claude Code delegation is operator-only. Shared contacts
  receive a structured refusal and the local CLI is not started.

Do not wrap `claude_code()` in `run_background()`. The adapter already owns a
bounded subprocess and returns a resumable JSON result.

## Permission boundary

The current co ai permission profile determines Claude Code's provider mode.
Read only uses Claude's normal permission rules. Auto permits in-scope file
edits while retaining Claude's rules for other actions. Full access
uses Claude Auto mode and its safety classifier. The integration supplies the
mode again when resuming and never selects `bypassPermissions`. Auto mode is
available only for supported accounts, models, Anthropic API connections, and
organization policy; an unavailable Auto mode is a provider failure to report.
Claude's safe mode disables ordinary project and user customizations—including
`CLAUDE.md`, skills, plugins, hooks, MCP servers, commands, and custom agents—so
they cannot raise the selected mode's authority. Put all relevant task and
project instructions in the prompt. The requested `cwd` must remain inside the
project root where `co ai` started.

## Example

```python
first = claude_code(
    prompt="Implement the parser described in issue #42 and run focused tests.",
    cwd="/absolute/path/to/repo",
)

# After retaining the session_id from the JSON result:
follow_up = claude_code(
    prompt="Address the review finding about malformed UTF-8 input.",
    session_id="0b7e2f13-9c44-48ef-91bc-426bbff68671",
    cwd="/absolute/path/to/repo",
)
```
