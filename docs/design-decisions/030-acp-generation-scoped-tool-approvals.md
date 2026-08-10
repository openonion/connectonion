# Design Decision: Bind ACP Tool Approvals to One Prompt Generation

**Status:** Accepted
**Date:** 2026-08-10
**Related:** [012 Tool Execution Separation](012-tool-execution-separation.md), [023 Trust Policy System](023-trust-policy-system-design.md), [025 Interruptible Agent Steps](025-interruptible-agent-steps.md), [028 ACP Ordered Event Bridge](028-acp-ordered-event-bridge.md), [029 ACP Persistent Session Ownership](029-acp-persistent-session-ownership.md)

## Decision

ConnectOnion remains the policy owner for ACP tool calls. The existing
`tool_approval` hook decides whether host configuration, a skill grant, a
session grant, the active mode, or a non-overridable control-file refusal
permits a call. ACP is used only when that policy reaches its existing human
approval boundary.

The synchronous Agent thread sends its existing `approval_needed` IO event
with the current tool-call ID. The ACP generation bridge converts it to the
official `session/request_permission` request and schedules the asynchronous
client call on the bridge's owning event loop. The Agent thread waits through
the same interruptible IO boundary used by hosted approvals; it never blocks
the event loop.

Every request is bound to one canonical session ID, one active prompt
generation, and the existing tool-call ID. A generation accepts at most one
pending permission request. Cancellation, close, EOF, or generation retirement
wakes the waiter and cancels the local client future. A late remote response
has no mailbox to enter and cannot authorize a later prompt or another
session.

The adapter advertises three stable options:

- `allow_once` maps to the existing one-call approval;
- `allow_session` uses ACP's `allow_always` presentation hint but is labelled
  “Allow for this session” and maps only to ConnectOnion's session scope;
- `reject_once` hard-rejects the current turn.

Only those exact option IDs are accepted. ACP's cancelled outcome, unknown or
malformed selected options, client errors, and disconnected transports all
become hard rejection. This slice does not advertise `reject_always`, because
ConnectOnion has no equivalent durable deny scope.

A session grant remains part of the Agent session dictionary. It becomes
durable only when the enclosing successful prompt crosses DD-029's atomic
commit boundary. Cancellation, refusal, update failure, or persistence failure
restores the prior checkpoint and therefore cannot accidentally retain a grant
from an uncommitted turn.

## Why

Reimplementing tool classification in the ACP adapter would create a second
authorization engine that could drift from host.yaml, bash-chain validation,
skill permissions, control-file protection, and future policy work. Reusing
the existing blocking gate keeps the decision in one place while the adapter
only translates transport models.

Session ID alone is not enough. An abandoned tool or late approval response
can outlive its request, and tool-call IDs are not globally unique. Adding the
prompt generation makes the reply a one-use capability with an explicit
lifetime.

ACP calls are asynchronous while Agent hooks are synchronous. Scheduling onto
the event loop and waiting from the worker thread preserves both APIs without
nested event loops, per-event tasks, or direct cross-thread client calls.

## Consequences

Allow-for-session survives ACP close/resume for the same logical session, but
does not create a project-wide or cross-session grant. Tool side effects that
completed before a later persistence failure cannot be rolled back; the
permission state and conversation snapshot are rolled back together.

The current ACP schema has no free-form feedback field in its permission
outcome, so ACP rejection maps to ConnectOnion's hard-reject behavior without
inventing text in protocol metadata. Session modes and a general
principal/capability policy engine remain separate decisions.

## Rejected alternatives

- **An ACP-specific dangerous-tool list:** duplicates policy and inevitably
  creates bypasses when one list changes.
- **Accept any selected option ID:** lets a malformed or malicious client
  manufacture authority the agent never offered.
- **Treat `allow_always` as project-persistent:** ConnectOnion has no matching
  audited grant contract in this milestone.
- **Use only session ID for correlation:** stale replies can authorize a later
  prompt with a reused tool-call ID.
- **Block the event loop on the Agent approval gate:** deadlocks the very
  client request needed to answer the gate.
