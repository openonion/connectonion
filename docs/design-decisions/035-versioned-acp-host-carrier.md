# DD-035: Carry Versioned ACP Notifications Beside Legacy Host Events

**Status:** Accepted
**Date:** 2026-08-11
**Related:** [028 Ordered ACP Event Bridge](028-acp-ordered-event-bridge.md), [032 ACP Interoperability Evidence](032-acp-interoperability-evidence.md), [034 ACP-aligned Wire Tool Statuses](034-acp-aligned-wire-tool-statuses.md)

## Decision

The authenticated ConnectOnion Host WebSocket remains a ConnectOnion
transport. It also carries a versioned `ACP_NOTIFICATION` envelope whose
`message` is one exact ACP JSON-RPC `session/update` notification:

```json
{
  "type": "ACP_NOTIFICATION",
  "acpSchema": "schema-v1.19.0",
  "message": {
    "jsonrpc": "2.0",
    "method": "session/update",
    "params": { "sessionId": "...", "update": {} }
  }
}
```

The outer envelope is not ACP. It exists because this socket also owns
authentication, onboarding, reconnect, persistence, and dashboard control and
does not perform ACP `initialize`. The nested message is serialized from the
official Python models with ACP camelCase fields.

Python pins `agent-client-protocol==0.12.0`; the JavaScript ACP models used by
`@connectonion/react` pin `@agentclientprotocol/sdk==1.2.1`. Both were generated
from stable `schema-v1.19.0`. The exact pair changes together with the carrier
version and the shared cross-repository fixture. This supersedes DD-032's SDK
range for the cross-language Host carrier; DD-032's typed stdio conformance
boundary otherwise remains in force.

The first carrier slice includes `tool_call` and `tool_call_update`. Canonical
trace events and provider-facing IO keep their ConnectOnion names and statuses.
This narrows DD-034's “do not rename wire events” decision: it still governs
canonical and legacy frames, while the public Host socket may add versioned ACP
aliases.

## Rollout and compatibility

Host dual-writes ACP and legacy tool frames during the migration. Released
clients therefore continue to receive the old event, while updated Python and
React readers accept both and de-duplicate by stable tool ID. For React
applications, `@connectonion/react` is the browser protocol boundary and the
only SDK used by oo-chat; its reader ships before or with the writer in a
coordinated release. The standalone `connectonion` TypeScript client may carry
the same compatibility reader for non-React consumers, but it is not an
oo-chat dependency or a React release gate. Legacy removal requires a future
major version, usage evidence, and a separate decision.

ACP mirroring is additive and non-authoritative. A malformed internal event or
conversion failure is logged, the legacy frame is still delivered, and the
forwarder drains to the single authoritative `OUTPUT`. This prevents a
completed side effect from looking retryable because its presentation mirror
failed.

Unknown schema versions and malformed envelopes are rejected. Valid ACP
partial tool updates preserve optional fields; unknown lifecycle values never
become a successful UI state.

## Rollback

Stop emitting `ACP_NOTIFICATION` frames. No trace, session snapshot, provider
event, authentication flow, or legacy consumer changes, so rollback does not
rewrite data and does not require a coordinated client downgrade.

## Rejected alternatives

- **Call the Host socket ACP:** it has no ACP initialization or capability
  negotiation and carries ConnectOnion-only control frames.
- **Replace legacy frames immediately:** breaks released clients before they
  can learn the new envelope.
- **Use compatible dependency ranges across languages:** pre-1.0 generated
  models can drift while package managers still consider the upgrade valid.
- **Store ACP envelopes in canonical traces:** couples persistence and evals to
  a transport migration and makes rollback destructive.
