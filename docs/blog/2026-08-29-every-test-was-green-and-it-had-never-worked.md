# Every test was green and the feature had never worked once

The native egress preflight is the part of Remote Browser that refuses to
start. Launching Chromium behind a loopback proxy proves nothing on its own —
the process starting successfully says nothing about which socket the next
request goes out of — so before the first page is opened, the preflight makes
the browser prove it: navigate somewhere the gateway must refuse, then check
that the refusal came from the gateway, then check that a loopback sentinel
saw no connections at all.

Its tests passed. All of them, every run. And it had never once succeeded
against a real browser.

## Two facts nobody had put together

The first probe asks for `http://remote-browser-preflight.invalid/`. The
reasoning is good: `.invalid` is reserved never to resolve, so a browser that
resolved names itself would fail locally, while a browser going through the
gateway gets the gateway's DNS failure. The code required status 502.

The gateway answers **403**. Its destination policy denies `.invalid` by name,
before DNS is ever consulted — the very special-use suffix list that another
review had hardened a day earlier. The 502 path exists, but only for a host the
policy *admits* and that then fails to resolve. The witness could never fire.

The second is smaller and worse. The gateway's refusals are sent with
`Content-Length: 0`. Chromium will not commit a bodyless 4xx or 5xx main-frame
navigation — it reports `ERR_HTTP_RESPONSE_CODE_FAILURE`, so `page.goto` raises
instead of returning a response:

```
403 empty body -> ERR_HTTP_RESPONSE_CODE_FAILURE
403 with body  -> status=403
```

The preflight catches every exception and collapses it to
`EGRESS_PREFLIGHT_FAILED`. So even with the status expectation corrected, both
probes raise, and the private browser can never start.

Fail-closed, which is the right direction to be broken in. But a boundary that
can only ever refuse is not a boundary; it is an outage with good manners.

## Why the tests could not see it

The suite drives a `FakePage`. `FakePage.goto` returns a response object where
real Chromium raises, and its constructor hard-codes `witness_status=502` —
the status the real gateway never sends. The fake modelled two behaviours the
real stack does not have, and the tests then verified the fake.

There was no test anywhere that ran this preflight against a real browser.

## The absence that proved nothing

There was a third problem, and it is the one worth remembering.

The subresource half of the proof — fetch, image, WebSocket, worker — runs
inside a bounded race that swallows each probe's own errors, by design: a probe
that fails is a probe whose request was correctly refused. Then the sentinel is
asked whether it accepted any connections, and zero means the browser never
went direct.

Zero also means the probe never ran. A wrong URL, a blocked API, an `await`
that resolves on the timer — every one of those produces the same zero as a
perfectly proxied request. Replacing the entire subresource function with
`async def noop(): return None` leaves the preflight passing.

An absence is only evidence once the thing that would have produced a presence
is known to have run. The gateway now counts the requests it has decided, and
the preflight reads that count before and after: the sentinel's zero means
something only when the gateway's counter moved.

That is also the fix for a subtler version of the same gap. The old check read
the counters 1.6 seconds after starting the probes and tore the sentinel down
immediately after; a leak whose socket landed at two seconds was invisible, and
worker startup on a cold Chromium can take longer than that. Requiring positive
evidence removes the dependence on a window.

## What it takes to believe a security check now

Three properties, and each was verified by breaking it:

- remove the positive control → the neutered-probe test goes red
- remove the gateway-witness header check → the foreign-403 test goes red
- put the error body back to empty → the real-driver test goes red

And the real-driver test itself runs both ways: it passes against a correct
launch with all seven probes reaching the gateway, and it still fails when
`<-loopback>` is replaced with a real loopback bypass. Passing alone would only
prove the check is lenient.

The preflight was green for its entire life without ever having worked. The
thing that finally told us was not a better assertion. It was running it.
