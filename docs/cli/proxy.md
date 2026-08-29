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

## How the two hops divide the work

The host resolves the hostname, classifies **every** address the lookup
returns, and pins one numeric address — exactly as it does without a share.
Only the last hop changes: instead of dialing that address itself, it asks your
share for that same numeric address.

```text
CONNECT 93.184.216.34:443      ← what the host asks your share for
CONNECT example.com:443        ← what it never asks
```

That matters. If the host forwarded the hostname, your share would resolve it a
second time and could land somewhere the host never approved. Your share then
applies its own policy to the address it was given, so a destination has to
pass **both** machines.

## Options

| Option | What it does |
|---|---|
| `--json` | the complete stable envelope, for scripts and agents |
| `--bind HOST` | listen on a specific address (default: the one a peer reaches) |
| `--ttl SEC` | stop sharing automatically after this long |

`co proxy share` picks its own address by asking the routing table which
interface reaches the internet. On a machine with several interfaces, or behind
a NAT where the peer arrives somewhere else, set `--bind` yourself;
`co proxy diagnose` tells you when the bound address and the reachable one
differ.

## Reaching your share from outside your network

A share listens on this machine. An agent on another network needs a path to
it — a port forward, a VPN, or a tunnel you already run. `co proxy diagnose`
prints the address a peer would use, which is where to point that path.

## Verified

A browser on a Google Cloud server, launched with the private egress policy and
no direct fallback, egressing through a laptop in Sydney:

```text
the server's own address        34.21.243.229
what the site saw               129.94.43.159   (the laptop's)
```

The same request without the share reports the server's address, which is the
whole reason this command exists.
