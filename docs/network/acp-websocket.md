# Authenticated ACP WebSocket

`co ai` starts an ACP v1 WebSocket preview at `/acp` alongside the existing web-chat
transport at `/ws`. ACP owns the coding-agent conversation. ConnectOnion still
owns who may open it.

The upstream remote transport is still an Active ACP RFD. This is the first
direct remote-ACP preview slice. The current O Chat release still
uses `/ws`; moving `@connectonion/react` and O Chat to native ACP is tracked
separately. Starting `/acp` by default does not bypass the existing trust gate
and does not make a local coding agent public by itself.

## Security boundary

The gateway performs these checks before it constructs an ACP Agent:

1. Verify the caller's Ed25519 signature.
2. Verify the signed recipient is this hosted Agent.
3. Atomically reject a reused signature.
4. Apply the Host's `open`, `careful`, `strict`, or custom trust policy.
5. For browsers, require an exact allowed `Origin`.
6. Require the first JSON-RPC text frame to be ACP `initialize`.
7. Bound verified admission attempts, tickets, connections, frames, and queues.

Only then does the gateway create one isolated `ConnectOnionACPAgent` for the
connection. The verified caller, trust level, recipient, Origin, and admission
method are attached as the connection principal. A connection or ACP session
ID is routing state, never authentication. The server returns a fresh
`Acp-Connection-Id` in the upgrade response, but it does not grant access.
Stdio and WebSocket call the same ACP agent factory; only their transports and
network admission differ.

Plain HTTP/WS is accepted only when both the ASGI peer and request authority are
loopback/localhost. A public authority requires TLS/WSS even when the immediate
peer is a local reverse proxy. The proxy must provide a correctly trusted secure
scheme; an ambiguous deployment fails closed.

ACP `authenticate` is not used for network admission. That ACP method remains
available for credentials an Agent itself may need, such as signing in to a
model provider.

## Programmatic client flow

A non-browser client signs the WebSocket upgrade as an ordinary ConnectOnion
HTTP request:

- method: `GET`
- path: `/acp`
- body: empty
- signed fields: method, path, canonical query, body hash, timestamp,
  one-use request ID, and recipient
- headers: `X-Co-From`, `X-Co-Signature`, `X-Co-Timestamp`, `X-Co-To`, and
  `X-Co-Request-Id`

After the server accepts the upgrade, the client sends ordinary ACP JSON-RPC
text frames. The first is `initialize`; subsequent session lifecycle,
permission, mode, prompt, cancel, resume, and close messages use the same ACP
v1 behavior as `co ai --acp` on stdio.

## Browser flow

Browsers cannot set custom headers on a WebSocket upgrade, so the future
React/O Chat native-ACP client will use a two-step admission flow:

1. Sign and `POST` a JSON object to `/acp/authorize` using the same `X-Co-*`
   headers. The exact browser Origin must be allowlisted.
2. Receive a random 256-bit ticket that expires after 60 seconds.
3. Open `/acp` with the returned subprotocols, for example:

   ```js
   const socket = new WebSocket(url, [
     "acp",
     `connectonion.ticket.${ticket}`,
   ])
   ```

The server stores only the ticket's SHA-256 digest. A ticket is bound to the
verified caller, this Agent's address, and the exact Origin. It is removed on
its first use, including a mismatched-Origin attempt, and is never accepted in
a URL query string. Responses use `Cache-Control: no-store` and an exact
`Access-Control-Allow-Origin`, never `*`.

The browser still signs the authorization request. The ticket adapts browser
transport limitations; it does not replace ConnectOnion identity or trust.
The preflight accepts only the documented signing headers and supports Private
Network Access when an HTTPS page reaches a loopback Agent.

Before admission, an ACP-enabled Host advertises the transport in its public
`/info` response:

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

This is ConnectOnion transport discovery, not an ACP `initialize` capability.
React selects native ACP when the exact supported descriptor is present and
uses the compatibility `/ws` transport only when it is absent. A malformed or
unsupported descriptor, or any later admission/transport failure, fails closed
instead of silently downgrading or sending through both paths.
The `/info` response is `Cache-Control: no-store`, so upgrade and rollback
selection cannot reuse a stale transport descriptor.

## Session ownership and permissions

Persistent network ACP sessions are stored under a stable namespace derived
from the recipient Agent, verified caller, exact Origin, admission method, and
bound workspace identity.
The same principal can reauthenticate and resume; another principal cannot
load the snapshot even with the copied session UUID and working directory.

Network sessions use `/` as a virtual workspace root. The Host maps it to the
directory captured when `co ai` started and rejects every other `cwd` before
constructing an Agent. The actual Host path is not part of the public protocol.
Stdio ACP keeps accepting an existing absolute directory from its local
launcher. See [DD-047](../design-decisions/047-network-acp-virtual-workspace.md).

Collaboration and permission are independent under DD-044. React owns
`default` / `plan` workflow state. The Host advertises only `:read-only`,
`:workspace`, and, when authorized, `:danger-full-access`. A launch `--yolo`
flag exposes the bounded Full access profile only to an authenticated admin;
contacts do not inherit it.

## Transport scope

This preview is WebSocket-only. ACP Streamable HTTP requires HTTP/2, while the
current embedded Uvicorn server serves HTTP/1.1. An ordinary HTTP request to
`/acp` therefore returns `426` and names WebSocket as the supported transport.
ConnectOnion will not label an HTTP/1.1 approximation as ACP Streamable HTTP.

This direct profile is not end-to-end encrypted through an untrusted relay.
TLS protects a direct connection; a relay that terminates TLS can read it.
Signed `_meta` does not change that. Relay ACP remains blocked on the secure
channel design and review gates in issue #898.

The legacy `/ws` protocol remains available during the frontend migration. It
continues to carry CONNECT/INPUT/EXEC and compatibility ACP envelopes; it is
not itself an ACP connection. See [WebSocket Protocol](websocket-protocol.md)
and [DD-045](../design-decisions/045-authenticated-acp-websocket-gateway.md).

Frames are UTF-8 JSON-RPC text with a 1 MiB maximum. Ordinary binary frames are
ignored per the upstream RFD; malformed text and oversized frames close the
socket. Each direction uses an eight-message bounded queue;
backpressure is applied instead of silently dropping ACP messages. The first
`initialize` frame has a 10-second deadline. Host shutdown and disconnect
settle turns and release persistent session leases.

## Hosting another ACP Agent

`host()` enables the endpoint only when given an ACP factory:

```python
host(
    agent,
    acp_agent_factory=lambda principal: MyACPAgent(principal),
    acp_origins=["https://app.example.com"],
)
```

The factory receives the verified `ACPPrincipal`. Do not infer authority from
an ACP session ID or accept an Origin wildcard for browser tickets.
