# DD-037: Bind ACP Host Permissions to One Session and Request

**Status:** Accepted
**Date:** 2026-08-11
**Related:** [030 Generation-scoped Tool Approvals](030-acp-generation-scoped-tool-approvals.md), [035 Versioned ACP Host Carrier](035-versioned-acp-host-carrier.md)

## Decision

The authenticated ConnectOnion Host WebSocket carries ACP
`session/request_permission` as one exact nested JSON-RPC request. The socket
itself remains a ConnectOnion transport: it performs no ACP `initialize` and
continues to own authentication, onboarding, reconnect, persistence, and
dashboard control.

The Host sends an `ACP_REQUEST` immediately before the existing
`approval_needed` event. Both frames preserve the same event UUID, session ID,
and tool-call ID. The request uses the carrier version established by DD-035
and advertises exactly five choices:

- `allow_once` maps to the existing one-call grant.
- `allow_session` uses ACP `allow_always`, but maps only to the current
  ConnectOnion session grant.
- `reject_soft`, `reject_hard`, and `reject_explain` all use ACP `reject_once`;
  their ConnectOnion-specific behavior is selected by the stable option ID.

`WebSocketIO` registers one pending permission request before either response
can reach the agent mailbox. An `ACP_RESPONSE` must match the active session
and the pending JSON-RPC ID. A matching response is consumed once. Unknown or
stale responses are rejected, while a matching malformed response and ACP
`cancelled` both become `reject_hard`. The legacy response path is also
one-shot and accepts only real booleans, the implemented scopes, and the three
implemented rejection modes. This keeps the existing permission policy engine
authoritative and prevents a transport value from manufacturing authority.

Human feedback is optional presentation data under
`_meta.connectonion.feedback`. It is copied only into a rejection and never
changes whether a call is allowed.

`@connectonion/react` is the browser protocol boundary. It validates and
de-duplicates the paired frames, exposes one normalized approval item, and
sends at most one response for that item. oo-chat renders and answers the
React package's normalized state; it does not parse ACP. The standalone
TypeScript SDK is retired and receives no new ACP frontend work.

## Compatibility and reconnect

Dual-write preserves released clients during the migration. An old browser
sees `approval_needed`; a new React client prefers the ACP request and uses the
legacy event only to enrich the same card. A mirror conversion failure logs a
warning and leaves the legacy request usable.

The pending identity lives on the session's `WebSocketIO`, not on one physical
socket. Reconnect therefore replays the same request ID and accepts one bound
answer. A later response cannot approve a different request. Removing the ACP
mirror is a safe rollback because canonical approval events and the policy
engine remain unchanged.

## Rejected alternatives

- **Treat the Host socket as an ACP connection:** it never negotiated ACP
  capabilities and carries non-ACP control frames.
- **Give ACP a second permission engine:** two policy implementations can
  disagree about the same side effect.
- **Trust any matching option kind:** several product choices intentionally
  share ACP `reject_once`; the advertised option ID is the stable mapping.
- **Put feedback in authorization fields:** explanatory text is untrusted
  metadata and must not grant capability.
- **Teach oo-chat or the retired TypeScript SDK ACP:** protocol ownership would
  be duplicated across frontend layers and drift during rollout.
