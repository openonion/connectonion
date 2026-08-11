# DD-040: Host session modes commit before acknowledgement

**Status:** Accepted

**Date:** 2026-08-11

## Context

DD-031 defines session-mode authority for the local ACP stdio adapter, and
DD-039 lets the authenticated network Host report an Agent-originated mode
change. The Host's client setter is still the legacy `mode_change` mailbox
message. It exists only while an Agent is running, has no owned response, can
cross a prompt boundary, and cannot persist a change made before the first
prompt.

The supported browser path is Host → `@connectonion/react` → O Chat. The
standalone TypeScript SDK is retired. React therefore needs one acknowledged
Host transaction; O Chat must remain protocol-free.

## Decision

### Carry one exact ACP request and response

The authenticated Host carrier accepts `ACP_REQUEST` with schema
`schema-v1.19.0` and an exact nested JSON-RPC `session/set_mode` request. Its
params validate through the official `SetSessionModeRequest` model and contain
only `sessionId` and `modeId`; `_meta` is never treated as authority. A
syntactically owned request receives one `ACP_RESPONSE`, correlated by the
request ID and the Host-bound session ID, containing the official empty
`SetSessionModeResponse` or a JSON-RPC error.

`CONNECTED` advertises `session/set_mode` only with an exact
`SessionModeState`. The persisted IDs remain `safe`, `accept_edits`, and `ulw`.
`plan` remains a temporary legacy UI alias for Safe and is never serialized as
an ACP mode.

### Derive modes from server authority

Safe is always available. Auto (`accept_edits`) is available only to the Host
operator/admin. ULW is available only to that identity when the Agent factory
was explicitly configured with a positive `_yolo_turns` ceiling. The Host
captures that launch ceiling once and disarms the Agent's automatic first-turn
activation; the durable session mode, not a constructor side effect, decides
the prompt policy.

An ACP client cannot select or extend ULW turns because
`SetSessionModeRequest` has no turns field. Entering ULW initializes the three
bounded server-owned fields from the captured ceiling. Leaving it removes all
three before persistence.

### Serialize prompt claims and policy writes in storage

The JSONL storage lock is the cross-socket and cross-worker commit boundary.
CONNECT creates an owned, durable Safe snapshot for a new session. INPUT and
`session/set_mode` each read the latest record and append their replacement
while holding the same lock. A `running` or `waiting_approval` record rejects
the mode request as retryable and prevents a second prompt claim.

The mutation is prepared in a detached copy. Ownership, TTL, history, trace,
permissions, and unrelated fields are preserved. Only a successful append may
update the connection snapshot or produce a success response. Storage lock
timeouts and append failures raise; they never fall through to an unlocked
write or an in-memory policy grant.

The process-local active-session registry remains a fast busy check, but it is
not the authority because another worker has another registry. The latest
locked durable record decides.

### Bound compatibility to the same transaction

Legacy `mode_change` is intercepted by the Host rather than forwarded into the
Agent mailbox. Its `plan` alias normalizes to Safe for rolling compatibility;
all other mode, ownership, busy-state, admin, and ULW-ceiling checks are the
same as ACP. It emits the existing `mode_changed` observation only after the
durable commit. The legacy path cannot supply a turn ceiling.

## Consequences

- A mode selected before the first prompt persists and governs that prompt.
- A response means the policy is durable, not merely queued in memory.
- Multiple sockets and workers cannot grant policy while a turn is running.
- Non-admin callers see Safe only; clients cannot manufacture Auto or ULW.
- Old clients keep a bounded transition path while React and O Chat migrate.
- A storage error is visible and leaves the prior policy authoritative.

## Rejected alternatives

- **Forward ACP into the running mailbox:** no idle receiver, no durable commit,
  and the request can cross an approval/tool boundary.
- **Trust the client session snapshot:** the client round-trips that JSON and
  could add `skip_tool_approval` itself.
- **Use only the in-memory registry:** worker processes do not share it.
- **Hold a file lock for the whole prompt:** it would serialize unrelated
  storage operations for the duration of model and human waits.
- **Accept a client `turns` extension:** ACP defines no such field and it would
  exceed the operator's launch authority.

## Related decisions

- DD-029: persistent ACP session ownership
- DD-030: generation-scoped ACP tool approvals
- DD-031: ACP session modes stay below launch authority
- DD-035: versioned ACP Host carrier
- DD-037: bound ACP Host permissions
- DD-039: authoritative ACP Host mode updates
