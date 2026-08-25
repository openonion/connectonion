# One browser API, three different promises

The awkward part of adding a paid browser was not choosing an executable. It
was deciding exactly when ConnectOnion is allowed to change its mind.

`co browser` already has a useful promise: type a command and a browser opens.
Making Onion Browser available could easily have weakened that promise. A
missing package, unsupported CPU, unavailable artifact, or empty balance would
become a new reason ordinary automation did not work. Silently falling back
everywhere would be worse: a task could start with one fingerprint and continue
with another after money had crossed the boundary.

The 1.8 contract therefore has three explicit meanings. `system` is the hard
free path and returns before ConnectOnion imports Onionwright, reads a paid
credential, downloads an artifact, calls the billing API, or creates a session.
`onion` is strict: either the exact compatible artifact starts or the command
returns a typed failure. `auto` may choose system Chrome, but only before a paid
session exists.

That last sentence determines the architecture. Resolution first asks
Onionwright to prepare Chromium `150.0.7871.187`: normalize the host, obtain the
signed manifest entry, verify and unpack the artifact, and prove the executable
is ready. None of that charges. Only then does the real persistent-browser
launch seam call `launch_paid()` with that same prepared result. From that
point, the supervised Onion process owns renewal and release. Failure is
visible; ConnectOnion does not hot-swap it into system Chrome.

The process boundary mattered too. `co browser` keeps a daemon alive between
commands. An old daemon ignores new JSON fields, so merely adding
`"engine": "onion"` would let an explicit paid request reach the old system
browser before the client noticed. The new client sends a read-only
`engine_status` probe first for explicit Onion requests. An incompatible daemon
is refused before the requested page action is sent. The probe itself is
page-less: it neither launches a browser, claims a tab, nor overwrites the last
command.

The result was measured at the boundaries that can betray the design. The
combined browser, tab/session, CLI, engine, paid-launch, and real Unix-socket
daemon suite passes 209 tests. A separate source-level integration check imports
Onionwright's public `PaidSessionClient` and `launch_paid`; ConnectOnion never
scans its cache. Tests also prove `system` cannot touch the paid path, preflight
failure in `auto` falls back before billing, strict `onion` never falls back,
and paid launch failure never starts system Chrome.

The remaining work is deliberately outside this green result. Onionwright must
be released, and an architecture-specific browser artifact must be signed,
notarized where applicable, published immutably, downloaded again, and exercised
through the production licence path. Until then the paid catalogue stays empty.
Passing client tests proves the choice is safe; it does not manufacture a
browser we can honestly sell.
