# A Thread Is Not an Async Runtime

*2026-08-26*

ConnectOnion already gave each browser session its own tab. Two agents could
hold different pages without navigating over each other, but they still could
not use them at the same time.

The browser had one worker thread. The daemon had one request loop. A slow
navigation on tab A blocked a text read on tab B even though the pages shared no
state beyond their browser context. Isolation existed; progress did not.

## Moving the queue is not removing it

An asyncio server in front of the existing driver would only move the waiting
line. Every request would still enter the single sync-Playwright worker. Changing
the driver import alone would be worse: helper modules still issue synchronous
Page calls, and a cancelled launch could leave Chrome holding the persistent
profile after the task appeared finished.

The migration therefore starts below the daemon. One internal core owns
Patchright's async API on one event loop. Session identity moves from
thread-local state to a `ContextVar`, so two tasks on the same thread do not see
each other's tab. A lock per tab keeps two commands from racing on one page,
while different tabs can interleave.

Lifecycle has its own boundary. Close stops new work, waits for operations
already admitted, and finishes context and driver cleanup even when its caller
is cancelled. An overlapping open fails instead of quietly reopening a browser
after another caller received “closed.”

## Liveness instead of a stopwatch race

Concurrency tests often compare total elapsed time: two 300 ms calls “should”
finish in less than 600 ms. That is fragile on a busy runner and can pass when
timing noise hides serialization.

The real-driver test instead holds a native two-second wait on tab A. While that
operation is still unfinished, tab B must return its page text within 500 ms. A
globally serialized driver cannot make progress on B until A returns, so it
cannot satisfy the condition. The test passed against the installed wheel and
native browser, proving independent progress rather than a favorable aggregate
duration.

This is the first #498 slice, not the declaration that the port is finished.
Humanized input, LLM element finding, the remaining browser verbs, concurrent
IPC, and the synchronous facade still have separate review boundaries. Keeping
those boundaries visible is how 1.8 gains concurrency without trading away the
browser behavior and cross-platform security it already has.

## Async parity is observable behavior

The next slice exposed a quieter migration risk. An async method existed for
counting selectors, but it returned an integer while the public method returned
`"2 elements match selector: button"`. Missing and out-of-range elements also
used different messages, and `wait(2)` omitted one word from its result. Each
implementation could drive the page correctly while still breaking an agent,
test, or caller that relied on the existing tool contract.

We now freeze three things for each deterministic verb: parameter names and
defaults, exact result shapes, and native DOM behavior. Contract tests compare
the old and async signatures and pin edge-case strings. A real-Chrome test then
exercises selectors, visible-item extraction, links, waits, and viewport changes.
This is intentionally narrower than copying every method at once: frame routing,
downloads, humanized input, and model-backed matching each introduce different
failure modes and retain their own review boundary.
