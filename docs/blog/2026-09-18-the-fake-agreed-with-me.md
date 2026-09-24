# The Fake Agreed With Me

The browser could read a page's DOM and could not see a single byte it sent. So
`co browser requests` now lists what a tab asked for and `co browser request 3`
opens one of them — headers and bodies, both directions. Twenty-nine tests, all
green, written before the code the way you are supposed to.

Then it ran against a real page:

```
1  GET   200  document  435B  -1789769685953ms  http://127.0.0.1:8731/
```

Playwright's `ResourceTiming` has a `startTime` and a `responseEnd`, and I had
read those as two points on one clock, so the duration was the difference. They
are not. `startTime` is an absolute epoch in milliseconds; every other field in
that struct — `domainLookupStart`, `connectEnd`, `responseEnd` — is an offset
*from* it. `responseEnd` was already the answer. Subtracting gave the epoch back,
negated, which is exactly the number above.

An ordinary misreading of a docstring. What makes it worth writing down is the
test that was supposed to catch it:

```python
self.timing = {"startTime": 0, "responseEnd": 143}
...
assert record["duration_ms"] == 143
```

Read that fake again. `startTime: 0` is not a plausible value — it is 1 January
1970 — and I did not choose it because a page might return it. I chose it because
zero made my arithmetic come out right. Then the assertion confirmed the
arithmetic, and the suite went green on a function that could not compute a
duration.

This is a different failure from a test that simply misses a case. A gap leaves
you uncertain. This kind leaves you *confident*, because the fake and the code
were written in the same hour by the same person from the same misreading, and
they agree with each other perfectly. The suite was not measuring the API. It was
measuring whether I was self-consistent, and I was.

The fix is one line of code and a better fake:

```python
# As Playwright reports it: startTime is an absolute epoch, every
# other field is an offset from it.
self.timing = {"startTime": 1789769685953.0, "responseEnd": 143.0}
```

The assertion is unchanged and now means something, because the fake would embarrass
the old implementation instead of flattering it.

The rule that comes out of it is narrow enough to act on: **a fixture standing in
for something you did not write should carry values you observed, not values you
chose.** If you cannot say where a number in a fake came from, it came from your
belief about the code under test, and the test is a mirror. Print one real
payload first. It costs a minute, and the difference between `0` and
`1789769685953.0` is the whole difference between a test that checks and a test
that agrees.

Two releases ago the same suite shipped a race in an outbox that CI caught and
local runs did not. That one was a missing case. This one had a case, and the
case was wrong. Both were only visible from outside the tests — once from a
loaded CI runner, once from a page that actually loaded.

## Postscript, 24 September: it agreed with me again

Before this shipped, the verbs moved under `co browser network` —
`requests`, `request <n>`, and a new `har start` / `har stop` that writes a
standard HAR file — so the surface matches vercel-labs/agent-browser, and they
learned the tab names `-t` already had. Thirty new tests went green against
fakes. Then the HAR went through Playwright's own `route_from_har()` with the
site switched off, and the page rebuilt itself from the file: the format was
right. What was wrong was in the file's first line.

The page loaded *before* `har start` was in the recording. A request event
fires, the handler starts reading the body, and the body arrives a few
milliseconds later — after `start` had already run. The fake handed its body
back instantly, so no fake request could ever straddle the moment recording
began. A real one did on the first try. The record now keeps when its event
fired, and a recording takes only what fired while it was on.

The same run produced a false alarm worth writing down too: an image in
`--content all` came out empty. Chrome had thrown away a test PNG that was only
a header; a valid one round-tripped as base64. The first thing a real run tells
you is sometimes about the test.
