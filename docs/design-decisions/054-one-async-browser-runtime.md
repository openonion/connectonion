# DD-054: One async browser runtime, two compatibility edges

**Status:** In progress for 1.8

**Date:** 2026-08-26

**Related:** [#498](https://github.com/openonion/connectonion/issues/498),
[#499](https://github.com/openonion/connectonion/issues/499),
[#500](https://github.com/openonion/connectonion/issues/500),
[#208](https://github.com/openonion/connectonion/issues/208)

## Context

The existing browser is safe but globally serial. `BrowserAutomation` uses
Patchright's synchronous API and sends every public method through one worker
thread. The daemon likewise accepts one connection, reads one request, dispatches
it, and replies before accepting the next. Per-session tabs prevent one agent
from navigating another agent's page, but an unrelated slow tab still blocks the
whole browser.

Changing only the daemon would not create concurrency: all requests would queue
at the one-worker driver. Changing only the driver import would also be
incorrect. Element extraction and humanized input call the synchronous Page API,
and cancellation must release a persistent profile before another runtime opens
it.

## Decision

The 1.8 browser has one internal `AsyncBrowserCore`, owned by one asyncio event
loop. It imports only `patchright.async_api`; no synchronous Patchright call is
allowed below that boundary.

Session binding uses a `ContextVar`, because concurrent asyncio tasks can share
one operating-system thread. Each session retains its own page, metadata, and
restore URL. A lock per tab serializes conflicting operations on that page while
independent tabs may interleave. Context launch and shutdown use a separate
lifecycle lock.

Shutdown is an explicit state transition. It stops admission, waits for active
operations, closes the context and driver completely even if the caller is
cancelled, then releases the persistent profile. A launch that overlaps that
transition fails rather than reopening the browser behind a completed close.

The migration has three review boundaries:

1. **#498 — async driver contract.** Port lifecycle, tabs, deterministic
   selectors, scripts, input, downloads/uploads, screenshots, stealth behavior,
   LLM element finding, and humanized input. Equivalent old/new contract tests
   remain until the port is complete.
2. **#499 — concurrent transport.** Run client requests as bounded async tasks.
   POSIX uses an asyncio Unix server; the authenticated blocking Windows pipe
   boundary is bridged into bounded transport workers. Both submit to the same
   async browser runtime. Same-tab conflicts stay deterministic; independent
   tabs make progress concurrently.
3. **#500 — synchronous compatibility facade.** Existing
   `BrowserAutomation` methods submit to an owned loop thread without nesting a
   caller's running event loop. The facade is compatibility, not a second driver.

The internal core is not exported as a public user API while #498 is incomplete.
The current synchronous API and daemon remain authoritative until the complete
contract and cross-platform transport matrices are green.

## Invariants

- one persistent browser context and profile per runtime;
- one page and one operation lock per bound session;
- independent tab operations can interleave; operations on one tab cannot;
- a cancelled launch or close leaves no context, driver, or profile owner;
- close never tears down another task while it is operating;
- passwords remain redacted and destructive shortcuts remain fail-closed;
- existing result strings, timeout behavior, claims, authkey recovery, and
  Windows/POSIX framing do not change accidentally;
- no release claims async completion while any in-use path still reaches the
  synchronous core.

## Verification

Every migration PR must include isolated async contract tests. The real-driver
gate holds a native two-second wait on one session page while requiring a text
read on another page to finish within 500 ms and before the wait completes. A
globally serialized driver cannot satisfy that liveness condition. The gate also
checks page isolation and focused-element behavior.

The macOS native gate runs with Chrome's mock keychain because the repository's
autouse fixture gives every test a disposable `HOME`. Production keeps the
existing real-keychain launch behavior for persistent cookies; mixing a fake
home with the real macOS keychain makes Chrome hang during context shutdown.

Before #498 closes, the async core must cover every current public browser verb,
the humanized-input acceptance suite, profile seeding/export, dead-context
recovery, downloads/uploads, screenshot payload bounds, and stealth checks.
Before #499 closes, slow-reader/writer, stalled client, cancellation,
disconnect, same-tab conflict, independent-tab progress, cold-start, and
shutdown load tests must pass on POSIX and Windows. Before #500 closes, repeated
sync and running-event-loop callers must leave no loop thread, task, page,
process, socket, or pipe behind.
