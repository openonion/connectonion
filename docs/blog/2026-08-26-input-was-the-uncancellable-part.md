# Input Was the Uncancellable Part

*2026-08-26*

The browser was closed. The task was cancelled. Nothing was running in the
terminal.

One thread was still waiting for me to type “yes.”

It came from the least browser-like method in the driver. When a site requires
2FA, `wait_for_manual_login()` pauses automation while a person signs in, then
asks for confirmation in the terminal. The synchronous implementation used
`input()`. During the async migration, the obvious replacement was:

```python
await asyncio.to_thread(input, "Ready to continue? ")
```

The event loop stayed responsive. The test looked green. Then we cancelled the
task.

## The future stopped; the input did not

Cancellation stopped the coroutine that was waiting for the worker thread. It
could not stop the thread inside `input()`. That worker still owned a read from
stdin, with no useful way to interrupt or reclaim it.

The leak was quiet. There was no busy loop and almost no CPU usage. It became
visible only when another manual-login request arrived. Two tabs now believed
they were waiting for the same terminal. A line intended for the live prompt
could wake the abandoned one instead. Repeating the sequence could leave more
blocked workers behind each time.

This was not a thread-pool sizing problem. More workers would merely allow more
uncancellable reads.

## Wait for readiness, not for a worker

On POSIX, stdin is a file descriptor. The event loop can register interest in
that descriptor and call `readline()` only after the terminal says data is
ready. Cancellation now unregisters the reader in `finally`; no thread exists to
outlive the task.

Windows console input has a different boundary, so it uses short awaited polls
for available key presses. Between polls, cancellation behaves like any other
async operation. Backspace, Enter, and Ctrl-C retain their terminal meanings.

There was one more ownership mistake to fix. Browser pages belong to sessions,
but stdin belongs to the process. Per-tab locks cannot protect it. The runtime
now has one manual-login lock, so only one tab may display and consume a prompt
at a time. Hosted deployments still refuse immediately and direct callers to
the saved-state workflow because they have no interactive terminal to own.

## The test that matters

The regression test does not merely assert that the method is declared with
`async def`. It starts a POSIX read, cancels it, and verifies that the exact file
descriptor was removed. A second test starts prompts from two tabs and proves
the second cannot read until the first has confirmed and released the shared
terminal.

The final browser verb turned out not to be about browser automation at all. It
was about naming the resource correctly. Moving a blocking call to a thread can
protect an event loop, but it cannot invent cancellation. When the resource is
global and the operation cannot be stopped, the async boundary has to move
closer to the resource itself.
