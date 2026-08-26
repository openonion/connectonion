# Remote Browser egress gateway

Remote Browser navigation is not exposed yet. Before it can be, the Host must
own the last security decision before a destination socket is opened. The
internal `EgressGateway` is that boundary: an authenticated HTTP/CONNECT proxy
bound to one ephemeral IPv4 loopback port.

The design and threat model live in [DD-056](../design-decisions/056-remote-browser-egress-gateway.md).
This page records the executable contract of the first gateway implementation.

## Connection path

```text
one authenticated loopback proxy connection
             |
             v
bounded request headers -> normalized authority -> one bounded DNS lookup
                                                    |
                                                    v
                                      classify the complete answer set
                                                    |
                              deny any prohibited address; otherwise
                                                    |
                                                    v
                                numeric family + sockaddr -> TCP socket
```

Chromium does not consume this component in this PR. There is no public OIP
command, daemon launch flag, or fallback path. A disabled or failed gateway
therefore leaves navigation unavailable.

## Authentication and lifetime

Each gateway instance creates a 32-byte URL-safe random password unless its
owning daemon injects one. The username and password become a Basic proxy
authorization value. The complete value is compared with
`hmac.compare_digest`; missing, wrong, or duplicate authorization fails before
resolution or dialing. `Proxy-Authorization` and `Proxy-Connection` are never
forwarded upstream.

Credentials live only with the gateway instance. A restarted Host-private
daemon creates a different gateway and credential. The later BrowserDaemon
integration must pass these values directly to the private browser context and
must not write them into the session registry, logs, diagnosis, or command
results.

## Accepted protocol

- `CONNECT host:port HTTP/1.1` creates one tunnel pinned to one approved numeric
  peer. An explicit safe port is required.
- Absolute-form `http://` and `ws://` HTTP/1.1 requests are normalized, checked
  against `Host`, rewritten to origin-form, and sent to one approved peer.
- Ordinary HTTP forces `Connection: close` and forwards only the declared
  `Content-Length`, so pipelined bytes cannot introduce another authority.
- A valid `GET` Upgrade may become a bidirectional tunnel to the same peer.
- Chunked request bodies, `Expect`, origin-form proxy requests, SOCKS, UDP,
  non-web schemes, ambiguous framing, and security-sensitive `Connection`
  tokens are rejected in the initial boundary.

All input headers must be visible ASCII with a valid token name. Duplicate
`Host`, proxy authorization, content length, transfer encoding, connection, or
upgrade semantics fail closed where applicable.

## Resolution and socket pinning

IP literals skip DNS. A hostname is resolved exactly once per new inbound
connection with `getaddrinfo(AF_UNSPEC, SOCK_STREAM, IPPROTO_TCP)`. The gateway
canonicalizes every returned address and applies the frozen destination policy;
one prohibited answer denies the complete set.

Approved strings are converted into `NumericEndpoint` values. That type rejects
hostnames, alternate textual IP forms, family mismatches, and invalid ports.
The production dialer creates a socket with the fixed family and calls
`loop.sock_connect()` with the numeric sockaddr before wrapping the connected
socket in asyncio streams. A failed approved candidate may try another member
of the same already-resolved approved set. It never resolves again and never
falls back to Direct.

## Default limits

| Boundary | Default |
| --- | ---: |
| Complete request headers | 16 KiB |
| Request line | 4 KiB |
| Header count | 100 |
| Header read timeout | 5 seconds |
| DNS timeout | 5 seconds |
| Numeric connect timeout across the frozen answer set | 10 seconds |
| Tunnel idle timeout per read/drain | 60 seconds |
| Bytes per direction | 128 MiB |
| Concurrent inbound connections | 32 |
| DNS answers before refusal | 32 |

Every configured limit must be finite, positive, and of the expected integer or
duration type. Overload is rejected before parsing, authentication, resolution,
or dialing. Shutdown closes admission, cancels owned resolver/tunnel tasks, then
waits for the listener; this ordering is required by Python 3.14's stronger
`Server.wait_closed()` semantics.

## Stable failures and privacy

The proxy returns an empty HTTP response with a constant status and
`X-ConnectOnion-Error` code when no application response has started. Initial
codes are:

- destination policy: `DESTINATION_INVALID`, `DESTINATION_SCHEME_DENIED`,
  `DESTINATION_PORT_DENIED`, `DESTINATION_HOST_DENIED`,
  `DESTINATION_DNS_FAILED`, `DESTINATION_ADDRESS_DENIED`;
- gateway boundary: `EGRESS_HEADER_TIMEOUT`, `EGRESS_HEADER_TOO_LARGE`,
  `EGRESS_AUTH_REQUIRED`, `EGRESS_OVERLOADED`, `EGRESS_CONNECT_FAILED`,
  `EGRESS_TRANSFER_LIMIT`, `EGRESS_GATEWAY_STOPPING`.

Once a tunnel or upstream response may have emitted bytes, a later failure only
closes the connection. Appending a second HTTP response would create a request
smuggling ambiguity.

Failures never echo the normalized host, URL path/query/fragment, credentials,
headers, cookies, resolver payload, or page bytes. The future bounded decision
ledger will store a daemon-keyed hostname hash; this transport does not log or
persist one.

## Verification boundary

Focused tests use injected resolvers and dialers so public policy decisions can
drive real loopback protocol servers without adding a private-network allow
exception. They assert zero dial on authentication, parsing, policy, DNS,
overload, and cancellation failures; exact header/body forwarding; CONNECT and
WebSocket byte flow; numeric-only socket creation; retry only inside one frozen
answer set; byte limits; and deterministic task/socket cleanup.

The next child must give BrowserDaemon a Host-private namespace/profile and
prove Chromium cannot bypass this gateway. Until that native preflight passes,
Remote Browser remains lifecycle-only.
