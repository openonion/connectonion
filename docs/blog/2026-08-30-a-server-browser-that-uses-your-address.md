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

## One hop moves, and only one

The host resolves the hostname, classifies every address the lookup returns, and
pins one numeric address — exactly as it does with no share involved. Then it
asks your machine for that same numeric address:

```text
CONNECT 93.184.216.34:443      ← what the host asks your share for
CONNECT example.com:443        ← what it never asks
```

If it forwarded the hostname, your machine would resolve it a second time, and
the address it dialed could differ from the one the host approved. Your share
then applies its own policy to what it was handed, so a destination has to pass
both machines.

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
