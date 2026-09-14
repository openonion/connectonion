# Asking for it is asking for it

The documented way to use the paid browser was three commands, and you only
found out about the second one by failing:

```
co browser --engine wtf tab open work
→ BrowserEngineError: onionwright_missing: Run `co browser install-onion`

co browser install-onion
→ Could not install Onionwright: this Python is externally managed...
   co browser install-onion --break-system-packages

co browser install-onion --break-system-packages
→ Installed Onionwright 0.0.14
```

Every one of those errors is good. Each names its cause and the exact command
that gets past it. The second one we only fixed two days ago, and the fix was
worth it.

But look at the first hop again. Someone typed `--engine wtf`. What did that
error actually ask them to decide?

## Nothing. It asked them to decide nothing

The paid engine cannot run without its client. There is no configuration in
which you want one and not the other, no scenario where a user weighs the
options and picks "paid engine, no client". The first error was a question with
one answer, and it cost a round trip to ask it.

That is the shape worth noticing: **an error that offers no choice is not an
error, it is a missing step.** The remedy being well-written made it easy to
miss — a bad error message announces itself, a good message for an unnecessary
question just looks like good documentation.

So an explicit `--engine wtf` now fetches the client if it is not there:

```
The WTF Browser needs its private client, which is not on PyPI. Fetching it…
Installed Onionwright 0.0.14 from the signed OpenOnion release.
```

Three commands became one.

## The rule this could have broken

`onionwright_install.py` opens with a promise:

> The command is deliberately explicit: importing ConnectOnion or selecting the
> system browser must never mutate a Python environment.

An auto-install is exactly the kind of convenience that erodes a promise like
that, so it is worth being precise about why this one does not.

The promise names two things it protects: **importing ConnectOnion**, and
**selecting the system browser**. Neither is what happens here. `--engine wtf`
is a typed, explicit request for a commercial product on an authenticated
account. The mutation follows a decision the user already made out loud.

The tests say so directly, and they are the ones that would catch a future
version of me widening this:

- `--engine auto` installs nothing
- `--engine system` installs nothing
- `--engine wtf help` installs nothing — a question is not a request to run
- a client already present is not reinstalled
- a failed fetch reports and **does not send the command**, so a paid command
  never reaches a daemon that cannot serve it

Four of those six tests exist only to constrain the feature. That ratio is about
right for a change whose risk is doing too much.

## Why it cannot just be a dependency

The obvious question, and we got it from the owner: why isn't `onionwright` in
`install_requires`, so `pip install connectonion` handles it?

Because the package on PyPI is not the product. Install it and you get one file:

```python
"""onionwright — humanized input for browser automation.

Name reservation. The product is proprietary and is not distributed from this
index; see https://browser.openonion.ai
"""

__version__ = "0.0.3"
```

A version string and a docstring. The real 0.0.14 has fifteen modules and comes
from a licence-gated bucket, through a signed manifest and a SHA-256 check —
the same path the browser binary itself travels. `openonion/onionwright#9` chose
one distribution mechanism over two on purpose: the wheel and the binary share a
manifest, a signature, and a checksum path.

Declaring the dependency would put a dead placeholder in every free user's
environment and change nothing about whether the paid engine works.

That decision is now being revisited — the placeholder may be replaced by the
real thing, which would make the dependency question a real one again. This
change is orthogonal to that: whichever way the wheel is distributed, asking for
the paid engine should get you the paid engine.

## The general form

Look for errors that name exactly one next action, where the caller has no
information the program lacks. Every one of those is a step the program declined
to take. Some genuinely should stay manual — the ones that spend money, or
overwrite something, or override a guard someone set on purpose; that is why
`--break-system-packages` is still opt-in one layer down. The rest are just
work you handed back.
