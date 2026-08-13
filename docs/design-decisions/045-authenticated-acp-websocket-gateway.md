# DD-045: Put direct native ACP behind ConnectOnion admission

**Status:** Accepted

**Date:** 2026-08-12

**Related:** [DD-029 Persistent ACP Session Ownership](029-acp-persistent-session-ownership.md), [DD-030 Generation-scoped ACP Tool Approvals](030-acp-generation-scoped-tool-approvals.md), [DD-035 Versioned ACP Host Carrier](035-versioned-acp-host-carrier.md), [DD-044 Canonical Approval Mode Vocabulary](044-canonical-approval-mode-vocabulary.md), [Issue #895](https://github.com/openonion/connectonion/issues/895), [Relay security RFC #898](https://github.com/openonion/connectonion/issues/898)

## Context

ConnectOnion has two working paths:

- `co ai --acp` is an ACP v1 Agent over local stdio;
- the authenticated `/ws` Host protocol drives the released browser and carries
  additive ACP messages inside compatibility envelopes.

The browser, editors, and authorized remote clients should eventually use one
ACP interaction plane without discarding ConnectOnion identity, trust,
onboarding, and permission ceilings.

ACP v1 formally documents stdio. Its Streamable HTTP/WebSocket remote
transport remains an Active RFD. The RFD defines one `/acp` endpoint, plain
UTF-8 JSON-RPC WebSocket text frames, and `initialize` as the first protocol
message. In v1, reconnect, liveness, and disconnected-message recovery remain
implementation responsibilities. This decision therefore defines a
ConnectOnion remote-transport preview, not a claim that the upstream remote
profile is stable.

## Decision

### Direct ACP is the interaction plane; ConnectOnion is the security plane

Default `co ai` serves native ACP at `/acp` beside the existing `/ws` route.
After admission, frames use the same `ConnectOnionACPAgent` lifecycle as stdio.
Both entry points call the same ACP agent factory; transports do not duplicate
agent construction policy.
Before accepting executable protocol work, the Host verifies:

- the caller's Ed25519 identity and signature;
- the signed recipient, request path, body digest, timestamp, and one-use
  request ID;
- cross-process replay protection;
- blacklist, whitelist, contact/admin state, onboarding, and trust policy;
- exact browser Origin;
- loopback peer plus loopback request authority, or TLS/WSS otherwise.

Duplicate security headers fail closed rather than allowing proxy-dependent
interpretation. Admission attempts, pending browser tickets, total
connections, and per-principal connections are bounded.

A public request authority is never accepted over a plaintext loopback backend
connection. A reverse proxy must supply a correctly trusted HTTPS/WSS scheme;
otherwise the Host rejects the request even though the immediate proxy peer is
local.

The first JSON-RPC text frame must be a JSON-RPC 2.0 request with a non-boolean
string/integer ID, method `initialize`, and parameters accepted by the pinned
official ACP SDK. Binary frames before it are ignored as required by the RFD.
`protocolVersion` must also satisfy the SDK's published integer range before a
coding Agent is constructed. The upgrade response
carries an `Acp-Connection-Id`; it and every ACP session ID are routing values,
never credentials.

Native stdio and WebSocket transports apply the same exact JSON-RPC envelope
classifier before SDK routing. A message cannot be both a request and a
response, and response envelopes cannot contain request members. Once a valid
first `initialize` frame is admitted, an invalid later envelope receives
JSON-RPC `-32600` through the existing bounded outbound queue and is never
delivered to the Agent. Responses remain correlated by ID rather than arrival
order. The pinned SDK continues to own parameter values, nested types, results,
and extensions such as `_meta`; envelope validation does not replace ACP
schema validation.

That error reply applies to invalid request candidates, not responses. A
response has exactly one result or error; the error object has an integer code,
string message, and optional arbitrary data. An error response may carry a null
ID when its sender could not identify the request. A malformed response closes
the transport without a reply, because replying to a response can create a
protocol loop between strict peers.

One pinned-router compatibility guard runs before both native transports hand
messages to the SDK. The SDK promotes `_meta` entries to Python handler keyword
arguments after parsing official fields, so metadata whose key matches an
official generated parameter name could otherwise shadow the visible field.
Such requests receive `-32602` with fixed public details, while invalid
notifications are dropped without a response. Unrelated `_meta` entries and
extension methods remain available. A shadowed first WebSocket `initialize`
fails the existing pre-Agent admission rule and closes with `4400`.

The guard also derives permitted top-level wire keys from explicit aliases on
those pinned request models. Raw JSON must therefore say `protocolVersion`,
`sessionId`, `modeId`, and `mcpServers`, never their Python-only construction
names. Alias/name duplicates and custom root fields receive the same fixed
`-32602` request error or notification drop. Standard optional/null values and
arbitrary content inside `_meta` remain available; underscore extension
methods retain their own raw payload namespace. The first WebSocket gate
applies this rule before Agent construction, while React already emits the
standard camelCase forms and needs no compatibility conversion.

### Browsers exchange a signed request for a one-use ticket

Browser JavaScript cannot add `X-Co-*` headers to a WebSocket upgrade. It first
sends a signed JSON `POST /acp/authorize` from an exact allowed Origin.

The Host returns a random 256-bit ticket with a 60-second lifetime and stores
only its SHA-256 digest. The ticket is bound to the verified caller, recipient,
and Origin, is consumed on the first attempt including a mismatched Origin,
and travels only in `Sec-WebSocket-Protocol` beside the `acp` protocol. It is
never accepted in a URL. Authorization responses are non-cacheable. CORS
preflight allows only the documented signing headers and supports the browser
Private Network Access preflight for a loopback Agent.

The ticket adapts a browser API limitation. It is not a session bearer token,
does not bypass trust, and cannot resume a different principal's session.

### Network persistence is namespaced by the authenticated principal

Every connection receives a new ACP adapter, so in-memory sessions, pending
permissions, and cancellation state are not shared. Persistent snapshots use a
stable, non-client-selectable namespace derived from version, recipient,
verified caller, exact Origin, and admission method. The directory name is a
SHA-256 digest; raw identity values are not placed in a filesystem path.

The same principal may reauthenticate and explicitly resume its session. A
different principal sees a separate namespace even if it copies the exact
session UUID and working directory. This is the narrow ownership invariant
needed for this endpoint; the broader cross-ingress `VerifiedPrincipal` model
remains #896.

### Collaboration and permission remain separate

DD-044 applies unchanged:

- `default` and `plan` are React-owned collaboration state and are not stored
  as Host authority;
- `:read-only`, `:workspace`, and `:danger-full-access` are the only permission
  profiles the Host newly emits;
- `--yolo` is an operator shorthand for the Full access ceiling, not a fourth
  protocol mode.

On the network endpoint, Full access is advertised only when the process was
launched with `--yolo` **and** the authenticated principal is an administrator.
The existing turn/checkpoint bound still applies. A contact never inherits the
operator's Full access launch flag merely by passing the trust gate.

### WebSocket-only preview and bounded rollback

The embedded Uvicorn path does not provide the HTTP/2 required by the proposed
Streamable HTTP profile. Ordinary HTTP `/acp` returns `426`; this build does not
label an HTTP/1.1 approximation as ACP.

The released O Chat remains on `/ws` until React owns native admission,
protocol validation, reconnect, correlation, de-duplication, and explicit
fallback. The standalone TypeScript SDK is retired. The supported browser
dependency direction remains:

```text
ConnectOnion Host -> @connectonion/react -> O Chat
```

Starting `/acp` and moving the released browser are separate rollback points.
The explicit transport discovery and fail-closed downgrade rule used for that
move are defined separately in
[DD-046](046-explicit-acp-transport-discovery.md).

### Relay ACP is not approved here

This decision covers direct loopback/TLS/WSS only. A relay that terminates TLS
can still read ACP content. Per-message Ed25519 proofs in ACP `_meta` can offer
provenance or integrity, but cannot provide confidentiality, forward secrecy,
or an end-to-end encrypted channel.

#898 must select and externally review a secure channel established before ACP
`initialize`, with separate encryption keys, downgrade resistance, and
cross-language malicious-relay vectors. Until then this endpoint must not be
routed through an untrusted TLS-terminating relay or described as relay-E2E
encrypted. #897 is deferred and may retain only a narrower post-decryption
provenance role after #898 decides it.

## Failure and resource behavior

- Unknown, blocked, stale, replayed, wrong-recipient, wrong-Origin, ambiguous,
  rate-limited, and insecure non-loopback admissions fail before Agent creation.
- Binary frames are ignored as required by the upstream RFD unless they exceed
  the transport limit. Malformed text and oversized frames close the connection.
  Syntactically valid JSON with a mixed or otherwise invalid JSON-RPC envelope
  receives `-32600` after first-frame admission and is not routed to the Agent.
  Each direction has a bounded eight-message queue and applies backpressure
  rather than dropping protocol messages.
- `initialize` has a bounded deadline. Disconnect and Host shutdown cancel
  active turns, close the ACP connection, settle session work, and release
  leases. One failing cleanup callback does not skip the remaining cleanup.
- Provider `authenticate` remains an ACP application method and is never used
  as network caller authentication.

## Rejected alternatives

- **Treat `/ws` compatibility envelopes as native ACP:** `/ws` has no ACP
  initialization and contains ConnectOnion control frames.
- **Use ACP `authenticate` for caller admission:** it runs inside the protocol
  and concerns credentials offered by the Agent, not the network peer.
- **Put a token or session ID in the URL:** URLs leak into logs and routing IDs
  are not authorization roots.
- **Accept wildcard Origin or duplicate security headers:** either lets an
  unrelated page or intermediary ambiguity spend local Agent authority.
- **Create one global ACP Agent:** it mixes sessions, permissions, and cleanup
  across authenticated callers.
- **Give every trusted caller launch `--yolo`:** trust to connect is not
  administrator authority to select Full access.
- **Claim relay encryption through ACP `_meta`:** signatures do not encrypt.
- **Claim Streamable HTTP over Uvicorn HTTP/1.1:** it would create false
  interoperability evidence.

## Compatibility and rollback

Removing the optional ACP factory removes `/acp` without changing `/ws`, stdio
ACP, or stored legacy browser sessions. Principal-namespaced ACP snapshots are
private preview state; they are not silently migrated into another identity or
transport namespace. Any future namespace migration requires an authenticated,
explicit rule.
