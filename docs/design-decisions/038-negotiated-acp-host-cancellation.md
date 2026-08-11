# DD-038: Negotiate ACP Host Cancellation Without Duplicate Interrupts

**Status:** Accepted
**Date:** 2026-08-11
**Related:** [025 Interruptible Agent Steps](025-interruptible-agent-steps.md), [035 Versioned ACP Host Carrier](035-versioned-acp-host-carrier.md), [037 Bound ACP Host Permissions](037-bound-acp-host-permissions.md)

## Decision

The authenticated Host WebSocket accepts an `ACP_NOTIFICATION` carrier whose
nested message is one exact ACP v1.19 `session/cancel` JSON-RPC notification.
The Host validates the carrier schema and connection-owned session ID, then
maps it to the existing internal `INTERRUPT` lifecycle from DD-025. Canonical
traces, persistence, provider calls, and stop-signal semantics do not gain a
second cancellation implementation.

`CONNECTED.carrier_capabilities` advertises the exact ACP schema and accepted
client notification method. `@connectonion/react` sends the ACP form only when
that capability is present and otherwise sends the legacy `INTERRUPT`. It must
never send both: a second queued interrupt could be consumed by a later turn.

Each active `WebSocketIO` generation accepts one interrupt request. The guard
lives on the IO rather than a physical socket, so reconnects and repeated
clicks cannot enqueue another signal. A new turn receives a new IO and a fresh
guard. A cancellation that loses the completion race stays in the completed
IO and cannot reach the next input.

When an ACP permission request is pending, the React client answers that exact
request with `RequestPermissionOutcome::Cancelled` rather than also sending a
session cancellation. DD-037 maps the outcome to the existing hard rejection,
which stops the turn without leaving an orphan interrupt.

## Compatibility and security

Released clients may continue sending `INTERRUPT`; the Host routes it through
the same one-shot IO guard. A client notification must arrive on an
authenticated connection and, when signed-command mode is negotiated, pass
the existing command signature and replay gate before ACP validation.

Wrong session IDs, unknown schemas or methods, malformed JSON-RPC messages,
and cancellation without an active turn receive explicit errors and execute
no cancellation. The capability is ConnectOnion carrier metadata, not ACP
`initialize` negotiation and not a grant of authority.

## Rollout and rollback

The Host reader and capability land first. The React writer lands second, and
O Chat then delegates its Stop action to React. Rollback removes the advertised
capability and ACP adapter; React falls back to the unchanged legacy frame.

## Rejected alternatives

- **Dual-send ACP and legacy cancel:** duplicate signals can cross a turn boundary.
- **Assume all Hosts understand ACP cancel:** breaks released Host versions.
- **Teach O Chat the capability or JSON-RPC shape:** duplicates protocol ownership.
- **Cancel arbitrary Python threads:** DD-025 rejects unsafe termination; this
  adapter preserves bounded abandonment and its documented side-effect limits.
