---
title: One key for every renewal
date: 2026-11-01
tags: [Browser, Billing, macOS]
---

# One key for every renewal

A paid WTF Browser session on macOS lasted exactly one billing period. The
first fifteen minutes were prepaid at start; three minutes before they ran
out, the runtime asked for the next period, and the API refused it. The page
went away on schedule, every time.

Each renewal carries an Idempotency-Key, so a retried request cannot charge
twice. The macOS runtime built that key in Swift as
`"renew:(state.sessionID):(sequence)"`. Swift interpolates `\(x)`, not `(x)`.
Without the backslashes the compiler accepted the line as ordinary text, and
every renewal from every session sent the same thirty-four characters. Keys
are unique per account, so the first renewal an account ever made succeeded
and every later one answered 409 `idempotency_key_conflict`.

Linux never saw it. Its renewals go through Onionwright's Python client,
which formats the key with an f-string that was right from the start.

The client fix was one backslash in two places, plus a test that scans every
Swift string literal for a parenthesised name without one. Shipping it was
the harder part. Artifact keys are scoped to the Chromium revision and
immutable, and production already held this revision, so new bytes needed a
new revision: macOS moved from 154.0.8037.58 to 154.0.8037.100, and the patch
series applied to it unchanged.

Browsers already installed would keep the bug until they updated, and the
key is signed into each spend authorization, so the server cannot ask for a
different one. The API now recognises that exact literal and stores it as
`renew:<session>:<period>`, which is what the client meant to send. The
signature still binds session, period and key, and a retried period still
replays without a second charge. Against production, a session renewed with
the literal key went from period 0 to 1 to 2.

This release asks for 154.0.8037.100 on macOS. Linux stays on
154.0.8037.58: it has nothing to fix.
