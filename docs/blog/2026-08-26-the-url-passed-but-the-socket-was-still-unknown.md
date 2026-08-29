# The URL Passed, but the Socket Was Still Unknown

*2026-08-26*

The first sketch for Remote Browser navigation was satisfyingly small. Parse the
URL, resolve its hostname, reject private addresses, then call `page.goto()`.

We already had the lifecycle. We already had an owner-bound tab. This looked
like the last check before adding `open`.

Then we followed the request one layer farther.

Our Python check would resolve the hostname and approve an address. It would not
hand that address to Chromium. It would hand Chromium the hostname again.
Chromium would resolve it later, when it opened the connection. A DNS answer
could change between those two moments, so the address that passed policy and
the address that received bytes did not have to be the same address.

The URL checker had made a decision about a socket it did not control.

## The proxy that private addresses could walk around

Putting a local proxy between Chromium and the network seemed to close the gap.
The proxy could resolve the hostname and connect directly to the approved
numeric address. Redirects and subresources would pass through it too.

Before writing the proxy, we checked Chromium's own proxy rules. That exposed a
second hole: Chromium implicitly sends localhost and link-local destinations
direct, bypassing an otherwise configured proxy. Those are exactly the
destinations Remote Browser must keep away from an untrusted page.

The browser offered a proxy, saw a local destination, and helpfully stepped
around our future security boundary.

Chromium does provide a subtractive bypass rule that forces those destinations
through the proxy. But that flag alone is not proof. An extension, profile
policy, engine difference, resolver rule, QUIC path, or future Chromium change
could restore direct traffic. The release gate therefore has to observe the
effective runtime: start private sentinel servers, attempt every private path,
and prove they accepted zero connections.

## The credential that the proxy setting did not carry

The first native preflight found a third boundary. macOS Chrome reached the
gateway, received its authentication challenge, and never sent the configured
proxy credential. The private sentinel still accepted zero connections, which
proved the launch failed closed. It did not prove the browser was usable.

That result matches a less obvious line in Chromium's own documentation:
credentials embedded in manual proxy settings are ignored. Playwright routing
could not repair it because the proxy challenge lives below a page request, and
a page-scoped CDP auth handler never received the challenge.

The secure fix belongs in the closed Onion Browser. It will read a credential
from a private file, then use Chromium's existing HTTP-auth delegate only when
the challenge is for the exact loopback proxy, fixed realm, Basic scheme, and
first attempt. A different proxy or a retry is canceled. An origin challenge
never sees the proxy password.

That discovery changes the delivery order. Remote Browser will not fall back to
system Chrome merely because it is installed. The paid browser hook and its
native zero-socket suite must pass first; a platform without that artifact keeps
navigation unavailable.

## One more boundary moved

The ordinary `co browser` daemon already has a persistent profile and shared
context. We could put the gateway there, but Chromium proxy selection belongs
to a browser context, not an individual tab. Remote policy would then change
unrelated local browsing, and future sessions with different shared-proxy grants
could not honestly claim per-tab isolation.

So the design moved again. Remote Browser will reuse the same BrowserDaemon and
AsyncBrowserCore implementation in a Host-private namespace, with its own
socket, lock, profile, and fixed fail-closed gateway. It is not a second browser
implementation. It is a separate security context for the same implementation.

Navigation is still absent. That is the useful result of the investigation.

The next code will begin with a parser, address classifier, deterministic DNS
and dialer seams, and a data-driven catalogue of private destinations. Only
after the gateway proves that redirects, rebinding, frames, images, scripts,
fetch, WebSockets, workers, and downloads cannot make a prohibited connection
will `open` become a Remote Browser command.

The mistake would have been easy to ship because the original URL really did
pass its check. The lesson is that SSRF policy does not belong to the string
that names a destination. It belongs to the component that chooses and opens
the socket.
