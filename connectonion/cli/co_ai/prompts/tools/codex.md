# Tool: Codex delegation

Delegate a scoped coding task to the user's installed Codex CLI when a separate
coding agent is better suited to implement or investigate it.

When the user explicitly asks to open, use, start, or hand work to Codex, call
`codex()` immediately. Do not probe with `pwd`, `ls`, or `which codex`; the
adapter resolves the workspace and reports an unavailable or unauthenticated
Codex installation honestly.

## Contract

- Pass `cwd` when the user named a specific repository. Otherwise omit it and
  let the adapter use its operator-bound workspace.
- Save the returned `session_id`. Pass the exact same ID on follow-up calls so
  Codex continues its existing thread instead of starting over.
- Give Codex a bounded task with the relevant requirements, constraints, and
  requested skill instructions. You remain responsible for the plan and review.
- Read the structured result and verify the work yourself before reporting it.
- A missing CLI, denied action, timeout, or failed turn is a result to handle;
  do not claim the delegated work completed.

Do not wrap `codex()` in `run_background()`. The adapter already has a bounded
timeout and streams Codex's inner command/file events and approval requests to
the frontend.

## Permission boundary

The current co ai permission profile determines Codex's policy. Read only
starts read-only and asks if Codex requests more permission. Auto allows workspace
writes while retaining approval for untrusted commands and requests outside
that sandbox. Full access runs without prompts using Codex's
`danger-full-access` sandbox. The tool reapplies the current policy when
resuming.

## Example

```python
first = codex(
    prompt="Implement the parser described in issue #42 and run its focused tests.",
    cwd="/absolute/path/to/repo",
)

# After reading the returned JSON envelope and retaining its session_id:
follow_up = codex(
    prompt="Address the review finding about malformed UTF-8 input.",
    session_id="0199...",
    cwd="/absolute/path/to/repo",
)
```
