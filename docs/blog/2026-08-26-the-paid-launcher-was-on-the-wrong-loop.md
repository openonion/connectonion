# The paid launcher was on the wrong loop

The paid-browser PR and the async-browser PRs were each green. That made their
integration look like a merge-order problem: put the paid branch on top, resolve
the overlapping browser files, and run the tests again.

The conflict was architectural, not textual. ConnectOnion's final 1.8 runtime
owns Patchright's async API on one event loop. Onionwright's paid launcher owned
the sync Playwright API. A mock could accept either object, so the old seam test
proved only that ConnectOnion passed four arguments in the right order. A real
launch would call synchronous methods on an async driver and fail after the paid
boundary had already been approached.

The correction was to put the missing boundary where the lifecycle already
lived. Onionwright now exposes an async paid launcher alongside the synchronous
one. It still owns the exact prepared executable, first charge, licence flag,
renewal supervisor, signed expiry, and release. ConnectOnion keeps ownership of
its async page interaction layer. Neither repository reimplements the other's
responsibility.

Cancellation made the boundary sharper. A task can be cancelled while the
blocking start request is still running in a worker thread. Returning immediately
would leave us unable to know whether the server charged and created a session.
The launcher therefore completes that irreversible request, releases any session
it produced, and only then propagates cancellation. The same rule applies when
Chromium startup is cancelled after charging.

The final test no longer substitutes a fake `launch_paid` function. CI checks out
both repositories, builds a real Onionwright `PreparedBrowser`, enters
ConnectOnion through its synchronous public facade, crosses the actual async paid
launcher, verifies the exact executable and licence-file arguments, then observes
one context close, one server release, and one driver stop.

Two green branches are not an integration test. When one branch changes the
execution model, every irreversible boundary downstream must speak that model
directly—and the test must cross the real boundary rather than a shape-compatible
mock.
