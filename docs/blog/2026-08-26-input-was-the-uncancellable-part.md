# Input Was the Uncancellable Part

*2026-08-26*

The last browser method to become asynchronous did not talk to the browser at
all. It waited for a person to type “yes.”

That made it more dangerous than it looked.

## A worker thread does not make input cancellable

The obvious port of `input()` is `asyncio.to_thread(input, prompt)`. It keeps the
event loop moving, but cancellation only stops waiting for the worker. The worker
itself remains blocked on stdin. Repeat that operation and a runtime can collect
threads that can neither finish nor be reclaimed. One future line of terminal
input may also wake an abandoned prompt instead of the active one.

The async browser now waits on stdin readiness directly on POSIX and unregisters
the file descriptor on every success, error, and cancellation path. Windows uses
short, awaited console polls so cancellation has a boundary between key presses.
One runtime-wide lock serializes prompts across tabs: pages are independent, but
the terminal is not. Hosted deployments still refuse immediately and point to
the state-seeding workflow because they have no interactive stdin.

## Cancellation must wait for the side effect

Page-context capture has the inverse problem. HTML, CSS, and element extraction
are naturally awaited, but filesystem writes are blocking. Moving them to a
thread protects the event loop; it does not make the write disappear when the
caller is cancelled.

Letting cancellation return immediately would leave a snapshot changing after
the tool reported that it had stopped. The capture path therefore finishes an
in-flight write before cancellation escapes. Concurrent tabs also reserve
distinct directories atomically, even when they use the same name in the same
second. A saved context is complete and attributable, not whichever tab won a
timestamp race.

## The fallback chain is part of the contract

Scrolling brought a different trap. ConnectOnion first emits real humanized
wheel input, then falls back to an AI-selected strategy, a scrollable element,
and finally the page. Each attempt is verified by comparing screenshots. An
async port that jumped straight to JavaScript would work mechanically while
discarding the human-input policy.

The new path preserves that order. Browser calls and pauses are awaited; model
selection and image comparison run off the event loop; cancellation stops later
mutations; and each verification image has a unique attempt identifier. A native
gate checks that wheel input changes the real page, not merely that a helper
returned a success string.

These were the final four missing verbs in the async driver surface. Their lesson
is the same one that shaped the earlier slices: `async def` is syntax. The real
contract is which state can be shared, when side effects are complete, and what
cancellation is allowed to leave behind.
