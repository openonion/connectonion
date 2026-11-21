# Tool: Codex delegation

Delegate a scoped coding task to the user's installed Codex CLI when a separate
coding agent is better suited to implement or investigate it.

When the user explicitly asks to open, use, start, or hand work to Codex, call
`codex()` immediately. Do not probe with `pwd`, `ls`, or `which codex`; the
adapter resolves the workspace and reports an unavailable or unauthenticated
Codex installation honestly.

If the request only says to open or start Codex, call `codex()` with no
`prompt`. That creates the native provider thread and Work Room without
inventing or submitting a task. If the user included work, pass their actual
request as `prompt`; never replace it with a generic greeting or probe.

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

The current co ai mode determines Codex's policy. Ask first (protocol
ID `read-only`) starts in the read-only sandbox; requests for more permission
ask the operator. A non-admin requester or no approval UI gets declined.
Hosted Auto uses the `workspace-write` sandbox with no approval prompts.
Full access uses the `danger-full-access` sandbox without routine prompts.
The tool reapplies the current policy when resuming.

When a result has status `blocked` or contains declined actions, tell the user
which actions were declined and why; never say the work was done. Report only
work supported by the recorded results.

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
