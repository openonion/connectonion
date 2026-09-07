# The suffix list, and the table that checked itself

Two small holes in the destination policy, found by the review that also found
the two real bypasses. Neither was exploitable the day it was noted, and both
are the kind that becomes exploitable quietly.

## A suffix list is only as good as the names it lists

The policy denies special-use hostnames by suffix: `.localhost`, `.local`,
`.internal`, `.invalid`, `.test`, `.example`. That list is the *only* thing that
can stop a split-horizon name — a name that resolves, inside some network, to
an address the frozen IP tables would happily allow because it looks public.
That is exactly why `metadata.google.internal` was dangerous, and why the
earlier UTS-46 bug that let you smuggle it past the list mattered.

So the list has to be complete, and it was missing entries that resolve
split-horizon by design:

- `.arpa` — RFC 3172, and `home.arpa` under it (RFC 8375) is what an ordinary
  home router hands out
- `.alt` — RFC 9476, reserved for non-DNS namespaces
- `.onion` — RFC 7686; a name that must never reach the public resolver at all
- `.corp`, `.home`, `.lan`, `.intranet` — not reserved by anyone, which is
  precisely the problem: they are squatted for internal networks constantly,
  and a remote caller sharing your connection has no business reaching a host
  named that way

None of these had a test, so none were denied. Now they are, and the test that
proves it goes red on the code that shipped without them.

## A table that agrees with itself proves nothing

The frozen IPv4 and IPv6 tables are the deny-list of address ranges. There was
a test that walked them — before, inside, and after every network — and checked
the classifier agreed. It passed. It could not have failed for the reason that
matters, because it built its expected answer from the same tables the
classifier reads. Two uses of one list agreeing tells you they are the same
list. It cannot tell you the list is missing a range.

The fixture pins a registry snapshot date in a comment and cites the IANA
special-purpose registries by URL, which reads like a claim that the tables
match the registry. Nothing checked that claim.

So there is now a second list, transcribed from the IANA registries by hand and
kept in the fixture rather than derived from the code: every special-purpose
block that must be denied. The test asserts each one is covered by some frozen
network. Drop `198.18.0.0/15` from the table — the benchmarking range, easy to
think is harmless — and the test names it. It is still a hand-maintained list,
so it can drift too; the point is that it drifts *independently*, and a bug has
to be made in two places at once to hide.

Both fixes are the same shape as the bugs the review found in the code: a check
that measures the wrong thing looks exactly like a check that passes. The only
way to know the difference is to break the thing on purpose and watch the check
go red — which is what the mutation runs in this change do, once each, before
the fix goes in.
