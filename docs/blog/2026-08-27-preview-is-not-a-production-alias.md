# Preview Is Not a Production Alias

*2026-08-27*

The ConnectOnion 1.8 browser candidate looked like a preview. Its version was a
preview, its Onionwright dependency was a preview, and the artifact manifest
was signed. We had done the work people usually mean when they say “separate
release channel.”

Then a cross-repository test set the ordinary `OO_API_URL` variable.

The preview client followed it straight to production.

That was the uncomfortable result because none of the cryptography had failed.
The checksum was right. The signature was right. The package version was
right. The client was prepared to download the expected bytes from the wrong
authority.

For a library download, that would already be a serious boundary mistake. For
a paid browser it was worse. The API does more than serve a file: it selects
the artifact, creates the metered session, and signs the runtime configuration.
A test labelled “preview” could therefore spend real credit and exercise
production policy. If it passed, the green check proved only that preview and
production happened to agree that day.

Our first instinct was to treat the endpoint as one more setting to document.
That would have preserved the bug in a friendlier form. Environment overrides
are useful precisely because they are ambient: a shell, a project `.env`, or a
parent process can provide them without the caller thinking about the value on
each request. The property that makes an override convenient for ordinary API
traffic makes it unsuitable for the authenticated bootstrap that downloads
code and crosses a billing boundary.

The turn came when we stopped asking, “Does this package have a preview
version?” and asked, “What is the first irreversible action?” Downloading code,
creating a paid session, and launching a remotely configured browser all
qualified. The channel had to be settled before any of them.

That changed the shape of the solution. The preview endpoint became part of
the packaged trust decision, not an alias for the production endpoint. The
signed manifest had to say `preview`, and the installed runtime had to report
the same channel before preparation or billing could begin. A mismatch now
ends the attempt rather than looking for a compatible fallback.

The same question exposed a second, quieter path. Even after a wheel had been
verified, an ordinary pip invocation could consult repository-controlled
configuration or indexes. So verification could be correct while installation
still executed something else. The installer now hands an already verified
local wheel to an isolated interpreter, with indexes and dependency resolution
disabled, and checks the installed client from outside the project directory.

We found the pricing decision by following the boundary one step further. If a
bare `co browser` could automatically select Onion, then installing the preview
once would turn later ordinary browser calls into purchases. The new default is
the free system engine. `auto` remains available as an explicit choice and may
select Onion; `onion` is the strict paid path. Both paid choices name the
`$0.025 / 15 min` price. The preview can now be installed without silently
changing what an unqualified browser command costs.

Local tests could prove these failure orders, but they could not prove a hosted
deployment. An earlier stacked candidate completed the real browser and billing
path; rebasing it as `1.8.0a4` changed the source and wheel hashes. That erased
the right to reuse the old acceptance result. The immutable dev3 wheel, preview
catalogue, API deployment, and paid lifecycle must agree again before a4 can be
published.

The lesson is smaller than the machinery. A preview is independent only when
it fails closed before the first irreversible action. A different version
string is useful evidence. It is not a trust boundary.
