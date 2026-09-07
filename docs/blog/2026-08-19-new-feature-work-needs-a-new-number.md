# New Feature Work Needs a New Number

The moment 1.7 was declared feature-frozen — "everything the eighteen alphas
built is now feature-complete, from here the line takes stabilisation fixes
only" — three PRs were already open against `main` that were exactly what
that sentence rules out: `co server new --region`, an authorization layer for
sharing an email address across accounts, and the signed grant primitives a
future proxy feature will need. None of them belonged on `release/1.7`
anymore. All three still needed to ship somewhere.

The version they landed in couldn't be another `1.7.0aN`. `main`'s
`pyproject.toml` still said `1.7.0a18` — the exact commit the beta was cut
from — and PEP 440 sorts `a19` before `b1`, which would have made three
genuinely new post-freeze features look, to any tool or person reading the
version, like they predated the beta they actually came after. The freeze
wasn't just a policy statement; it was the boundary a version number has to
respect once a beta exists on the other side of it.

So `main` gets its own next number: `1.8.0a1`. Cutting it is mechanical in a
way that's worth noticing — the same four files, the same test that fails if
they disagree, the same docs-site preview channel to update, run exactly the
way they were for every one of the eighteen 1.7 alphas before it. The only
thing that changed is which train the number names.

One of the three isn't a feature yet in the way a release note usually means
it: `connectonion.network.proxy` ships signed grant and delegation objects — a
real, tested authorization primitive — with no `co proxy` command anywhere
that uses it. It's in this release because merged code ships in every wheel
whether or not there's a command line pointed at it yet, not because there's
something to demo. The version history entry says so plainly rather than
implying a command exists that doesn't.
