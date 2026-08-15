# Ten minutes was not a timeout policy

*2026-08-15*

An agent asked ConnectOnion to let a shell command run for two hours. Ten
minutes later, the command stopped. Worse, the tool reported the stop as an
ordinary string result, so the agent believed the command had completed.

Both behaviours came from a small convenience that had outgrown its original
context. The shell tools accepted a `timeout` argument but silently replaced
every value above 600 seconds with 600. When `subprocess` raised its timeout
exception, the tools caught it and returned text beginning with `Error:`.
Humans could read that text as a failure; the tool executor could not. From its
perspective the Python function returned normally, so the trace status was
`success`.

## Nested agents changed the scale

Ten minutes may sound generous for a command typed at a terminal. It is not
generous for an agent that launches another agent. The child may inspect a
repository, edit several files, run a test suite, and wait for a remote build.
That work can legitimately exceed the old ceiling, and the parent already has
the context needed to choose an appropriate bound.

The fix makes the public argument truthful: the default remains 120 seconds,
but an explicit caller-supplied timeout now reaches `subprocess.run` unchanged.
There is no hidden second policy inside the tool.

## Failure needs structure

The shell tools also no longer consume `TimeoutExpired`. A direct Python caller
can catch that exception normally. When the same function runs as an Agent
tool, ConnectOnion's existing executor catches it at the orchestration boundary
and records a tool result with `status: error` and `error_type:
TimeoutExpired`. The model still receives a useful error message, while the
trace, events, and clients can reliably tell that the command did not finish.

Tests cover both halves of the contract. A 7,200-second timeout must be passed
through unchanged for `bash`, `Shell.run`, and `Shell.run_in_dir`; a simulated
timeout must raise from the direct API and become an error in an Agent trace.
No test needs to wait two hours to prove it.

The broader lesson is that limits are part of an API even when they are hidden.
If a caller is allowed to request a value, silently substituting another value
creates false confidence. And once a failure crosses a tool boundary, it must
remain a failure—not merely look like one in a string.
