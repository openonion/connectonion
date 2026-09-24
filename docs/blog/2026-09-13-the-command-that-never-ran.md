# The command that never ran

An unattended agent stopped after a bash command was refused. The log explained
which policy refused it, but it did not show the command:

```
✗ Error: Tool 'bash' denied by connectonion.auto: command is outside the
focused verification and read-only allowlists
```

That was enough to know the policy had worked. It was not enough to know what
the agent had tried. The refused command left no filesystem changes, process
output, or other evidence behind. Its arguments existed only at the tool
boundary, and the log dropped them at exactly that boundary.

## A start record waiting for a finish

Tool logging is deliberately split in two. `log_tool_call` stores the tool name
and arguments, then `log_tool_result` prints one compact line containing the
stored call, status, and duration. Successful tools complete both halves:

```
▸ bash(command="git status")                         ✓ 0.02s
```

A policy refusal is raised by a `before_each_tool` hook. The executor catches
that exception and prints its message directly, without completing the pending
tool log. The command was not missing from the logger; the second half of the
logging protocol was never called.

That distinction matters. Reformatting the policy error would duplicate command
rendering, invent another truncation rule, and fix only one source of refusal.
Completing the existing tool log preserves the same display and redaction path
used by every executed command.

## Complete the record before explaining the error

The error path now calls `log_tool_result(..., success=False)` before printing
the detailed exception. A refused command therefore produces two useful pieces
of evidence:

```
▸ bash(command="co browser get_text | head -40")     ✗ 0.01s
✗ Error: Tool 'bash' denied by connectonion.auto: ...
```

The first line answers what was attempted and when. The second answers why it
did not run. This also covers exceptions from other pre-execution hooks and
ordinary tool failures, whose pending call records had the same incomplete
lifecycle.

The tool still never executes after a refusal. The change is observability only:
it completes a log record that already exists and leaves permission decisions,
trace status, and error propagation unchanged.

## The regression test refuses before execution

The focused test installs a `before_each_tool` hook that raises the same shape
of policy error seen in unattended runs. It then asserts that the executor marks
the trace as an error and completes the logger with `success=False` while the
original command remains the pending call's arguments.

Before the fix, the trace assertion passed but the logger assertion failed: the
system knew the call failed, yet the human-readable evidence omitted what the
call was. After the fix, the full tool-executor unit file passes 22 tests.

The lesson is small: when logging has a start and a finish, rejection is still
a finish. A command that never ran often needs a better record than one that did.
