# One open port

The rental host in Melbourne was never meant to be a test machine. It runs a
client's nightly crawl on the smallest instance Google sells, it was set up by
hand in the 1.6 days, and it has no domain because nothing ever needed one.
Which is exactly why it was the right second machine for 1.8: nobody in the
repository had prepared it for this.

At 09:31 it got a firewall rule for port 8001. At 09:33 the laptop said the
host was not reachable directly, and the port was demonstrably open. The
morning's post covers why — the client refused plaintext on principle, and
the principle was right. By 11:20 the same laptop had a page open on that host
showing its own home address, over the same plaintext port, with the socket
sealed end to end and no certificate anywhere in the path.

## What the second machine taught

The first pair — a laptop and a fresh `co server new` box — proved the
feature. The second pair proved the *provisioning*, and it did so by having
none. Two things went wrong on it, and neither was the feature.

The sealed socket did not support `async for`. Every unit test passed because
every unit test called `recv()`; the share's frame reader iterates. One live
run found it in a second, and it now has a test that iterates.

The host ran out of memory. Not because of anything 1.8 did: yesterday's crawl
had left a Chromium renderer holding 645 MB for 27 hours under a browser
daemon nobody had stopped, and an e2-small has 2 GB. The paid engine's Chrome
could not start, and the preflight said only that the egress boundary "could
not be proven". Killing the stale daemon freed a gigabyte and the next session
went straight through. `dmesg` showed the crawl's own Chrome had been
OOM-killed twice this week already; that is the rental project's problem to
solve, but it is the kind of thing a stable release should know about itself.

## Why this is 1.8.0

The policy says a `.0` is earned by being run end to end by people who did not
build it, on machines they did not prepare. The Melbourne run is one machine
of that kind, and the person who asked for it made the call that the basic
path is proven. The number on the page was the laptop's; the tab died when
the share stopped; the host's real workload kept running underneath. That is
the whole product, measured twice today on two different kinds of host.

What 1.8.0 does not claim: both machines behind NAT (still needs a rendezvous,
2.5), a relay path that is end-to-end encrypted (it is not; direct sockets
are), and a diagnose command that names the endpoint it could not reach
(#1387, next patch).
