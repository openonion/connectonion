# The page that must not load

This morning the two-machine run got further than it ever had. A laptop on a
home connection in Sydney attached to a Google Cloud server, `co remote-browser
start` came back `active`, and the browser on the server opened
`api.ipify.org` — and the page said `129.94.43.159`. The laptop's address.
Eight alphas of gateway, policy, private runtime and paid engine had finally
lined up, and the number on the screen was the right one.

That is the moment it is tempting to stop. The feature is "working". Cut the
beta, write the post, go to lunch.

## The second check

Instead we ran `co proxy stop` on the laptop and reloaded the tab on the
server.

The interesting outcome would not have been an error. It would have been a
page that loaded — showing `35.229.135.74`, the server's own address. Every
piece of the chain was built so that cannot happen: the Remote Browser is
pinned to the loopback gateway, the gateway dials only through the share, and
the share is gone. But "built so that cannot happen" is a claim about code,
and the earlier same-network demo had never tested it. If the browser had any
path back to the data centre's connection, this reload was the first time
anyone would have seen it — and a user would not have seen it at all. Their
tab would simply keep working, from the wrong country, while they believed
their traffic left from home.

```text
This site can't be reached
ERR_TUNNEL_CONNECTION_FAILED
```

The tab broke. That is the result the whole feature exists to produce, and it
is the first time it has been observed on two real machines rather than
asserted in a test.

## Why this is the beta

`1.8.0b1` is cut from this run. The successful number has been in the alphas'
notes since a3; the failing one had not. A beta is where the feature set stops
moving and other people run the path — and the one-line check they should
run is not "does the site see my address" but "does the tab die when I stop
sharing". Anyone who gets a page after `co proxy stop` has found a bug worth
more than every green matrix on this branch.

What is left before `1.8.0` is exactly that: the second and third run of this
path on machines nobody in this repository set up, and one run of the paid
engine by someone who had to top up first. The session that produced the
screenshot above cost $0.025.
