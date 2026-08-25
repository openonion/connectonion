# The second tab was not concurrent

We already had one browser tab per agent. That looked like concurrency on the
board: `research` belonged to one task, `inbox` to another, and neither could
navigate the other's page.

Then we timed two 200 ms operations.

They took about 400 ms.

The tabs were isolated, but the daemon still accepted one connection, finished
its browser call, sent the reply, and only then accepted the next connection.
The browser driver added a second queue of its own: every synchronous Patchright
call ran through one worker thread. A named tab prevented corruption; it did not
let the second task move.

The fix was to choose one place that owns concurrency. The daemon now owns one
asyncio event loop and one async Patchright runtime. Each request is an asyncio
task. The browser core locks the page for that request's bound tab, not the whole
browser. Two requests for `research` still run in order. A request for `research`
and one for `inbox` can overlap.

Claims stay outside that scheduling decision. Before a task touches a page, a
small registry lock decides whether its caller owns the tab. Two callers racing
for `main` therefore cannot both pass an asynchronous check-then-write gap: one
records the claim and the other receives exit code 4. The winner also records a
request id in the tab metadata. A `finally` block removes that exact request id
after success, failure, or cancellation without deleting the longer-lived tab
owner.

We kept the native transports rather than hiding blocking Windows pipes behind
an unbounded default executor. POSIX connections enter the event loop directly.
Windows accept, authentication, read, and write calls cross a dedicated bounded
worker pool and submit to the same async dispatch path. Both sides cap admitted
clients, request bytes, read time, and reply time. Concurrency without those
bounds would only trade one global queue for an unlimited pile of tasks.
On Windows, a successful whole-browser `close` also waits for the exact daemon
PID that served it to exit. The next command can therefore cold-start against a
new named pipe instead of reaching the old daemon during its shutdown window.
Because closing a Windows listener does not interrupt an `accept` already
blocked in a worker, shutdown authenticates one internal wake connection and
discards it before joining the bounded worker pool.

The useful test is still the original stopwatch. Two independent 200 ms
operations go through the real local socket and overlap. The same-tab test takes
roughly 400 ms and proves ordering remains. A third test closes the client before
the reply, then checks that the request lease and active operation are gone while
the tab's durable owner is still present.

The lesson was not "replace threads with asyncio." It was that isolation and
concurrency are different properties. A tab map gave us isolation. Only moving
the daemon and the driver onto the same owned async runtime made the second tab
concurrent.
