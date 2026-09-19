---
title: Ten thousand tests found none of them
date: 2026-09-19
---

# Ten thousand tests found none of them

1.8.6 fixed twelve defects. The offline suite grew from 9,491 tests to 10,431
across the same nine previews. It reported **none** of the twelve.

Eleven were found by a person using the software. The twelfth was found by a
test — one written that afternoon, for a bug already found by using the
software.

That ratio is the most useful thing this release produced, so it is worth being
precise about what it does and does not mean.

## It does not mean the tests are bad

The suite caught plenty. Every refactor in those nine previews was safe because
of it, and a handful of times it stopped a change that would have broken
something three files away. It does the job it was built for.

The job it was built for is *this code does what this code did yesterday*. Not
one of the twelve was that.

## What they actually were

Lined up, they are the same defect twelve times:

- `mentioned: false` on a message that plainly `@`-ed the bot
- `✓ whatsapp reachable`, derived from a package being importable, a row in
  SQLite, a timestamp in a shared library, and a pid — no network anywhere
- `✓ Canceled`, for a delete that removed a different email
- `--since 30d` returning month-old mail
- a listener printing `listening` for hours after being unlinked
- a message that arrived undecryptable and was recorded nowhere
- `sent.jsonl` holding the Markdown that was typed while the group received its
  translation, so `log` showed a message nobody had seen
- `send` with no text: an empty bubble, a message id, exit 0

**Every one is a confident report of something that did not happen.** And every
one had a passing test, because the test asserted the same wrong thing the code
did. A decision table cannot tell you the table is wrong.

## Why using it works where asserting does not

When you assert, you write down what you expect and check for it. Your
expectation is the oracle, and a wrong expectation is invisible — it agrees
with itself forever.

When you *use* the thing, the oracle is the world. You @ the bot and watch for
a reply. You cancel a meeting and look in the calendar. You send a formatted
message and read it on a phone. The world does not share your misconception,
so it disagrees, and the disagreement is the finding.

The clearest case this cycle: I read `session.db`'s modification time as proof
a listener was alive. Forty minutes later I saw a perfectly healthy connection
whose file was three hours stale. The file records traffic, not liveness — a
signal with a lower bound and no upper bound, which I had been reading in both
directions. No test could have found that, because I would have written the
test from the same belief.

## The part that is uncomfortable

Two of the twelve were found in builds published an hour earlier. Green CI,
green suite, artifacts verified, installed and checked — then used, and broken.

Worse: I shipped a release *about* commands claiming things they had not
checked, and inside the same week wrote a log that recorded what was typed
while the wire carried something else. Knowing the shape by name did not stop
me producing it. The concept was in my head and the bug was in my hands and the
two did not meet until I read the record back.

## What changed as a result

Not the test count. Three things about how the work ends:

**Acceptance is against the artifact.** Not the checkout. Every gate in
[the 1.8.6 record](../acceptance/1.8.6/release-candidate-2026-09-19.md) was run
against the package installed from PyPI, with `PYTHONSAFEPATH=1` so `python -c`
could not quietly import the source tree instead. Twice in this session that
exact confusion made a version check meaningless.

**Claims get narrowed to what was measured.** The Ollama gate asks for "no
cloud keys". I deleted every key, and connectonion loaded them back from
`keys.env` at import. So that claim is not in the record. What is in the record
is the property actually wanted — no silent fallback — tested by pointing the
local endpoint at a closed port and confirming it *failed* with hosted keys
sitting right there.

**Inheritance is proved, not assumed.** The calendar journey was accepted a
week earlier on an older build. Instead of re-running it or waving it through, I
diffed the five calendar source files between the two commits: byte-identical.
The old result applies, and the reason it applies is in the file.

## If you take one thing

Ship it, then use it. Not "run the tests, then ship" — *use it*, on something
real, where being wrong costs you something.

The twelve defects in this release were all visible within seconds to anyone
actually looking at the result. What made them survive was that nobody was
looking at the result; we were looking at assertions about it, and the
assertions agreed.
