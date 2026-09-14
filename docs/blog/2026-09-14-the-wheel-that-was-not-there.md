# The wheel that was not there

The owner asked a reasonable question: why isn't `onionwright` just a dependency,
so `pip install connectonion` handles the paid browser's driver?

The answer at the time was that the package on PyPI was not the product. Install
it and you got one file:

```python
"""onionwright — humanized input for browser automation.

Name reservation. The product is proprietary and is not distributed from this
index; see https://browser.openonion.ai
"""

__version__ = "0.0.3"
```

A docstring and a version string. The real 0.0.14 had seventeen modules and came
from a licence-gated bucket, through an authenticated request, a pinned Ed25519
manifest, and a SHA-256 check — the same path the browser binary travels.
`openonion/onionwright#9` had chosen one distribution mechanism over two on
purpose: the wheel and the binary share a manifest, a signature and a checksum.

That is a real reason, and it is a security reason, not a commercial one. So it
was worth saying out loud rather than just doing what was asked.

Then the owner said: replace it. Put the real thing on PyPI.

## What a reversed premise does to a guard

The repo had `packaging/check_placeholder.py`, which opens:

> onionwright is proprietary. The PyPI entry exists to hold the name; the
> product is distributed through the licence-gated endpoint. That intent was
> written in the README, and a rule that lives only in a README is a rule that
> holds until someone is in a hurry.

It is a good guard. It refuses to publish any wheel containing more than the
reserved name, and it runs in CI and in the release workflow so it cannot be
skipped on the one path where nobody is looking.

Its premise is now false. And a guard whose premise is false is not a guard that
needs rewording — it is a guard with nothing left to hold. Keeping it inverted
("assert the wheel *does* contain the implementation") would be a check that
passes on every possible input and reassures the reader for free.

So it is deleted, and so is the placeholder tree.

The guard beside it, `check_metadata.py`, is untouched and still runs in both
places. That one refuses to publish the internal README — positioning, measured
competitive baselines, private repo links — into permanent public metadata. The
reversal did not touch its premise at all.

That is the actual skill: when a decision moves, work out which guards were
about the decision and which were about something else standing near it.

## Five tests, three answers

Five tests mentioned the placeholder.

Three of them guarded something real and only happened to read that directory:
the build backend is pinned for reproducible wheels, the driver dependency is an
exact `playwright==1.61.0`, the licence text is byte-identical across every
distribution. Those kept every assertion and lost one path each.

Two had the placeholder as their whole subject. Deleting a failing test is how
coverage disappears quietly, so they were replaced with what the reversal makes
worth watching:

- the release workflow publishes the real package, from the real tree, with
  `check_metadata` and a clean-install check still in front of it
- the runtime licence layer still exists

That second one matters more than it looks. Publishing the driver is not
publishing the browser — the binary stays licence-gated and the licence is still
checked at launch. If that ever stopped being true, the paid product would
quietly become the free one, and no error message would announce it.

## A new check, because permanence changes the stakes

Both CI and the release workflow now install the built wheel into a clean
interpreter and assert it imports and reports the version it claims.

That check would have been mild ceremony before. It is not now: a PyPI version
can never be replaced. A broken wheel at `0.0.14` is not something a later commit
fixes, it is something `0.0.15` works around forever. Verification is worth most
right before the moment a mistake stops being reversible.

## What the caller got

`connectonion`'s installer used to be 289 lines: authenticate, fetch the signed
manifest, verify the Ed25519 signature against a pinned public key, resolve a
download grant, stream the wheel under a size ceiling, hash it, compare, then
call pip on the local file.

It is 134 lines now, and the interesting part is one line:

```python
ONIONWRIGHT_REQUIREMENT = f"onionwright>={ONIONWRIGHT_VERSION}"
```

The deleted code was not bad code. It was correct, careful, and answered a
constraint that no longer exists. The credential handling went too — an install
that needs no token cannot raise `AmbientCredentialError`, and catching an
exception that can never arrive tells the next reader it can.

And the original question now has the answer it always wanted:

```bash
pip install 'connectonion[wtf]'
```

## The thing worth carrying

A constraint you have written code around becomes invisible. It stops being "we
decided this" and becomes "this is how it is" — and then the code, the tests, the
guards and the docs all quietly encode a decision nobody is re-examining.

The tell here was that the answer to "why isn't it a dependency" was long. Short
answers describe the world. Long answers describe a decision.
