# The laptop dials out

`co proxy share` opened a listening socket on your laptop and told the browser
host where it was. On a laptop that lives behind a home router, that address is
`192.168.x.x`, and the host is a server in a data centre. The share came up,
printed "sharing", and the host could not reach it. The only setups where it
worked were the ones where both machines were on the same network — which is
to say, the demo, and nothing anyone would pay for.

The product is that a browser on a server leaves the internet from your
address. The one machine involved that can never accept a connection is yours.

## Reverse the arrow

Nothing listens on the laptop any more. It dials the host over the same direct
WebSocket every `co` command already uses, presents a grant, and stays on the
socket. From then on the host sends work *down*:

```text
host → laptop   {"type":"PROXY_STREAM","id":7,"op":"resolve","host":"example.com","port":443}
laptop → host   {"type":"PROXY_STREAM","id":7,"op":"resolve","addresses":["93.184.216.34"]}
host → laptop   {"type":"PROXY_STREAM","id":8,"op":"connect","address":"93.184.216.34","port":443}
laptop → host   {"type":"PROXY_STREAM","id":8,"op":"connect"}
both            {"type":"PROXY_STREAM","id":8,"op":"data","data":"<base64, ≤32 KiB>"}
```

One socket, many streams, six ops. A home router is happy to let an outbound
connection through and keep it open; that is the only thing it is good at.

## What did not change

The browser host's egress gateway still speaks CORESOLVE and numeric CONNECT
to a "share endpoint". That endpoint is now a second gateway on loopback in
the host process, whose resolver and dialer are the channel. The daemon, the
pinned `shared-proxy.json`, the double classification, the frozen deny table:
untouched. The share moved from a socket on the laptop to a socket in the
host, and the gateway did not notice.

The laptop end runs the same `EgressGateway` too — never started, used only as
the policy. Every `resolve` and every `connect` the host asks for goes through
the same classifier the laptop's own listener would have applied. Lending a
connection still does not lend the network behind it.

## What has to be true for the attach to happen

The socket is the one `CONNECT` authenticated, so the host knows who is on it.
The attach carries a grant signed by that same identity, naming the host as
the holder. The host checks: authenticated, signed commands on, direct
transport (the relay would carry every byte of every page through
`oo.openonion.ai`, and a share only exists on a direct socket), trust at least
`contact`, grant verifies, grantor is the socket's identity. Any one of those
missing is a refusal with the reason, before a gateway is opened.

A `start --proxy shared` from that identity finds its own channel by address.
There is no channel to find when the laptop has not attached, and the answer
is `REMOTE_SESSION_PROXY_NOT_ATTACHED` with the one command that fixes it,
`co proxy share`. The laptop-side precheck that used to guess at this is gone;
the host is the authority on what is attached to it.

## The socket is the lifetime

The channel is registered when `PROXY_ATTACH` is accepted and detached in the
session's `finally`. When the laptop closes the lid, the socket drops, the
channel closes, and every stream on it fails with `PROXY_DETACHED`. The
browser's next request through the shared gateway gets a refusal, not a
fallback to the host's own connection — the fail-closed rule from DD-056 is
enforced by the socket going away, which is the one event nobody can forget
to handle.

`co proxy share` reconnects with backoff (1 s doubling to 60 s), minting a
fresh grant with the *original* expiry. A reconnect must not quietly extend
the TTL the operator asked for.

`--bind` is gone; there is nothing to bind. `--ttl` stays, default 24 h.

Measured: nine unit tests on the channel, one in-process end-to-end test with
a real `run_ws_session` behind `websockets.serve` and a real `EgressGateway`
on both ends, where the origin sees the laptop side. All red before the
change. The two-machine run — a GCP host, this Mac behind home NAT, no ports
opened — is the acceptance for `1.8.0b1` and is reported separately.
