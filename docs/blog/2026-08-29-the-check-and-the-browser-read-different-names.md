# The check and the browser read different names

The module had one job: given a URL a stranger submitted, say whether the
browser may dial it. No DNS, no sockets, just a decision. It shipped with 275
lines of tests, 81 negative vectors, a frozen table checked against the IANA
special-purpose registry, and a fail-closed default for every IPv6 address
outside `2000::/3`. Every alternate way of writing 127.0.0.1 that I could think
of — `2130706433`, `0x7f.1`, `127.1`, `0177.0.0.1` — was correctly pinned to the
loopback literal and denied.

Then a review asked what happens if you append one character:

```
http://metadata.google.internal。/
```

That last character is U+3002, the ideographic full stop. It is what your phone
types at the end of a Chinese sentence. The policy returned **allowed**.

## Where the character goes

A browser does not read a hostname the way Python's `str` does. Before anything
else, it runs the string through UTS-46 — the Unicode mapping that turns
`BÜCHER.de` into `xn--bcher-kva.de`. That same mapping turns U+3002 into an
ordinary ASCII `.`, and turns fullwidth `１２７` into `127`.

My code ran that mapping too. It ran it seventh.

Ahead of it sat the check for a double trailing dot, the strip of a single
trailing dot, the parser for alternate IPv4 forms, and — after it — the lookup
of the hostname against the special-use list. So the code that decided
"is this `localhost`?" and the code that produced the string `localhost.` were
on opposite sides of the mapping. Before it, the string was
`metadata.google.internal。`: not in the deny list, ending in no known suffix.
After it, the string was `metadata.google.internal.` — with a trailing dot the
strip had already run past, which is why `.endswith(".internal")` was false
there too.

Two consequences. The first is the one that matters: every special-use hostname
became reachable by appending one character. `metadata.google.internal.` is the
exact name GCE resolves to 169.254.169.254, the endpoint that hands out service
account tokens. The address tables could never have caught it, because a
split-horizon internal name is the case they exist to complement.

The second is quieter. `http://127。0。0。1/` came back with `literal=None` — the
policy declared it a *name*, not an address. Downstream that means the decision
gets deferred to whatever a resolver returns, for a destination the browser will
dial numerically without asking anyone. The module's whole reason to exist is
that every layer makes the same decision; here it handed the next layer a
different answer than the browser's.

## The fix is an ordering

```python
if ":" not in host:                      # IPv6 literals have nothing to map
    host = idna.uts46_remap(host, std3_rules=True, transitional=False)
# every check below now reads the string the browser will read
```

Seven lines moved. The tests I wrote to prove the bug went red first on
unpatched code — `localhost。`, `metadata.goog。`, `kubernetes.default.svc.cluster.local。`,
the fullwidth-digit literals — and green after.

## What made it invisible

Nothing in the test suite was wrong. The special-hostname tests passed
`localhost`, and `localhost` was denied. The IPv4-form tests passed
`2130706433`, and it was pinned. The suite had no non-ASCII authority in it at
all except one happy-path IDN and one string used to check that error messages
don't leak the URL.

That is the shape of the gap. A test suite proves the cases it contains, and a
security check written against ASCII gets tested against ASCII, by the same
person, in the same sitting. Coverage percentage says nothing here — the lines
all ran. What was missing was an input class, and input classes don't show up in
a coverage report.

The second finding from the same review has the same signature. `classify_address`
accepted an iterable of operator deny ranges, materialized it with `tuple()`,
and then recursed into IPv4-mapped IPv6 addresses passing along the *original*
iterable — by then exhausted. Deny a range, wrap the address in `::ffff:`, and
the range no longer applied. There were tests for operator denies with
generators, and tests for operator denies inside transition addresses. Neither
combined the two, and the one combination that existed only in the gap between
them was the broken one.

Both bugs lived where two correct-looking things met. Neither was reachable by
reading either side alone.
