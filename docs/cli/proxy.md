# co proxy

Lend this computer's internet connection to an agent you authorize.

A browser running on a server reaches the internet from a data-centre address.
Sharing your connection makes its traffic arrive from *here* instead:

```text
browser on the host  ──▶  your computer  ──▶  the internet (your address)
```

```bash
co proxy share to 0xHOST     # lend your connection to one agent
co proxy status              # what is shared right now
co proxy stop 0xHOST         # stop lending
co proxy diagnose 0xHOST     # why a share is not working
```

Then start the remote session against it:

```bash
co remote-browser 0xHOST start --proxy shared
```

`--proxy direct` (the default) keeps the host on its own connection.

## What gets shared, and what does not

**Shared:** an outbound path to the public web, for destinations the policy
already allows.

**Not shared:** the network behind your connection. The share applies the same
destination policy as the host's own egress gateway, so a remote agent cannot
reach your router, your NAS, a service on your laptop, or anything on your LAN
— those come back `403 DESTINATION_ADDRESS_DENIED`. Lending a connection is not
lending a network, and the check that keeps a remote caller off the host's
private network is the one that keeps it off yours.

Nothing reads your browser profile, cookies, files or credentials. The tunnel
carries bytes the remote browser already decided to send, and for HTTPS the TLS
session stays end to end — the share connects a socket and copies bytes; it
installs no certificate and sees no page content.

## DNS and the two decisions

In `shared` mode the remote server does not resolve browser destinations. Its
private gateway asks the Laptop Proxy to resolve the hostname. The Laptop
classifies the complete answer set first; the remote gateway independently
classifies the same set and selects one numeric address; then the Laptop
classifies that numeric address again before opening the public socket.

```text
WTF Browser: example.com
        ↓ no server DNS
Laptop DNS: 93.184.216.34
        ↓ complete answer set is accepted by both machines
CONNECT 93.184.216.34:443      ← final Laptop dial
```

This gives the remote WTF Browser the Laptop's DNS and public-IP boundary
without trusting either machine's decision alone. Chromium target DNS, QUIC and
non-proxied WebRTC UDP are disabled, and the browser has no Direct proxy
fallback.

## Options

| Option | What it does |
|---|---|
| `--json` | the complete stable envelope, for scripts and agents |
| `--bind HOST` | listen on a specific address (default: the one a peer reaches) |
| `--ttl SEC` | stop sharing automatically after this long |

`co proxy stop` sends an authenticated stop request to the live service, waits
for its listener to close, and only then reports success. Deleting stale state
is not treated as stopping a Proxy.

`co proxy share` picks its own address by asking the routing table which
interface reaches the internet. On a machine with several interfaces, or behind
a NAT where the peer arrives somewhere else, set `--bind` yourself;
`co proxy diagnose` tells you when the bound address and the reachable one
differ.

## Reaching your share from outside your network

A share listens on this machine. An agent on another network needs a path to
it — a port forward, a VPN, or a tunnel you already run. `co proxy diagnose`
prints the address a peer would use, which is where to point that path.

The first preview intentionally keeps this two-machine model. A later transport
may make `share to` create its own outbound reverse path through the remote
Agent; that is not silently claimed by the current listener implementation.

## Verified

A browser on a Google Cloud server, launched with the private egress policy and
no direct fallback, egressing through a laptop in Sydney:

```text
the server's own address        34.21.243.229
what the site saw               129.94.43.159   (the laptop's)
```

The same request without the share reports the server's address, which is the
whole reason this command exists.
