# The second walk

After the first round of testing, 1.8.8b9 carried a dozen fixes, each pinned
by a test that had failed first. It would have been easy to call that done.
Instead the same five testers installed b9 from PyPI into empty profiles and
walked the same five paths again, with one new instruction: for every problem
from the first walk, say FIXED, NOT FIXED or PARTLY, and show the evidence.

Most of it held, and it held where it mattered. On the hosting walk, a stale
"approve" from a second device was refused with `STALE_ANSWER` — directly and
through the relay, for approvals and for questions — and never landed on the
next request. A visitor's Home page listed only the visitor's own runs. A bare
stranger was refused by rule, and the owner's balance did not move.

What the second walk found was of a different kind. The first round's bugs
were wrong answers. The second round's were waits: a browser command that
asked Chrome for its cookies while Chrome waited on a Keychain prompt, and
never came back; a phone that joined a session while its Home page was still
rendering, and missed the turn that started in that second; a first benchmark
whose example had no data in it, so the agent went looking for some for five
minutes and a dollar. None of them fails a unit test that does not wait, and
all of them are what a new user meets first.

The pattern we are keeping is the second walk itself. A fix is a claim about
the product, and the only evidence that counts is the published artifact doing
the right thing for someone who has never seen it. Capturing this release's
own picture found one more: `co create` into a folder that exists signed a new
user up for an account before telling them the folder was taken. It checks
the folder first now.
