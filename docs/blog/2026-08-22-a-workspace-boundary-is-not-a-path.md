# A Workspace Boundary Is Not a Path

The first public Beta 7 Claude failure test did exactly what a boundary test
should do: it asked the owned adapter to work one directory outside its
workspace. Claude Code never launched. The tool rejected the request in less
than a millisecond.

Then the browser printed the Host's absolute workspace path.

The rejection was correct, but its explanation crossed the boundary it was
describing. The adapter had formatted the resolved root into its JSON error,
and the parent agent faithfully repeated that error in O Chat. No credential
was exposed, yet a private machine path had become browser data. A safe action
with an unsafe description is still an information leak.

Keeping the absolute path seemed useful for debugging. It was not useful to
the person who could act on the error: the browser user cannot change the
Host's configured root, and does not need to know its spelling. The actionable
fact is only that the requested directory is outside the configured workspace.
Detailed local diagnostics belong in Host-owned logs, not in the provider's
public envelope.

The adapter now returns categorical messages for four boundary failures:
the configured workspace is unavailable, the requested directory is
unavailable, the target is not a directory, or the target escapes the
configured workspace. None includes the configured root, requested path,
resolved symlink target, or raw operating-system exception.

The regression tests deliberately use names such as
`customer-secret-workspace` and `private-host-directory`. They cover a direct
escape, a symlink escape, a missing directory, a file used as a directory, and
an invalid operator workspace. Each assertion checks both the useful public
category and the absence of every sensitive-looking path. The Claude adapter
suite passes 56 tests; the related provider, approval, error, and Work Room
suites pass another 92.

The lesson is smaller than “hide errors.” Errors are part of the product and
must remain specific enough to recover from. But a boundary message should
name the rule that failed, not disclose the private value used to enforce it.
