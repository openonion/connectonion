# Preview Is Not a Production Alias

*2026-08-27*

The ConnectOnion 1.8 browser candidate had a preview version, an exact preview
dependency, and a signed artifact manifest. On paper, that looked like a
separate release channel. Then the first cross-repository check supplied the
ordinary `OO_API_URL` setting and watched the preview client follow it straight
back to the production control plane.

Nothing had defeated the checksum. The client was prepared to download the
right bytes from the wrong authority.

That distinction matters for a paid browser. The API chooses the artifact,
creates the metered session, and signs the runtime configuration. If preview
can silently inherit a production endpoint, a test can spend real credit and
exercise production policy while still reporting a preview package version.
The green result proves only that two channels happened to be compatible that
day.

## The channel now crosses every trust boundary

The 1.8 browser preview client names `preview` in four places that must agree.
It installs the exact Onionwright preview version, calls the dedicated preview
API, accepts only a signed manifest whose channel is `preview`, and checks that
the runtime client still reports that channel before browser preparation or
billing can begin. The general production override is deliberately ignored;
local tests have a separate loopback-only preview override. Hosted traffic is
fixed to the packaged preview hostname, so a repository `.env` file cannot
redirect the ambient credential to an arbitrary HTTPS host.

That local override exposed another useful boundary. Preview needs an HTTPS
origin in normal use, but an integration test should not need a public
certificate merely to bind an ephemeral server on the loopback interface. The
validator therefore permits an overridden origin only when it is loopback, and
permits HTTP only when both the API and artifact URLs are loopback addresses.
Credentials, paths, queries, fragments, malformed ports, and other remote hosts
are rejected instead of normalized into something surprising.

The failure order is part of the design. A version or channel mismatch stops
before download, pip installation, browser preparation, session creation, or
charging. A preview label is not a warning attached to a production request;
it is an input to every decision that can spend money or execute downloaded
code.

The 1.8 preview also makes spending an explicit choice. A bare `co browser`,
`BrowserAutomation`, or async core selects the free system engine. `auto` still
exists as an explicit policy and may choose paid Onion when ready; `onion`
forces the paid path. Either paid outcome names `$0.025 / 15 min`. The
preview trust chain is therefore available without turning ordinary browser
usage into an implicit purchase.

## Offline green is necessary, not deployment proof

The superseded stacked 1.8 browser candidate first passed the focused preview
and version suites, the browser security/runtime matrix, the installed-wheel
harness, and a real ConnectOnion-to-Onionwright preview boundary check. A fresh
install also proved that it ignored `OO_API_URL` and selected the preview origin
without reading credentials or touching the network in system mode.

Those results established the client boundary, not the hosted one. At that
checkpoint the final gate still had to deploy the isolated preview API and run
the exact artifact through create, navigation, WebGL, download, renewal, close,
release, and billing reconciliation. That later passed on the exact stacked
source and wheel. The clean 1.8.0a4 rebase has repeated the local full,
cross-repository, package, and installed-wheel gates, but its source and wheel
hashes necessarily changed. The hosted gate is therefore required again, after
the immutable dev3 wheel and matching oo-api catalogue coordinate exist.

The lesson is smaller than the machinery: a preview channel is independent
only when it fails closed before the first irreversible action. A different
version string is useful evidence, but it is not a trust boundary.
