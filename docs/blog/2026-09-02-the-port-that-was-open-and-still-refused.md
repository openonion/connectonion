# The port that was open and still refused

The Melbourne rental host got its firewall rule at 09:31. `curl` from the
laptop answered `200` on `:8001`, a bare WebSocket connected, and `co proxy
share` kept saying the same thing it had said with the port closed:

```text
reconnecting (the host is not reachable directly; retrying in 60s)
```

That is a bad message, and it has its own issue now. But the reason behind it
was a rule I had written myself. `endpoint_is_safe` rejects any public
endpoint that is not `https`. A self-hosted agent that announces
`http://34.129.161.131:8001` is, to the 1.8.0b1 client, not there.

## Why the rule existed

#649. A CONNECT frame is signed. On a plaintext link anyone who can see the
bytes can copy the frame, and for five minutes that copy opens the host's
whole whitelisted tool surface. TLS made the link private, so the rule was:
TLS, or loopback, or the relay. Every `co deploy` host gets a domain and Caddy
for exactly this reason.

The rental host was not deployed that way. It was provisioned by hand under
1.6, it runs a client's crawl every night, and nobody had a reason to give it
a domain — until the feature whose whole point is *that machine's own
connection* needed to reach it. Aaron's question was the right one: both
sides have keys. Why is a certificate authority involved at all?

## What changed

It is not. The address *is* the Ed25519 public key, so each side can already
verify the other with nothing it does not have. The direct socket now opens
with one extra exchange: each side sends a one-time X25519 key, signed by its
long-term identity, and from then on every frame — CONNECT included — is a
NaCl box with a per-direction counter.

```text
SEAL       {to, from, ephemeral, timestamp, signature}
SEALED_OK  {to, from, ephemeral, client_ephemeral, signature}
SEALED     {n, c}   ← everything after, both ways
```

A captured frame is now unreadable, and a replayed one fails to open because
the counter only goes up. The #649 property holds without TLS, and the relay
is not in the loop at all: it keeps forwarding control frames, which is what
it was for.

The client rule is the mirror image of the old one. Every direct socket is
offered a `SEAL`. A host that answers is used, plaintext or not. A host that
does not — a 1.7 host — is used bare only if the link is already private, or
if the client has no keys and therefore nothing signed to lose. Otherwise the
socket is closed and the client goes to the relay, as before.

## What it costs a host

One open port. No domain, no certificate, no Caddy, no port 80 for ACME. The
firewall rule the rental host got this morning is the whole provisioning step.

## What it does not fix

The port still has to be open. Two machines both behind NAT still have no
direct path, and that is a rendezvous problem for the decentralised layer,
not a cryptography one. The bad message — "not reachable directly" when the
truth was "reachable, refused by my own rule" — is #1387.
