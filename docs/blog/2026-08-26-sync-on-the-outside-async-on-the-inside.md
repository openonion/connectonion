# Sync on the outside, async on the inside

Changing a browser driver from synchronous to asynchronous is easy if every caller
can change with it. `BrowserAutomation` could not make that bargain. It is already
used as an Agent tool, in context managers, in scripts, and from server workers.
Making every method return a coroutine would turn an internal driver migration into
a public breaking change.

ConnectOnion 1.8 keeps the old surface and changes the ownership underneath it.
Each `BrowserAutomation` instance owns one private thread, one asyncio event loop,
and one async browser core. A normal method call captures the caller's session-tab
binding, submits the matching coroutine to that loop, waits for the result, and
returns the same ordinary Python value as before.

The thread boundary matters most when the caller already has an event loop. Calling
`asyncio.run()` there would fail with a nested-loop error. Running the browser loop
in its own thread gives this case defined behavior: the synchronous call blocks its
caller, while the browser runtime continues normally. The inverse case is rejected.
If code somehow invokes the synchronous facade from the browser's own runtime
thread, waiting would deadlock that loop, so the call raises a direct `RuntimeError`.

Shutdown is part of the compatibility contract, not cleanup trivia. A session-bound
`close()` releases only that tab and leaves the shared runtime alive. An unbound
`close()` waits for the async core to finish closing its pages, context, and driver,
then stops and joins the event-loop thread. Repeated construction and close cycles
therefore do not accumulate loops or threads, and repeated close calls are harmless.

The useful tests operate at the boundary. They compare every public method name and
signature with the previous class, call the facade from inside an already-running
event loop, carry a session binding across the thread hop, attempt the forbidden
same-thread call, and repeat create/close cycles while retaining each old thread so
the test can prove all of them stopped.

The public API did not become async. Its implementation did. That distinction lets
existing code keep working while the daemon and direct Python tools finally share
one browser architecture.
