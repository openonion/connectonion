# A release talks to production

`co browser install-onion` on a fresh server installed Onionwright 0.0.12,
`co remote-browser start` reported the session up, and the first page never
loaded. The error was `EGRESS_PREFLIGHT_FAILED`, which says nothing. Under it,
after instrumenting the host, was a 403 from our own API: *spending requires an
Agent-signed authorization.* The server had started demanding a signature that
no client we had ever shipped could produce.

So we shipped one. Onionwright 0.0.13 signs the spend challenge with the
agent's own key, and ConnectOnion now installs and requires 0.0.13.

## The default that pointed the wrong way

There was a second bug hiding behind the first. The unreleased 0.0.13 client
defaulted to the *preview* channel — reasonable while every build of it was a
`.devN`. Installed on a production server it asked `browser-preview` for a
manifest, was told the channel did not match, and reported `manifest_invalid`.
The channel that could have authorized the spend was never contacted.

The server already pairs version shapes with channels: `X.Y.Z` is production,
`X.Y.Z.devN` is preview. The client now derives its default the same way, from
its own version string. A release build talks to production without anyone
passing a flag; a dev build talks to preview. `release_channel=` still exists
for the case where you mean it.

## No compatibility shim

The old clients are not kept working. Onionwright has no consumers outside this
repository yet, so a compatibility layer would have been code protecting nobody.
The production catalogue simply gained one entry, and ConnectOnion's pin moved
from 0.0.12 to 0.0.13.

## Measured

The two-machine Remote Browser acceptance — a laptop behind a home router
lending its connection to a browser on a GCP host — had been stuck at exactly
this point: attached, session started, page blocked. With a client that can
pay, the run went through in one sitting:

```text
Mac egress            129.94.43.159
host egress           35.229.135.74
tab → api.ipify.org   129.94.43.159
tab → ifconfig.me/ip  129.94.43.159
co proxy stop; reload ERR_TUNNEL_CONNECTION_FAILED
/api/v1/usage         total_cost_usd: 0.025
```

The last two lines are the ones worth keeping. Stopping the share breaks the
tab instead of quietly sending it out of the data centre, and a session that
lived a few minutes cost exactly one interval. The docs now carry this run in
place of the earlier same-network figure.
