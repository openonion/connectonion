# The Owner Needs a Door

`co ai` was secure on a fresh install. It was also unusable.

The default careful policy admits known contacts and lets a stranger become a
contact by presenting `CO_INVITE_CODE`. We deliberately stopped shipping a
literal invite in that policy: a password committed to a public repository is
one password shared by every installation, not an access-control mechanism.
`co init` and `co create` replaced it with a unique per-project code.

But the shortest path in the documentation is simply:

```bash
pip install connectonion
co ai
```

That path creates and hosts the global identity directly. It does not run
either project command, so there was no invite in the environment. The host
correctly advertised no onboarding method. The person sitting at the machine
had started their agent and then had no credential with which to connect their
own client.

## Why printing a code is not a fix

The tempting patch is to generate a code at startup and include it in the host
banner. It makes the demo work, but turns every captured terminal, CI log,
screen share, and support paste into a credential leak. Masking part of the
code is no improvement: the owner still cannot use it, while the output still
reveals secret material for no operational benefit.

The other tempting patch is to use a fixed fallback whenever the variable is
missing. That recreates the original universal-password defect under a new
name.

The useful distinction is between *creating* a recovery path and *displaying*
its credential. Creation should be automatic; disclosure should be deliberate.

## One code, minted once

The web-server path now ensures the global identity has one owner invite in
`~/.co/keys.env`. The file is owner-readable on POSIX. A cross-process lock
protects the first write, so two simultaneous cold starts cannot mint two
different answers and silently invalidate the first one handed to a client.

Precedence remains ordinary and unsurprising. A code already loaded from the
process or current project wins. Otherwise an existing global code is loaded
into the server process. Only when all three are absent is a new value minted,
stored, and used. Restarting preserves it.

Startup says only that an owner invite was created and points to:

```bash
co keys --reveal
```

Plain `co keys` confirms the credential exists with a fixed-width mask. The
explicit reveal command shows it when the operator is actually onboarding a
client. That matches how recovery phrases and provider tokens already work:
safe inspection by default, full material only after an intentional flag.

## The invariant

A careful default needs two properties at once: an unrelated stranger cannot
walk in, and the owner has a private way back in. We had tested the first half
and assumed the project scaffolding covered the second. It did not cover the
product's shortest entry point.

The regression tests now begin from an empty home, exercise the real careful
rule with the minted value, reject an unrelated value, preserve an existing
invite across restart, and check that normal key output never contains it.

Security defaults are not complete when they deny the wrong person. They are
complete when the right person can recover access without teaching logs the
secret.
