# A Private Tab Is Not a Private Browser

*2026-08-26*

Remote Browser already had owner-bound tabs. Alice could reconnect to her tab,
Bob could not see it, and the Host could stop it without guessing which caller
owned the session. It was tempting to put the new egress proxy on that tab and
move on to navigation.

Then we looked at where Chromium accepts a proxy.

The durable profile and proxy belong to the browser context, not to our tab
registry. A Remote Browser tab inside the ordinary `co browser` process would
therefore share network authority with local tabs. Setting the gateway for the
remote tab could redirect local browsing. Keeping the existing context could
do the reverse: a local environment proxy or profile preference could become
part of Remote Browser without the Host ever choosing it.

The tab was private in our database. The browser was not private at the layer
that opens sockets.

## We kept the implementation and changed the ownership boundary

The fix was not a second browser driver. The Host now starts the same
`BrowserDaemon` and `AsyncBrowserCore` behind a different native endpoint, lock,
profile, log, and Windows authentication key. Its launch inputs arrive as one
immutable value instead of being rediscovered from process environment
variables.

That separation gave startup an order we can test. The egress gateway must be
serving before the browser object exists, and both must exist before the IPC
endpoint becomes reachable. Shutdown reverses the authority: browser first,
gateway second. If the gateway disappears, the daemon refuses commands before
touching a tab. It never tries Direct because Direct is not a recovery path; it
is a different security policy.

One regression made the boundary clearer. Our first endpoint helper protected
its parent directory with mode `0700`. That was correct for the private runtime
directory and disastrously broad for an explicit legacy socket at
`/tmp/browser.sock`: it tried to change `/tmp` itself. The adjacent local-daemon
suite caught it. The helper now hardens only a directory it creates, while the
private address factory owns and verifies its dedicated directory.

## Configuration is evidence, not the verdict

The private launch asks Chromium to use one authenticated loopback proxy, block
Service Workers, disable QUIC and non-proxied WebRTC UDP, subtract Chromium's
implicit loopback bypass, and fail browser-side hostname resolution outside the
gateway. Tests also prove that ordinary local browsing still honors its old
environment-compatible configuration.

But a list of launch flags is not proof that Chromium cannot escape them. This
slice deliberately leaves navigation unavailable. The next test must run the
pinned browser on every supported operating system, attempt redirects,
subresources, workers, WebSockets, downloads, and DNS rebinding, and observe
zero connections at private sentinels.

A private session begins with identity. A private browser also needs exclusive
ownership of the process boundaries that decide profile, proxy, and sockets.
The word “private” is only earned at the lowest layer that can violate it.
