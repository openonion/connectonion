# The pointer was still on its way

*2026-10-23*

An agent chose the right button and then appeared to wait for almost a minute.
The page eventually changed, so the operation looked successful in its final
receipt. In a long workflow, those successful minutes made the queue crawl.

Our first suspicion was that two layers were both drawing a human pointer
trajectory. The trace did not support it. The page received one curved approach,
but many consecutive movement events arrived about a second apart. Other clicks
on the same runtime were fast. Matching the page events to the command windows
put most of the delay before the button press, rather than in the final context
save. It located the slow phase without explaining the underlying runtime cause.

The approach was still trying to deliver every intermediate point after it had
fallen behind. For a click, the destination matters more than faithfully replaying
an old travel schedule. We kept the curve and gave each planned point a small
allowance for dispatch and pauses. Once a point is stale, the click approach may
skip it. The final coordinate is always awaited, including the existing overshoot
correction, before a button goes down. Ordinary moves and hover retain their
complete paths, since intermediate positions can be the point of those actions.

The small change needed more than a faster stopwatch. In a fresh native browser,
a local page counted trusted pointer events and changed its address after one
click. With an explicit one-second delay added after each mouse acknowledgement,
the old approach took 51.18 seconds and sent 50 moves; the new one took 5.36
seconds and sent five. Both reached the exact target, pressed once and completed
the fragment transition. Without that injected delay, both took about 1.15 seconds
and sent 50 moves. Failure and cancellation tests also checked that an unfinished
approach could not press the button.

That experiment supports a mitigation, not a diagnosis of the production browser.
The isolated browser's actual acknowledgements were fast. A sparse path is also
a real tradeoff, including at ordinary latency, and one blocked browser call can
still wait. In this delayed-dispatch fixture, skipping stale waypoints avoided replaying
most of that minute. The investigation into the production cadence remains open.

We also put the installed candidate through the current O Chat production
build. A real model requested two one-time tool approvals, clicked the static
fixture once and sent its screenshot through native Host image IO. The phone
reload check initially accepted cached completion text too soon; independent
review caught the still-reconnecting state. The corrected test now waits for a
new connection, the Send control and the same loaded image, while checking that
neither input nor click was replayed. [The scoped consumer acceptance](https://github.com/openonion/connectonion/blob/fa48f52885e7fea1d9b8c3b061e47f5c6da1f0a5/docs/acceptance/click-pacing-2026-10-23/README.md)
records the exact coverage and the remaining production boundary.

Getting the faster path into a working service exposed a second kind of wait.
The existing browser belonged to more than one task. Restarting it to load a
small input fix would have stopped someone else's work, so the reimbursement
worker needed a separately owned runtime. A healthy preflight was not enough:
the next CLI command could quietly start a replacement if that daemon died.
The supervisor's no-restart policy did not govern the client's startup path.

An optional daemon PID pin gives the managed worker a different contract from
an interactive terminal. Missing or changed ownership becomes a visible error,
including after an engine probe, rather than a request to create another
browser. Independent review followed the same boundary through close, where
force cleanup must not adopt a replacement process. A real CLI trial exercised
that boundary without opening a page or a paid session. The ordinary unpinned
CLI still starts a browser on demand.

The candidate packages both changes, but they have separate evidence. A bounded
gesture demonstrates less accumulated dispatch delay. A daemon pin identifies
which process the worker may use or clean up. Neither result proves the remaining
business queue is complete, or that copying a version number into a running
service has upgraded its live browser. That last step still needs a published
artifact, fresh runtime checks and an actual bounded business trial.
