# The gateway held, but the answer leaked

The egress gateway is the piece that makes remote browsing safe to offer: a
loopback proxy that Chromium is launched against with no direct fallback, which
resolves every hostname itself, checks every address the lookup returns, and
dials only a numeric address it already approved. If it has a hole, a stranger
reaches your private network through your own browser.

So before merging it I had an independent pass try to break it, with one
instruction: find a byte that reaches an unapproved socket.

It could not. Not through DNS rebinding on a new connection — the gateway
re-resolves and re-classifies each time, and answering `8.8.8.8` first and
`127.0.0.1` second gets the second connection refused with no dial. Not through
the 26 request-parsing tricks it tried: bare-LF request smuggling, duplicate
`Host`, obs-fold continuations, `Content-Length` fighting `Transfer-Encoding`,
`http://example.com@169.254.169.254/`, a CR buried in a header value. Not
through the authentication path, which is checked before resolution on every
route and has no second-request branch to skip. Not through the resolver, which
denies a whole answer set if any member is private. The property the module
exists for held.

What it found instead was on the way back.

## The response was never ours to relay

The gateway serves exactly one request per connection. After that it stops
reading, and the connection is finished — from its point of view.

It never told the client that. The upstream response went through a raw byte
pump: read bytes, write bytes, no parsing, no rewriting. So when a hostile
origin answered

```
HTTP/1.1 200 OK
Content-Length: 0
Connection: keep-alive

HTTP/1.1 200 OK
Content-Length: 8

smuggled
```

both responses reached the client, and the client had been told the proxy socket
was reusable. Chromium pools plain-HTTP proxy sockets by *proxy server*, not by
origin. A second response sitting in the receive buffer of a socket the client
believes it can reuse for a different origin is the shape of a
response-smuggling bug.

The documentation, meanwhile, said the gateway "forces `Connection: close`." It
did — on the request going *upstream*. Nobody had asked what the client saw.

The fix is to rewrite the response head as well: drop `Connection`,
`Keep-Alive`, `Proxy-Connection`, append `Connection: close`, then pump the
body. Now the one-request-per-connection rule is visible to the client instead
of being merely true inside the gateway.

## Two more, both from trusting a number a stranger chose

`Content-Length` sized a `readexactly()`. One connection declaring 64 MiB grew
resident memory by 227 MB before a byte moved; the connection cap multiplies
that. The transfer limit was there — 128 MiB — but a limit on total bytes
transferred is not a limit on bytes held at once. Streaming in chunks makes the
declaration irrelevant to memory.

And admission counted connections before reading any of them. Four TCP
connections that sent *nothing* — no credential, no request — filled a
four-connection gateway and made an authenticated `CONNECT` return
`429 Too Many Requests`, for the full header timeout, renewably. The credential
was checked carefully and then handed a queue that anyone could fill. Pending
sockets now have their own budget and only convert to a served slot once the
credential is proven.

## The test that would have passed on the bug

One more thing worth recording. There is a test named
`test_numeric_dialer_never_calls_getaddrinfo` — the anti-TOCTOU property, the
single most important thing this module does. The reviewer replaced the entire
body of `dial_numeric` with the bug it names, resolving by name instead of
dialing a pinned address.

All 37 tests still passed.

The test feeds an already-numeric string, and asyncio short-circuits numeric
strings before it reaches the patched resolver. The property is genuinely
enforced — by a different function, checked by a different test — but the test
that reads like the guard is not the guard. That is worse than no test, because
the name tells the next reader the question has been answered.

Nothing in the suite asserted anything about the response the client receives,
either, beyond its status line. Which is exactly why the smuggling window was
invisible: the tests watched everything going out and nothing coming back.
