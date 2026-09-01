# A browser on a server, using your address

`co proxy share to <address>` is in 1.8.0a3. It lends this computer's internet
connection to one agent you authorize, and a remote browser session started
with `--proxy shared` reaches the internet through it.

```bash
co proxy share to 0xHOST                        # on your computer
co remote-browser 0xHOST start --proxy shared   # then start the session
```

The number that matters, measured across two real machines — a Google Cloud
server running the paid Chromium 151, a laptop in Sydney lending its
connection:

```text
the server's own address        34.21.243.229
what the site saw               129.94.43.159
```

## Lending a connection, not a network

The obvious way to build this is a forwarder: accept a connection, open a
socket, copy bytes. That version would also hand the remote caller your router's
admin page, whatever listens on `localhost`, and every other thing that answers
inside your house — and each of those requests would arrive from a machine that
trusts them.

So the share is not a forwarder. It is the same component as the browser's own
egress gateway — same parser, same authentication, same destination policy, same
limits — bound to a reachable address instead of loopback:

```text
CONNECT 192.168.0.1:80  →  403 DESTINATION_ADDRESS_DENIED
```

The check that keeps a remote caller off a server's private network turned out
to be, unchanged, the check that keeps it off yours.

## DNS moves too

The first implementation moved only the final socket: the server resolved the
hostname and asked the Laptop for one numeric address. That proved the public
IP, but it did not satisfy the product boundary. A server-side DNS lookup is
still a server-side network signal.

The next preview moves DNS to the Laptop as well:

```text
WTF Browser on server → Laptop DNS → both policies approve all answers
                      → Laptop connects the selected numeric address
```

The Laptop classifies the complete answer set before returning it. The remote
gateway classifies it independently. The Laptop classifies the selected numeric
address again before dialing. Neither side can widen the other's decision, and
Chromium never asks the server resolver for the target.

The same correction closes a second truthful-state bug: `start --proxy shared`
used to accept the Laptop endpoint and then persist `proxy_mode: direct`.
Runtime creation now writes one private Proxy binding before WTF Browser starts,
and a running runtime refuses a different exit. `co proxy stop` now stops the
live listener rather than only deleting its registry entry.

## What else is in this release

The boundary that makes the above safe to offer: a frozen destination policy
that classifies alternate address forms and special-use names, an authenticated
loopback gateway that owns DNS and dials only approved numeric sockets, a
Host-private browser runtime that keeps a remote caller's session out of the
browser holding your logins, and a preflight that makes the browser prove it
used the gateway before the first page opens.

Paid Onion Browser on Linux is a working customer path in this preview:
`co browser install-onion` bootstraps the runtime through a signed release
channel, and a paid session downloads and runs the exact Chromium 151 artifact.
A session now says what it costs when it starts.

## Try it

```bash
pip install connectonion==1.8.0a3
```

Preview releases are opt-in; `pip install connectonion` still gives you stable
1.7. Remote **navigation** is still switched off — `diagnose` reports
`navigation_policy: not_enabled` until the installed-artifact acceptance suite
finishes. The share is reachable on your own network today; carrying it across
networks still uses a tunnel you provide.
