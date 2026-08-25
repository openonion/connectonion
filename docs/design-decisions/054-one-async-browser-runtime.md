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

The internal core is not exported as a public user API. The daemon now owns it
directly; the current synchronous Python API remains authoritative until #500's
facade and cross-platform compatibility matrices are green.

The #499 transport boundary keeps claim admission separate from page execution.
A registry lock performs unknown-tab validation, claim takeover/refusal, and a
request-scoped audit lease as one transition. The lease is keyed by a unique
request id and cleared in `finally`, so cancellation removes only the request
that was cancelled; it does not erase a durable owner or another in-flight
request. Once admitted, the async core's tab lock orders that page while other
tab locks remain free.

POSIX hands the already race-checked AF_UNIX listener to
`asyncio.start_unix_server`. It admits at most 32 connection tasks, rejects
excess connections without spawning more tasks, limits each request to 1 MiB,
and applies absolute 120-second read and reply deadlines. Windows retains the
authenticated `multiprocessing.connection` named-pipe wire. Its blocking
accept/read/write calls run through a dedicated eight-worker executor and feed
the same asyncio dispatch path; a 32-slot admission semaphore bounds queued
connections. Shutdown stops admission, cancels owned connection tasks, awaits
the browser runtime cleanup, and removes the endpoint only if its pid sidecar
still names this process.

The second #498 review boundary ports deterministic contracts that do not depend
on frames, downloads, humanized input, or model-backed element matching. It covers
tab-registry status; exact selector count/text/fill results; repeated-item and link
extraction; viewport changes; text and duration waits; raw selector extraction; and
platform shortcut guidance. Signature checks and exact result assertions compare
this boundary to `BrowserAutomation`; sharing a method name is not treated as parity.

The third boundary makes the deterministic core frame-aware. Page and frame
scripts share one local-path and JSON-validation contract. Direct file inputs and
file-chooser uploads enumerate the same filtered frame set, preserve global match
indexes, and await the locator, chooser, post-upload wait, and context save. It
deliberately does not port selector clicks: the public click path is humanized, so
substituting a raw async locator click would match the signature while changing the
observable behavior.

The fourth boundary ports known-target pointer and text input. It reuses the
synchronous layer's pure geometry, timing distributions, personas, text
segmentation, and clipboard rules, but every browser event and pause is awaited.
Selector clicks preserve exact-text filtering, global indexes across matching
frames, bounding-box pointer input, forced-click fallback, result strings, and
context-save ordering. CJK clipboard round trips run off the event loop, share one
runtime lock across tabs, and restore the previous clipboard before cancellation
escapes. Natural-language element matching, AI-selected scrolling, and form verbs
remain later #498 boundaries rather than being mixed into known-target input.

The fifth boundary ports model-selected element actions as one unit. DOM
extraction is awaited on the owning page, while debug-file writes and the
synchronous `llm_do` matcher run in worker threads. The matcher still uses the
existing prompt, `InteractiveElement` schema, ambiguity rules, and pre-built
locators; the async runtime does not invent a second selection policy. Exact
frame names take precedence over URL-substring fallback so a main `data:` URL
that happens to contain an iframe name cannot steal the target. Click, hover,
right-click, double-click, select, checkbox, and element-wait behavior preserve
their existing result and fallback contracts across the main DOM, named
iframes, and open shadow roots.

The sixth and final driver-parity boundary covers the four verbs left by the
whole-surface audit. Focused typing uses the same awaited humanization layer and
runtime clipboard lock. Scrolling preserves the human, AI, element, and page
fallback order while moving model calls and image comparison off the event
loop; every attempt gets a unique screenshot name. Page-context capture awaits
DOM reads, writes files off-loop into collision-safe directories, and does not
let cancellation escape while a write is still running. Manual login uses an
event-loop stdin reader on POSIX and cancellable console polling on Windows,
rather than leaving a blocked `input()` worker behind. Prompts are serialized
across tabs because the terminal, like the clipboard, is runtime-global state.

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
checks page isolation and focused-element behavior. Its frame fixture executes a
local script in a named `srcdoc` iframe, uploads one file directly, uploads another
through a real file-chooser event, and reads both selected filenames back from the
native DOM.

The macOS native gate runs with Chrome's mock keychain because the repository's
autouse fixture gives every test a disposable `HOME`. Production keeps the
existing real-keychain launch behavior for persistent cookies; mixing a fake
home with the real macOS keychain makes Chrome hang during context shutdown.

Before #498 closes, the async core must cover every current public browser verb,
the humanized-input acceptance suite, profile seeding/export, dead-context
recovery, downloads/uploads, screenshot payload bounds, and stealth checks.
Before #499 closes, slow-reader/writer, oversized/stalled client, admission-cap,
cancellation, disconnect, same-tab conflict, independent-tab progress,
cold-start, and shutdown load tests must pass on POSIX and Windows. Before #500 closes, repeated
sync and running-event-loop callers must leave no loop thread, task, page,
process, socket, or pipe behind.

The #499 native gate exercises the complete path rather than composing two mock
claims: a real socket client asks the real daemon to hold one real Chrome tab for
two seconds, then another client must read a second real tab within one second
and before the hold finishes. The transport-only matrix separately proves
same-tab ordering, a two-caller claim race, disconnect cleanup, and parallel
client admission without paying Chrome launch cost in every platform job.

The completed review boundaries additionally run against native Chrome. They
prove selector counts and text, repeated-item bounds, link filtering, text waits,
raw extraction, viewport changes, page/frame scripts, both upload paths,
exact-text/frame selector clicks, known-selector typing, anchor-relative clicks,
model-selected actions across main/iframe/shadow DOMs, main-document forms, and
independent-tab progress during humanized input and a stalled matcher on a real
DOM. The final gate also exercises focused typing, verified human scrolling,
context files, and hosted manual-login refusal. The whole public surface now has
an exact signature-parity test; #498 still closes only after the full regression,
installed-wheel, native-browser, hosted, cancellation, profile, stealth, and
recovery evidence is reviewed. These boundaries do not make the async core public.
