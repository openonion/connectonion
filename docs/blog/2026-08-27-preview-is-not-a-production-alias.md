# Preview Is Not a Production Alias

*2026-08-27*

ConnectOnion 1.9 had a preview version, an exact preview dependency, and a
signed artifact manifest. On paper, that looked like a separate release
channel. Then the first cross-repository check supplied the ordinary
`OO_API_URL` setting and watched the preview client follow it straight back to
the production control plane.

Nothing had defeated the checksum. The client was prepared to download the
right bytes from the wrong authority.

That distinction matters for a paid browser. The API chooses the artifact,
creates the metered session, and signs the runtime configuration. If preview
can silently inherit a production endpoint, a test can spend real credit and
exercise production policy while still reporting a preview package version.
The green result proves only that two channels happened to be compatible that
day.

## The channel now crosses every trust boundary

The 1.9 client names `preview` in four places that must agree. It installs the
exact Onionwright preview version, calls the dedicated preview API, accepts
only a signed manifest whose channel is `preview`, and checks that the runtime
client still reports that channel before browser preparation or billing can
begin. The general production override is deliberately ignored; local tests
have a separate preview-specific override.

That local override exposed another useful boundary. Preview needs an HTTPS
origin in normal use, but an integration test should not need a public
certificate merely to bind an ephemeral server on the loopback interface. The
validator therefore permits HTTP only when both the API and artifact URLs are
loopback addresses. Credentials, paths, queries, fragments, and non-loopback
HTTP are rejected instead of normalized into something surprising.

The failure order is part of the design. A version or channel mismatch stops
before download, pip installation, browser preparation, session creation, or
charging. A preview label is not a warning attached to a production request;
it is an input to every decision that can spend money or execute downloaded
code.

## Offline green is necessary, not deployment proof

The exact 1.9 candidate passed 91 focused preview and version tests, 308 browser
tests, the 96-test daemon suite with local sockets enabled, the installed-wheel
harness, and a real ConnectOnion-to-Onionwright preview boundary check. The
broader offline matrix passed 7,670 tests. A fresh install also proved that the
candidate ignored `OO_API_URL` and selected the preview origin without reading
credentials or touching the network in system mode.

Those results establish the client boundary. They do not establish the hosted
one. The final gate still has to deploy the isolated preview API and run the
exact artifact through create, navigation, WebGL, download, renewal, close,
release, and billing reconciliation. That deployment needs explicit access to
the shared JWT, billing, and signing authority; copying an entire production
environment would erase the isolation we are trying to prove.

The lesson is smaller than the machinery: a preview channel is independent
only when it fails closed before the first irreversible action. A different
version string is useful evidence, but it is not a trust boundary.
