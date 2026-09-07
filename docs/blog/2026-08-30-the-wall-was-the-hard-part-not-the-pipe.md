# The wall was the hard part, not the pipe

A browser on a server has a data-centre address, and a lot of the web treats
that differently from a home connection. So the plan was always that the
browser runs on the server and reaches the internet through your own machine:

```text
browser on the host  ──▶  your computer  ──▶  the internet (your address)
```

For weeks the work that went into this looked like it was about something else
entirely. Five pull requests, all about refusing things: a policy that
classifies every address a DNS lookup returns, a loopback gateway the browser
cannot get around, a private runtime so a remote caller's session never sits in
the browser holding your logins, a preflight that makes the browser prove it
actually used the gateway, and the paid engine pinned to all of it.

None of that gives you a residential address. It is a wall.

The pipe — the part that actually changes the address — took an afternoon.

## Why that ordering was not a mistake

Point a server's browser at your laptop without the wall and you have not lent
it your internet connection. You have lent it your network. Your router's admin
page answers on your LAN. So does whatever is on `localhost`. So does the NAS.
A page the remote caller controls can ask for any of them, and every one of
those requests now originates from inside your house.

The destination policy that keeps a remote caller off the *host's* private
network is, unchanged, the thing that keeps it off yours. That is why the share
is not a forwarder. It is the same gateway — same parser, same authentication,
same policy, same limits — bound to a reachable address instead of loopback:

```python
self._gateway = EgressGateway(
    username="connectonion-proxy",
    password=credential,
    bind_host=bind_host or local_egress_address(),
)
```

One parameter. Everything else was already there, and had already been attacked
five times.

## The one design decision worth stating

The host still resolves the hostname itself, classifies every address the
lookup returns, and pins one numeric address. Only the last hop moves: instead
of dialing that address, it asks your share for that *same numeric address*.

```text
CONNECT 93.184.216.34:443      ← what the host asks your share for
CONNECT example.com:443        ← what it never asks
```

If it forwarded the hostname, your share would resolve it a second time, and
the address your machine dialed could differ from the one the host approved.
That is the same time-of-check/time-of-use gap that made us build a socket
boundary instead of a URL check in the first place — it would have walked right
back in through the new door.

Your share then applies its own policy to the address it was handed, so a
destination has to pass both machines. Neither one trusts the other's decision.

## Proof, not architecture

Two machines, both real: a Google Cloud box in Iowa running the browser, a
laptop in Sydney lending its connection.

```text
the server's own address        34.21.243.229
what the site saw               129.94.43.159
```

The second number is the laptop's. The browser was launched with the full 1.8
private policy — fixed loopback proxy, no direct fallback, browser-side DNS
disabled, QUIC and non-proxied WebRTC UDP off — and it was the real paid
Chromium 151, downloaded through the signed release channel on the server, not
a system Chrome standing in for it.

Then the sharper test, the one that says whether the wall survived the pipe:
ask the share for something on the sharer's own network.

```text
CONNECT 192.168.0.1:80  →  403 DESTINATION_ADDRESS_DENIED
```

Lending a connection, not a network. That distinction is what the five refusing
pull requests bought, and it is why the afternoon that added the pipe was an
afternoon and not a rewrite.
