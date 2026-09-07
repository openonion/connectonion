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

Every address above is optional once `co remote-browser config 0xHOST` has
remembered one; `co proxy share`, `stop` and `diagnose` then use it.

## How it connects

Your computer dials the host — nothing listens here, so it works from behind
a home router or a hotel NAT without port forwards or tunnels. `co proxy
share` opens the same direct, signed WebSocket `co remote-browser` uses,
attaches with a grant you sign (naming the host and an expiry), and then
serves the host's requests over that socket: resolve this name, connect to
this address, here are the bytes.

```text
your computer ──dials──▶ host        PROXY_ATTACH  (signed grant)
your computer ◀──────── host         PROXY_STREAM  resolve / connect / data
```

The command keeps running while the share is attached. If the socket drops it
reconnects with backoff (1 s, 2 s, ... up to 60 s) and re-attaches with a grant
carrying the same expiry; `co proxy status` shows `attached` or `reconnecting`
while that happens. The share ends when you stop it, when `--ttl` runs out
(default 24 h), or when the process exits.

Only a direct connection is accepted. The relay carries control frames, not
page bytes; if the host is reachable only through the relay the share reports
that and keeps retrying.

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
| `--ttl SEC` | stop sharing automatically after this long (default: 24 h) |

`co proxy stop` sends an authenticated stop request to the live share, waits
for it to detach and exit, and only then reports success. Deleting stale state
is not treated as stopping a share.

`co proxy diagnose` distinguishes "never shared", "the share process is gone"
and "the process is alive but not attached right now" — each with the one
command that fixes it.

## Security

- **You sign the grant.** The attach carries a grant signed by this computer's
  identity, naming the host as holder with an expiry. The host refuses a grant
  for another host, an expired one, or one signed by anyone other than the
  identity on the socket — so a copied grant is useless to whoever copied it.
- **Only your own sessions use it.** The host keys attached shares by your
  address. `co remote-browser start --proxy shared` from your identity uses
  your share; nobody else's session can.
- **Signed one way, TLS both ways.** Your frames to the host are Ed25519-signed
  like every other command. The host's frames back to you are not signed: they
  arrive inside the TLS session you opened to an endpoint whose identity you
  already verified, and no one else can inject into that socket.
- **Bounded.** Streams per share and bytes per frame are capped; a grant's
  `max_bytes` and `expires_at` are enforced on the host, and the share stops
  itself at `--ttl`.
- **Policy on both ends.** Every destination is classified on the host and
  again on your computer. Your LAN stays yours.

## Verified

A browser on a Google Cloud server, launched with the private egress policy and
no direct fallback, egressing through a laptop in Sydney:

```text
the server's own address        34.21.243.229
what the site saw               129.94.43.159   (the laptop's)
```

The same request without the share reports the server's address, which is the
whole reason this command exists.
