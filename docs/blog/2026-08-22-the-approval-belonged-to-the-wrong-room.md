# The Approval Belonged to the Wrong Room

The Codex Work Room finished a real Rust task, then failed on the smallest
possible follow-up. The browser kept the draft and eventually reported that
the Host had not confirmed it. The Host log said the message had arrived. No
file changed, and Codex never showed a new turn.

The message had stopped at an approval dialog, but not one the Work Room could
answer. A terminal follow-up resumes Codex by calling the framework's `codex`
tool directly. That call still passed through the ordinary agent approval
plugin, which opened an outer tool approval before the native Codex adapter
could start its turn. The focused Work Room owns native Codex approvals; the
outer conversation owns generic tool approvals. We had asked one room to
answer a decision rendered in another.

Making Codex automatic would have hidden the symptom by removing decisions we
want people to see. Letting every direct tool call through would have weakened
the Host boundary. The useful fact was narrower: while holding the durable
session lock, the Host had already verified the requester, the terminal Codex
invocation, and its exact state revision.

The runner now turns that fact into a one-shot capability for one operation:
the outer `codex` wrapper. The approval plugin consumes it at the first tool
boundary. A different tool consumes nothing useful and still asks; a later
Codex call still asks. Once the native adapter starts, its command and file
approvals continue through the Work Room exactly as before.

The regression uses a real Agent with the real approval plugin, not a fake that
jumps straight to the adapter. Negative cases prove the capability cannot
approve another tool or survive for a later call. The focused provider tests
and approval tests pass together, so the boundary is checked from both sides.

An approval is not just a yes-or-no question. It also has an owner and a
surface. When execution crosses from an outer agent into a focused native
provider session, preserving every approval layer can be just as wrong as
removing one. The right question must appear in the room that can answer it.
