# DD-046: Select native ACP through explicit transport discovery

**Status:** Accepted

**Date:** 2026-08-12

**Related:** [DD-035 Versioned ACP Host Carrier](035-versioned-acp-host-carrier.md), [DD-045 Authenticated ACP WebSocket Gateway](045-authenticated-acp-websocket-gateway.md), [Issue #915](https://github.com/openonion/connectonion/issues/915), [React issue #32](https://github.com/openonion/connectonion-react/issues/32)

## Context

DD-045 mounts native ACP at `/acp`, while the released browser still uses the
legacy ConnectOnion `/ws` transport. React must select one path before it can
authenticate or initialize ACP. The legacy socket advertises ACP carrier
capabilities only after its own authenticated `CONNECTED` handshake, which is
too late for pre-connection selection.

Trying `/acp` and falling back after an Origin, TLS, trust, authorization, or
network failure would turn a security or operational error into a silent
downgrade. Trying both paths could duplicate prompts, permission decisions, or
cancellation. Package-version inference would also advertise endpoints that a
generic `host()` did not mount.

Upstream ACP negotiates protocol features during `initialize`; its remote
transport remains Draft. ConnectOnion therefore needs a narrow, explicitly
versioned preview descriptor for choosing the transport, without inventing a
second set of ACP feature capabilities.

## Decision

An ACP-enabled Host publishes this public descriptor in `/info` only after it
has successfully mounted the gateway:

```json
{
  "transports": {
    "acp": {
      "protocol_version": 1,
      "type": "websocket",
      "path": "/acp",
      "authorization": {
        "type": "connectonion-ticket",
        "path": "/acp/authorize"
      }
    }
  }
}
```

This descriptor selects a transport. It is not an ACP `initialize` capability,
is not authentication, and grants no authority. It contains fixed public route
metadata only; connection IDs, session IDs, permissions, identities beyond the
existing public Agent address, tickets, and signatures remain absent.
`/info` is returned with `Cache-Control: no-store`: a response cached before an
ACP deployment could otherwise turn explicit native support back into legacy
fallback, while a cached descriptor after rollback could advertise a dead
endpoint.

React selects exactly one path before admission:

- no `transports.acp` descriptor means use the bounded legacy `/ws` fallback;
- the exact supported descriptor means use native ACP;
- a malformed or unsupported descriptor fails closed;
- after native ACP is selected, every admission, Origin, TLS, trust, and
  transport error fails closed rather than downgrading or attempting `/ws`.

Protocol version 1 comes from the pinned official ACP SDK constant. ACP feature
support remains negotiated with the official SDK after `initialize`.

This is the narrow 1.7 compatibility slice of issue #345's later discovery and
transport separation. It does not pull the 2.3 provider/adapter architecture
into the preview train.

## Rejected alternatives

- **Probe `/acp` and downgrade on failure:** conflates absence with security,
  policy, CORS, TLS, and network failures.
- **Open `/ws` to read its capabilities first:** selects the old protocol before
  discovering the new one and creates a dual-connection lifecycle.
- **Infer support from the package version:** the optional ACP factory, not the
  installed version, determines whether `/acp` exists.
- **Call this an ACP capability:** ACP capabilities describe optional protocol
  behavior after `initialize`; this metadata chooses how to reach initialize.
- **Publish tickets or session details:** routing and admission state do not
  belong in unauthenticated discovery.

## Compatibility and rollback

Hosts without native ACP omit `transports.acp` and old React clients ignore the
new field. Removing the descriptor makes updated React choose legacy `/ws`
without changing stored sessions. Once a valid descriptor was observed for a
connection attempt, however, errors never trigger an automatic downgrade.
