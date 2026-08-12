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
`SessionModeState`. The persisted IDs are `default`, `auto_approve`, and `full_access`.
`plan` remains a local UI workflow mapped to Default and is never serialized as
an ACP mode.

### Derive modes from server authority

Default is always available. Auto-approve (`auto_approve`) is available only to the Host
operator/admin. Full access is available only to that identity when the Agent factory
was explicitly configured with a positive `_yolo_turns` ceiling. The Host
captures that launch ceiling once and disarms the Agent's automatic first-turn
activation; the durable session mode, not a constructor side effect, decides
the prompt policy.

An ACP client cannot select or extend Full access turns because
`SetSessionModeRequest` has no turns field. Entering Full access initializes the three
bounded server-owned fields from the captured ceiling. Leaving it removes all
three before persistence.

### Serialize prompt claims and policy writes in storage

The JSONL storage lock is the cross-socket and cross-worker commit boundary.
CONNECT creates an owned, durable Default snapshot for a new session. INPUT and
`session/set_mode` each read the latest record and append their replacement
while holding the same lock. A `running` or `waiting_approval` record rejects
the mode request as retryable and prevents a second prompt claim.

Both WebSocket INPUT and HTTP `/input` carry the signature-verified requester
into that prompt claim. An existing owned session cannot be claimed by a
different identity or by a path that dropped the identity after authentication;
the session ID remains correlation, never authority.

The mutation is prepared in a detached copy. Ownership, TTL, history, trace,
permissions, and unrelated fields are preserved. Only a successful append may
update the connection snapshot or produce a success response. Storage lock
timeouts and append failures raise; they never fall through to an unlocked
write or an in-memory policy grant.

The process-local active-session registry remains a fast busy check, but it is
not the authority because another worker has another registry. The latest
locked durable record decides.

The storage implementation is intentionally synchronous, but WebSocket
CONNECT and mode handlers never run that file-lock wait on the async event
loop. They delegate the complete transaction to a worker thread and await its
result. This changes scheduling only: the JSONL lock remains the sole commit
boundary.

CONNECT does not publish authenticated connection state until durable mode
initialization and mode-state derivation both succeed. A failure sends a
bounded error, logs the private exception on the server, and leaves later
frames on that socket subject to the unauthenticated gate.

### Make the Host ceiling terminal for each Full access grant

The captured launch ceiling is also attached to the fresh hosted Agent as a
Host-only runtime boundary. When that many turns have been consumed, the Host
may emit the existing checkpoint observation but must immediately exit to
Default, remove all bypass fields, and stop. The legacy local-Agent mailbox may
still extend a locally configured Full access run; it cannot extend a Host grant. A
client that wants another hosted Full access run must make another durable
`session/set_mode` transaction after the prompt is idle.

Before the final Host record is appended, the verified requester is restored
and the session is normalized against the captured policy. Invalid plugin or
Agent state is downgraded to Default and has every Full access bypass field removed. This
prevents a terminal `used == turns` snapshot, or any expanded ceiling, from
stranding the durable session.

If Agent construction or execution raises after the atomic prompt claim, the
Host appends a policy-normalized terminal `failed` replacement before the
exception crosses the carrier boundary. A failed factory cannot leave the
session permanently `running` and block later prompt or mode transactions.

### Keep carrier failures stable and bounded

HTTP prompt claims map the same owned policy failures to transport status:
missing or foreign ownership is 404, busy/running is 409, and invalid policy
input is 400. Internal storage details are logged but never returned.

The Python client applies one caller-supplied deadline to endpoint resolution,
CONNECT negotiation, PING handling, and the owned ACP response together.
Successful acknowledgements remove any local Full access bypass fields before
mirroring Default or Auto-approve, so the client snapshot cannot retain stale authority.
The deadline bounds client waiting, not the already-running Host transaction:
a timeout is an unknown outcome, never proof of rollback. The client keeps its
old local snapshot and reconnects to read authoritative `CONNECTED` mode state
before retrying.

WebSocket prompt execution uses the same disclosure boundary. Owned
`ModeTransactionError` policy results retain their stable public fields;
unexpected Agent or storage exceptions are logged with traceback on the Host
and collapse to `-32603 / Unable to run agent` on the wire.

### Bound compatibility to the same transaction

Legacy `mode_change` is intercepted by the Host rather than forwarded into the
Agent mailbox. Its `plan` alias normalizes to Default for rolling compatibility;
all other mode, ownership, busy-state, admin, and Full-access-ceiling checks are the
same as ACP. It emits the existing `mode_changed` observation only after the
durable commit. The legacy path cannot supply a turn ceiling.

## Consequences

- A mode selected before the first prompt persists and governs that prompt.
- A response means the policy is durable, not merely queued in memory.
- Multiple sockets and workers cannot grant policy while a turn is running.
- Slow storage cannot stall unrelated WebSocket work on the event loop.
- Non-admin callers see Default only; clients cannot manufacture Auto-approve or Full access.
- A hosted Full access grant ends at its launch ceiling and requires a new transaction.
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
