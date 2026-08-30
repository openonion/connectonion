# DD-056: Remote Browser navigation needs an egress gateway, not a URL check

**Status:** Proposed for 1.8; navigation remains disabled

**Date:** 2026-08-26

**Related:** [#991](https://github.com/openonion/connectonion/issues/991),
[#1297](https://github.com/openonion/connectonion/issues/1297),
[#1306](https://github.com/openonion/connectonion/issues/1306),
[#1036](https://github.com/openonion/connectonion/issues/1036),
[browser#103](https://github.com/openonion/browser/issues/103),
[DD-054](054-one-async-browser-runtime.md),
[DD-055](055-owner-bound-remote-browser-lifecycle.md)

## Decision summary

Remote Browser will not authorize navigation by validating the submitted URL
and then calling `page.goto()`. The enforcement point must be a fail-closed
loopback egress gateway through which Chromium sends every HTTP, HTTPS,
WebSocket, worker, subresource, redirect, and download connection. The gateway
resolves each authority, classifies every returned address, and dials an
already-approved numeric address without resolving the hostname a second time.

The Host will run that gateway beside a Host-private instance of the existing
BrowserDaemon/AsyncBrowserCore. It will not attach security policy to the
ordinary local `co browser` daemon: Chromium proxy configuration is
context-scoped, not tab-scoped, so changing the shared local context would also
change unrelated local browsing. A separate daemon namespace is reuse of the
same implementation and async runtime model, not a second browser
implementation.

No `open`, `do`, screenshot-after-navigation, or page-action command may be
added until the gateway and its negative vectors pass through an installed
wheel and native Chromium.

## Why the obvious boundary is insufficient

Playwright can pause a request with `browser_context.route()`, but continuing
the request gives DNS resolution and connection establishment back to Chromium.
Resolving in Python first and then continuing by hostname creates a time-of-
check/time-of-use gap: the address Chromium dials can differ from the address
Python approved. A redirect is a new request, and pages also create requests
through iframes, images, scripts, fetch, WebSockets, workers, and downloads.

Route interception is still useful for command attribution and structured
errors, but it is not the network authority. Playwright also documents request
visibility differences around Service Workers, so a security boundary cannot
depend on every request appearing in one high-level callback.

Chromium adds implicit proxy bypasses for localhost and link-local addresses.
Consequently, merely setting a proxy is also insufficient: a private
destination could go direct around it. The reviewed launch contract must remove
those implicit bypasses and must not configure a `DIRECT` fallback.

## Threat model and invariant

The remote caller may control URLs, page content, redirects, DNS answers,
subresources, WebSocket endpoints, download responses, and alternate textual IP
forms. The caller may race requests and may retry after any failure. A public
origin may itself be compromised.

The protected resources are services reachable from the Host but not intended
for ordinary public web browsing, including:

- loopback and unspecified addresses;
- link-local and multicast ranges;
- RFC private and unique-local networks;
- carrier-grade NAT, benchmark, documentation, reserved, and future-use ranges;
- cloud metadata names and addresses;
- operator-configured deny ranges and ports;
- Unix sockets, local files, browser-internal schemes, and non-web protocols.

The invariant is:

> No browser-controlled destination byte is sent until the exact socket address
> selected for that connection has passed the current destination policy.

DNS lookup traffic is made by the gateway's bounded resolver, not speculatively
by Chromium. A policy denial never retries through a different proxy or direct
connection.

## Runtime topology

```text
authenticated OIP command
          |
          v
RemoteBrowserService -- owner/session authority + bounded decision ledger
          |
          v
Host-private BrowserDaemon / AsyncBrowserCore
          |
          | fixed proxy, no DIRECT fallback
          v
127.0.0.1:<ephemeral policy gateway>
          |
          | resolve -> classify all answers -> dial approved numeric sockaddr
          v
public destination
```

The gateway starts and binds before Chromium starts. Chromium receives only the
gateway's loopback address. If the gateway dies, Chromium receives a proxy
connection failure; it cannot fall back to direct egress. Host shutdown closes
admission, browser traffic, gateway connections, resolver tasks, and the
private daemon in that order.

Loopback is not authentication. The gateway requires a random, daemon-scoped
proxy credential stored only in the Host-private runtime directory. It rejects
unauthenticated local clients in constant time and consumes
`Proxy-Authorization` rather than forwarding it. The credential selects no
broader network authority; it only prevents another local process from
borrowing the bounded public-web gateway.

Chromium deliberately ignores credentials embedded in manual proxy settings.
A native macOS persistent-context reproduction also showed Patchright's proxy
username/password reaching the gateway without `Proxy-Authorization`; neither
Playwright routing nor a page-scoped CDP Fetch auth handler received the proxy
challenge. Therefore system Chrome is not a Remote Browser engine merely
because the requested proxy flags look correct.

The paid Onion Browser reads an absolute path from
`--connectonion-proxy-auth-file`, validates a bounded private credential file in
the browser process, and supplies the credential only through Chromium's HTTP
authentication delegate when the proxy flag, exact `127.0.0.1:<port>`
challenger, Basic scheme, fixed Remote Browser realm, and first attempt all
match. A mismatched or repeated proxy challenge cancels instead of opening a
dialog or trying another credential source. Origin authentication never
receives the proxy credential. The password itself is absent from argv,
environment variables, logs, errors, telemetry, crash annotations, CDP events,
and origin headers. [browser#103](https://github.com/openonion/browser/issues/103)
owns this closed-browser hook and its compile/native verification.

The Host-private daemon uses the same BrowserDaemon and AsyncBrowserCore code as
`co browser`, but a different socket/pipe namespace, lock, PID sidecar, and
persistent profile directory. All Remote Browser Direct sessions share this one
remote profile and direct egress policy. Local `co browser` keeps its existing
profile and behavior.

Future shared-proxy grants may require different browser contexts because
Chromium proxy selection is context-scoped. #1036 must choose and test that
context/process model; this decision does not claim per-tab proxy isolation.

## Gateway connection contract

The first implementation accepts only browser web traffic:

- HTTP absolute-form requests;
- HTTP `CONNECT` for HTTPS and secure WebSockets;
- ordinary WebSocket upgrade over HTTP;
- TCP only, with an explicit safe-port policy.

It does not accept inbound forwarding, arbitrary SOCKS commands, UDP, QUIC,
WebRTC peer traffic, `file:`, `ftp:`, `data:` as a network destination,
`chrome:`, extension protocols, or a generic tunnel API. Browser launch options
must prevent UDP/QUIC/WebRTC from becoming an alternate egress path.

For every new authority the gateway:

1. parses a bounded request line and authority before reading or forwarding a
   body;
2. authenticates the local proxy client and strips proxy credentials;
3. rejects userinfo, control characters, invalid ports, overlong names, invalid
   IDNA, ambiguous syntax, and unsupported schemes;
4. normalizes the hostname once, including a single trailing dot and IPv6
   brackets;
5. canonicalizes IP literals before classification, including IPv4-mapped IPv6;
6. resolves hostnames with a bounded resolver and response-size limit;
7. denies the request if **any** returned address is prohibited;
8. selects only from the approved answer set and connects to that numeric
   socket address without another hostname lookup;
9. applies connection, idle, byte, concurrency, and header limits;
10. tunnels bytes only after the numeric connection succeeds.

Denying a mixed public/private DNS answer set avoids choosing a public address
on the first connection and a private one on a retry. Every new connection
resolves and revalidates again; an existing tunnel remains pinned to its already
approved socket. A rebind on a later connection is denied before dial. Redirect
counting belongs to the browser command/interception layer because an
end-to-end TLS tunnel cannot inspect HTTP response status.

For an HTTPS `CONNECT example.com:443`, TLS remains end-to-end between Chromium
and the destination. The gateway does not install a root certificate or inspect
page plaintext. It connects to the approved numeric address while Chromium's
TLS handshake inside the tunnel retains the original hostname for SNI and
certificate verification.

## Chromium launch invariants

The exact flags/options must be asserted against the Onion engine, rather than
assumed from documentation. A system engine is eligible only if it later passes
the identical authenticated effective-runtime suite without a weaker shim:

- fixed loopback proxy for every relevant scheme;
- daemon-scoped proxy authentication through the exact native challenge hook,
  with no credential forwarded upstream;
- proxy bypass subtraction for Chromium's implicit localhost/link-local rules;
- no `DIRECT` fallback in the proxy list;
- resolver rules that stop Chromium target-host DNS and exempt only the numeric
  loopback gateway endpoint;
- no arbitrary extensions or profile-level proxy override in the Host-private
  profile;
- QUIC disabled;
- non-proxied WebRTC UDP disabled;
- `service_workers="block"` requested as best-effort request-visibility
  hardening. Real Chrome measurement shows that this driver option does not
  prevent registration, activation, or page control, so it is not an egress
  boundary; the authenticated loopback gateway and native preflight remain the
  authority for Service Worker traffic;
- downloads accepted only through the same context and gateway.

Preflight must test the effective runtime, not only inspect requested flags: a
private loopback sentinel and DNS spy must remain untouched before the first
remote session is reported ready. An extension, policy, engine variation, or
flag regression that restores direct traffic makes Remote Browser navigation
unavailable.

Chromium has changed host-resolver failure-token spelling across revisions. The
implementation must select the syntax verified against the pinned Chromium
revision and fail preflight if the effective launch contract cannot be proven.

## Stable results and audit evidence

Primary-document denial returns a stable Remote Browser failure. A denied
subresource does not reveal its URL to the remote caller by default; it records
a bounded warning and decision counter visible through `diagnose`.

Initial codes:

- `DESTINATION_INVALID`
- `DESTINATION_SCHEME_DENIED`
- `DESTINATION_PORT_DENIED`
- `DESTINATION_HOST_DENIED`
- `DESTINATION_DNS_FAILED`
- `DESTINATION_ADDRESS_DENIED`
- `DESTINATION_REBINDING_BLOCKED`
- `DESTINATION_REDIRECT_LIMIT`
- `EGRESS_GATEWAY_UNAVAILABLE`
- `PROXY_CHAIN_UNSUPPORTED`

The gateway decision ledger stores only timestamp, gateway connection ID,
decision code, normalized scheme, port, address class, and a keyed hash of the
normalized hostname. Browser-context routing may correlate a command request,
owner-bound session, and resource class when that attribution is unambiguous,
but enforcement never depends on this best-effort join: a shared TLS tunnel does
not expose its page or tab to a non-intercepting proxy. The ledger does not store
URL paths, queries, fragments, credentials, headers, bodies, cookie values, DNS
payloads, or page content. Counts and recent failures are bounded.

## Executable negative-vector plan

The vector catalogue is data-driven so the same cases run at four layers:

1. pure parser/classifier tests on Python 3.10-3.13;
2. gateway tests with deterministic resolver and dialer seams;
3. BrowserDaemon integration through native socket/named-pipe transport;
4. installed-wheel Chromium E2E on Linux, macOS, and Windows.

Required host forms include:

- `127.0.0.1`, `127.1`, integer/octal/hex-like IPv4 forms, and mixed-case
  `localhost` with a trailing dot;
- `[::1]`, IPv4-mapped IPv6, IPv6 zone identifiers, unspecified, multicast,
  unique-local, and link-local IPv6;
- private IPv4, carrier-grade NAT, link-local, multicast, reserved, benchmark,
  documentation, and metadata destinations;
- IDNA/punycode edge cases, embedded credentials, empty hosts, invalid ports,
  control characters, overlong labels, and multiple trailing dots.

Required request paths include:

- initial main-frame navigation;
- every 30x hop and redirect-limit exhaustion;
- DNS public-to-private rebinding between requests;
- iframe, image, script, stylesheet, font, media, fetch/XHR, EventSource,
  WebSocket, worker, and Service Worker attempts;
- popup first request;
- attachment and download redirects;
- concurrent allowed and denied requests on different owner-bound tabs;
- gateway crash during an active page and restart without direct fallback.

Native negative tests use `page.set_content()` to create private subresource
attempts without first needing a private test page. Loopback sentinel servers
count accepted sockets and bytes; the assertion is zero, not merely a browser
error. Parser/gateway rebinding tests use deterministic resolver answers and a
dialer spy so they prove which numeric address would have been selected. Positive
E2E uses a controlled public endpoint and verifies ordinary multi-origin pages,
OAuth redirects, WebSockets, and downloads remain usable.

## Delivery order

1. Land the pure normalization/classification policy and versioned vector
   catalogue with no browser command.
2. Land the bounded loopback gateway and prove zero-dial denials under race,
   cancellation, malformed input, and resource exhaustion.
3. Give BrowserDaemon an explicit namespace/profile/launch-policy contract;
   verify local and Host-private daemons can run concurrently without sharing
   sockets, locks, profile files, or proxy settings.
4. Add the private proxy-auth credential-file hook to the paid Onion Browser,
   compile it at the pinned Chromium revision, and keep system Chrome
   unavailable for Remote Browser navigation.
5. Wire the gateway through Onionwright's paid engine and run the identical
   negative vectors through installed production-shaped Linux, macOS, and
   Windows artifacts. A platform without a passing paid artifact remains
   unavailable; it does not fall back to system Chrome.
6. Add Remote Browser `open` only; map primary and subresource decisions into
   stable envelopes and diagnosis.
7. Add screenshots and actions after `open` proves the policy under parallel
   tabs, downloads, browser restart, and cancellation.
8. Treat shared proxy mode as a separate #1036/#1172 gate; never silently reuse
   Direct when a pinned shared grant fails.

The executable limits and protocol contract for step 2 are documented in
[Remote Browser egress gateway](../network/remote-browser-egress-gateway.md).
The namespace, profile, launch-policy, and shutdown contract for step 3 is
documented in
[Remote Browser private runtime](../network/remote-browser-private-runtime.md).

Each step is its own reviewable PR with documentation, unit tests, native E2E,
and a rollback that leaves navigation unavailable rather than bypassing the
gateway.

## Rejected alternatives

### Validate only the `open` URL

Rejected because redirects and page-created requests escape the check.

### Resolve in the command handler, then call `page.goto(hostname)`

Rejected because Chromium performs the later dial and may resolve a different
address.

### Depend only on Playwright routing or CDP Fetch interception

Rejected because these APIs authorize a URL before Chromium's socket selection;
they do not pin the address actually dialed. They remain useful as an additional
attribution/error layer.

### Trust Playwright proxy username/password with system Chrome

Rejected because Chromium documents that manual proxy settings do not carry
credentials, and the native macOS persistent-context reproduction reached the
gateway without `Proxy-Authorization`. Requested configuration is not evidence
of effective authentication. System Chrome remains a valid ordinary local
engine, but not a Remote Browser navigation engine until it independently
passes the same authenticated zero-socket suite.

### Load a credential extension or inject an authorization header

Rejected because an extension adds a second mutable network authority and
profile surface, while header injection risks placing a proxy secret on an
origin request. The browser's existing proxy-auth challenge delegate already
distinguishes proxy authentication from origin authentication and can scope the
credential to the exact challenger, realm, scheme, and first attempt.

### Apply the proxy to the ordinary local browser context

Rejected because proxy configuration is context-scoped. It would change local
`co browser` traffic and still could not isolate future session-pinned proxy
grants by tab.

### TLS interception

Rejected because destination enforcement needs the authority and numeric peer,
not page plaintext. Installing a Host root certificate would add credential,
privacy, and compatibility risk without closing the socket-selection gap.

### OS firewall as the only guard

Rejected as the portable product boundary because macOS, Linux, Windows, local
development, containers, and hosted runners expose different firewall
authority. Platform sandbox/firewall rules may be defense in depth, and tests
should use them where available, but the browser must still fail closed through
the portable gateway.

## Evidence consulted

- Chromium proxy documentation describes implicit localhost/link-local bypasses
  and the subtractive `<-loopback>` rule. It also states that Chrome does not
  use credentials embedded in manual proxy settings:
  <https://chromium.googlesource.com/chromium/src/+/main/net/docs/proxy.md>
- Chromium 151's `ChromeContentBrowserClient::CreateLoginDelegate()` receives
  the proxy challenge and `first_auth_attempt`, while ChromeOS's
  `SystemProxyLoginHandler` demonstrates asynchronous, policy-scoped credential
  delivery through `content::LoginDelegate`:
  <https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.137/chrome/browser/chrome_content_browser_client.cc>
  and
  <https://chromium.googlesource.com/chromium/src/+/refs/tags/151.0.7922.137/chrome/browser/ash/net/system_proxy_manager.cc>
- The Playwright Chromium proxy-auth report was closed as not reproducible
  after a Linux success report, not with a confirmed fix:
  <https://github.com/microsoft/playwright/issues/37444>
- Chromium's SOCKS guidance uses host-resolver rules to prevent browser-side DNS
  leakage through a proxy:
  <https://chromium.googlesource.com/experimental/website/+/HEAD/site/developers/design-documents/network-stack/socks-proxy.md>
- Playwright documents context routing, WebSocket traffic, and Service Worker
  visibility limitations:
  <https://playwright.dev/python/docs/network>
- CDP Fetch documents that redirects create later paused requests, but
  continuation still hands the request to Chromium's network stack:
  <https://chromedevtools.github.io/devtools-protocol/tot/Fetch/>
- The WHATWG URL Standard defines the browser-compatible host parser, including
  IPv4 numbers written with one to four decimal, octal-like, or hexadecimal
  parts: <https://url.spec.whatwg.org/#concept-ipv4-parser>
- The frozen address policy is derived from the IANA IPv4 and IPv6
  special-purpose registries. Its snapshot date is part of the executable
  vector catalogue so a registry refresh is an explicit policy change:
  <https://www.iana.org/assignments/iana-ipv4-special-registry/>,
  <https://www.iana.org/assignments/iana-ipv6-special-registry/>
