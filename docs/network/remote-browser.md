# Remote Browser (1.8 preview)

Run a browser on someone else's computer, from yours.

A ConnectOnion address can host a browser that you drive over an authenticated
connection. The browser's cookies and profile stay on the host; you get a
session that belongs to you and nobody else.

```bash
co remote-browser 0xHOST start      # claim a session
co remote-browser 0xHOST sessions   # list yours
co remote-browser 0xHOST status  rb_0123456789abcdef0123456789abcdef
co remote-browser 0xHOST stop    rb_0123456789abcdef0123456789abcdef
```

That is the whole surface today. `start` is safe to retry: the same owner and
request ID gets the same session back rather than a second one.

The session opens a visible window by default, exactly like `co browser` on
your own machine; a host with no display runs headless by itself. Pass
`--headless` to ask for that explicitly.

The address is 42 characters and never changes between calls, so remember it
once and leave it out afterwards:

```bash
co remote-browser config 0xHOST --proxy shared   # once
co remote-browser start                           # from now on
co remote-browser sessions
```

An explicit address still wins when you give one. With nothing remembered and
no address on the command line, the command stops and tells you to run
`config` — it never guesses a host.

## Reaching the internet through your own connection

A browser on a server reaches the internet from a data-centre address. Lend it
yours and pages see your address instead:

```text
browser on the host  ──▶  your computer  ──▶  the internet (your address)
                          co proxy share to <address>
```

```bash
co proxy share to 0xHOST                        # on your computer
co remote-browser 0xHOST start --proxy shared   # then start the session
```

Or, after `co remote-browser config 0xHOST --proxy shared`, the same two
commands with nothing to type: `co proxy share` and `co remote-browser start`.

Measured on a Google Cloud server egressing through a laptop in Sydney: the
server's own address is `34.21.243.229`, and the site saw `129.94.43.159`.

`--proxy direct` (the default) keeps the host on its own connection. Asking for
`shared` without a share endpoint answers `REMOTE_SESSION_SHARE_MISSING` rather
than quietly falling back — a silent fallback would send traffic from the data
centre while you believed it left from home. Any other mode answers
`REMOTE_SESSION_PROXY_LOCKED`.

Both machines apply the destination policy, so sharing a connection does not
share the network behind it. See [co proxy](../cli/proxy.md).

The selection is pinned when the WTF Browser runtime is created. One running
runtime cannot mix `direct` and `shared`, or two different Laptop exits. A
change requires a new runtime; losing the Laptop Proxy never falls back to the
server's datacentre address.

## Scripting it

`--json` returns a stable envelope on every command — `schema_version`, `ok`,
`command`, `request_id`, `summary`, `result`, `state`, `tips`, `warnings`,
`next_actions`, plus `code`, `message`, `retryable` and `retry_after_seconds`
when something fails. Branch on `ok` and `code`, never on English text. Local
validation failures use the same envelope, so `--json` never writes usage text
to stderr.

The Python async API returns a `TIMEOUT` envelope when its deadline expires.
Cancelling the calling task stays ordinary Python cancellation — it raises
`asyncio.CancelledError` rather than becoming a retryable remote failure.

## Diagnosing

`co remote-browser 0xHOST diagnose <session>` reports what the session can and
cannot do right now, including `navigation_policy`. Use it before assuming a
command is broken; several capabilities are deliberately switched off in this
preview.

---

## Security

### Page commands are switched off on purpose

`diagnose` reports `navigation_policy: not_enabled`, and there is no `open` or
`do` for a remote session yet. Use local `co browser` for page actions
meanwhile.

The reason is that checking the submitted URL does not hold. Between the check
and the connection, the browser resolves DNS and dials on its own, so the
address it reaches can differ from the address that was approved. Redirects,
iframes, images, `fetch`, WebSockets and downloads each open their own
connections that the first check never saw.

### What replaces the URL check

Navigation will be authorized at the socket, not at the URL. The host runs a
loopback egress gateway and starts the browser with no way around it: every
HTTP, HTTPS, WebSocket, worker, subresource, redirect and download connection
goes through the gateway. In `direct` mode the host gateway resolves and dials.
In `shared` mode the Laptop resolves the name and opens the final socket; both
machines classify the complete answer set before one numeric address is used.

```text
remote command ──▶ Remote Browser service ──▶ host-private browser
                                                     │ fixed loopback proxy,
                                                     │ no direct fallback
                                                     ▼
                                       egress gateway 127.0.0.1:<port>
                                       classify · direct/shared transport
                                                     ▼
                                             the public internet
```

The invariant: **no byte leaves for a browser-chosen destination until the exact
socket address for that connection has passed the destination policy.** If any
address in a DNS answer is private, the whole request is denied — so a lookup
cannot return a public address on the first try and a private one on a retry.
If the gateway dies, the browser loses its connection; it never falls back to
direct.

What this protects: loopback and link-local addresses, private and unique-local
networks, carrier-grade NAT, cloud metadata endpoints, reserved ranges, and
whatever ranges and ports the operator adds. These are the things a host can
reach but a remote caller was never meant to see — and the same policy protects
your home network once `--proxy shared` sends that traffic through your laptop.

The remote browser runs as a separate instance from your local `co browser` —
same code, its own profile and socket namespace. Two reasons: a remote caller's
session must not sit in the browser holding your logins, and Chromium's proxy
setting is per-browser, not per-tab, so pinning the gateway on your everyday
browser would cut off your own local browsing. The namespace, profile, IPC
credential and gateway are described in
[Remote Browser private runtime](remote-browser-private-runtime.md); that
isolation is the runtime boundary navigation needs, not navigation itself.

TLS stays end to end. The gateway installs no root certificate and reads no page
content; for `CONNECT` it dials the approved address while the browser's own
handshake keeps the original hostname for SNI and certificate checks.

Failures are stable codes, not prose: `DESTINATION_ADDRESS_DENIED`,
`DESTINATION_REBINDING_BLOCKED`, `DESTINATION_DNS_FAILED`,
`EGRESS_GATEWAY_UNAVAILABLE` and their siblings. A denied subresource does not
hand its URL back to the caller; it increments a counter visible through
`diagnose`.

### Transport

This preview accepts direct OIP transport only. A Relay path answers
`SECURE_CHANNEL_UNAVAILABLE` until the reviewed OIP secure channel lands. It
never downgrades to plaintext browser control.

Session IDs are identifiers, not secrets. Listing, status, diagnosis and stop
are all filtered by the OIP identity that completed CONNECT, so holding another
owner's session ID grants nothing. Stop is idempotent and leaves a tombstone as
reconnect evidence.

---

[DD-055](../design-decisions/055-owner-bound-remote-browser-lifecycle.md) is the
lifecycle decision; [DD-056](../design-decisions/056-remote-browser-egress-gateway.md)
is the egress gateway design and its executable negative-vector plan.
