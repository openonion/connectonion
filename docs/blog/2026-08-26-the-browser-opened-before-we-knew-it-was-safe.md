# The Browser Opened Before We Knew It Was Safe

*2026-08-26*

The private BrowserDaemon had a careful launch policy. Chromium received one
loopback proxy, no implicit localhost bypass, browser-side DNS failure outside
the gateway, blocked Service Workers, disabled QUIC, and disabled non-proxied
WebRTC UDP. The process opened successfully.

That last sentence was the problem.

“The browser opened” only proved that the driver created a context. It did not
prove which component would resolve a hostname, whether an internal redirect
would use the proxy, or whether Chromium would recover from a dead gateway by
opening a direct socket. If the daemon returned ready at that point, every
later page command would rely on configuration as evidence of network behavior.

For Remote Browser, configuration is a request. Readiness needs a verdict.

## Two witnesses, not one successful page

The native preflight now runs against the real persistent context before seed
cookies or user pages exist. Its first request uses a reserved `.invalid`
hostname. Browser-side DNS cannot resolve it; only the authenticated gateway
can turn that exact attempt into our stable 502 response. That response is a
witness that the browser reached the gateway and let the gateway own DNS.

The second request points at an owned IPv4 loopback sentinel. The gateway must
reject it with 403 while the sentinel records zero accepted sockets and zero
bytes. We repeat the zero-socket observation across fetch, image, WebSocket,
and worker paths because browser-owned transports do not all share the same
page interception surface.

Neither response is useful alone. A 403 without the DNS witness could come from
the wrong layer. A 502 without the sentinel could coexist with Chromium's
implicit direct path for loopback. Together they prove the behavior we need at
startup, and any timeout, unexpected status, accepted socket, or internal error
collapses to one non-secret failure. The partially opened context and driver
are then closed.

## The 407 that changed the release boundary

The first real-browser experiment did not pass this preflight. System Chrome
reached the proxy but never supplied `Proxy-Authorization`. Credentials in a
manual proxy URL are intentionally ignored by Chromium. Playwright routing and
page-scoped CDP Fetch interception also failed to cover the browser-owned
challenge early enough. The gateway returned 407, while the direct sentinel
correctly stayed at zero.

That was not a reason to weaken the test. It clarified the product boundary:
system Chrome is not an eligible Remote Browser engine. The closed Onion
Browser must answer only the exact first challenge from the pinned loopback
proxy, using a credential file owned by the Host-private runtime. A mismatched
realm, scheme, challenger, or repeated challenge must be cancelled.

The daemon now writes that file atomically beside the private profile. On
POSIX, its parent must be owned by the current user with no group or world
access, and the file is mode 0600. The launch policy gives Playwright only the
loopback proxy server—never its username or password—and passes the browser a
path-only switch. Construction failures and orderly shutdown both remove the
file. This still is not native-browser evidence; it is the exact producer side
of the contract that the pinned Onion Browser must consume.

This PR therefore stops at a fail-closed checkpoint. Its unit and lifecycle
tests pass, but it makes no installed-browser claim. The release gate remains
closed until the paid Onionwright engine, native credential hook, and exact
browser artifact meet in one stack and pass the full Mac and Linux matrix.

Opening a process is an implementation event. Declaring a private browser ready
is a security decision. The preflight exists to keep those two moments apart.
