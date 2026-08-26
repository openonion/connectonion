# The browser worked until the caller already had a loop

The async browser migration looked finished. The daemon could keep two tabs moving
at once, a blocked navigation no longer froze every client, and the old global
Playwright worker was gone. Then we tried the most ordinary server-side call:

```python
async def handle_request():
    browser.go_to("https://example.com")
```

`BrowserAutomation` has always been synchronous, so existing applications quite
reasonably call it from request handlers that already own an asyncio loop. Our first
facade tried to run the new coroutine with `asyncio.run()`. Python answered with the
error it reserves for exactly this mistake: an event loop was already running.

Making `go_to()` async would have made the error disappear, but only by handing it to
every user. Agent tools, scripts, context managers, and server workers would all have
to change for what was supposed to be an internal driver replacement.

The turn came from treating the loop as an owned resource instead of something to
borrow from the caller. Each facade now starts one private thread and one asyncio
loop. A synchronous call carries its session-tab binding across that boundary,
submits the core coroutine, waits, and returns the same ordinary value as before.
The request handler's loop is no longer nested or commandeered.

That solution created a second trap. We scheduled a facade call from its own browser
thread to see what would happen. The thread submitted work to its loop and then
waited for the result; the loop could not run the work because its only thread was
waiting. Nothing crashed. Nothing timed out. It simply stopped.

The fix is intentionally blunt: a synchronous facade call made from the owned
runtime thread raises `RuntimeError` before submission. A test schedules that exact
mistake on the loop and proves it fails instead of deadlocking.

Shutdown exposed the ownership rule one more time. A hosted session's `close()` must
release one tab, while an unbound `close()` must close the shared browser, stop the
loop, and join the thread. We retained every thread from repeated create-and-close
cycles in a test; if even one remained alive, the compatibility layer was not done.

The last surprise came from a repository search after the facade tests were green.
The stealth detector harness and the opt-in `human_jitter` plugin still reached into
the deleted private executor. They now use a narrow internal callback that runs
beside the async core on its owning loop. Driver objects no longer leak across the
thread boundary just because a diagnostic or plugin needs raw page work.

The lesson was not merely "put asyncio on another thread." Compatibility depends on
making ownership visible: who owns the loop, which session owns the tab, who may
block, and who must join at shutdown. Once those answers became executable tests,
the public API could stay synchronous while its implementation finally became async.
