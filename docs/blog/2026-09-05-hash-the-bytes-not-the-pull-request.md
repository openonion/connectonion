# Hash the bytes, not the pull request

Moving the paid browser from Chromium `151.0.7922.137` to `151.0.7922.222` is
three constants. The interesting part is what has to be true before you are
allowed to change them.

The catalogue that tells a client which bytes to download is a Python dict in
oo-api, and the pull request that added the `.222` entries stated their sizes
and SHA-256 digests. It would have been very easy to copy those digests into
the pin, run the tests, and ship. The digests would have matched, because they
would have matched *themselves*: the same number copied from the same place,
agreeing with itself all the way to production.

So they were recomputed from the objects instead:

```
gcloud storage cat gs://oo-releases-prod/chrome/151.0.7922.222/linux-x86_64.tar.zst | sha256sum
6bc4c672eb039088cf83656254e49bb9946c896dd34410e3585772f8de17cce6
```

Two hundred megabytes through a VM to learn one line, twice, plus a third for
the Onionwright wheel. All three matched the catalogue. That is a boring
result, and boring is the point: the check that only ever passes is worth
running precisely because the day it fails is the day someone ships bytes
nobody verified.

## The deploy that looked like it had not happened

The catalogue was merged and deployed, the workflow was green, and the live
signed manifest still returned exactly one artifact: the old `.137` build. The
new entries were missing.

The first instinct — the deploy did not restart the service — was wrong. The
manifest endpoint filters by what the asking client can actually use:

```python
actual = client_version or LEGACY_PAID_CLIENT_VERSION
return _version_tuple(actual) >= _version_tuple(minimum_client_version)
```

The request had named no client version, so the server assumed the oldest one
it still supports, 0.0.12, and correctly withheld artifacts that require 0.0.14
to extract. Asking again as a 0.0.14 client returned all three. The server was
right and the check was wrong: it had verified that *some* bytes come back, not
that the new ones are reachable by the client that will ask for them.

That is why the compatibility floor moves in the same commit as the revision.
`.222` requires Onionwright 0.0.14 and fails closed against 0.0.13, so a pin
that advanced the browser without advancing the floor would let a client ask
for bytes it cannot use, and the failure would arrive at extraction time on a
user's machine rather than at the manifest.

## What macOS gets

Nothing yet, and saying so is part of the change. Both macOS architectures are
built and staged, and their production release is waiting on a re-run of the
gate. Until that lands, an explicit `--engine onion` on a Mac returns the typed
unavailable error rather than a paid session.

That is survivable only because paying became opt-in in the same release. A
default that reached for the paid engine would have turned "macOS has no
production artifact yet" into a broken first command for every Mac user. It
turns it into a precise answer to a question only someone who asked for the
paid browser can ask.
