# A reason that nothing read

The paid browser reported when its session ended, and then kept serving pages
anyway.

Onionwright hands back a `terminal_reason` on a paid session: expiry,
revocation, non-payment. The daemon surfaced it — in `status`, once, next to the
session id and the paid-until time. That was the only place the word appeared
outside of writing it down. A grep for it in the whole codebase returned two
lines: the assignment, and the status field.

So the sequence was: a session ends upstream, Onionwright sets
`terminal_reason`, and the browser context it produced is still open. The next
`go_to`, the next `extract_data`, the next screenshot — all run. The session is
over; the browser is not. That is an unpaid browser doing paid work, and nothing
in the client stopped it, because nothing in the client read the field that says
to.

The fix is a guard at the one place every page command enters:

```python
def _require_live_paid_session(self):
    run = self._paid_run
    if run is None:
        return                       # free/system: never gated
    if getattr(run, "terminal_reason", None):
        raise PaidSessionEndedError(run.terminal_reason)
```

`_tab_operation` is the single async context manager that wraps `go_to`,
`extract_data`, every screenshot, every click. One call at the top of it, and a
terminated session refuses every verb with the reason attached, instead of
serving them.

The test that matters here is not the one that checks the guard raises — that is
easy and proves little. It is the one that asserts the guard is *called from the
entry point*, because the whole bug was a check that existed (the reason was
right there in `status`) and was never consulted. So the test reads the source of
`_tab_operation` and asserts the call is in it; remove the call and the test goes
red, which is the property that was actually missing — not "can this raise" but
"does anything invoke it."

There is a smaller lesson in how the guard almost shipped broken. Inserting the
new method just above `_tab_operation` slid the `@asynccontextmanager` decorator
onto the wrong function — it decorated the guard and left `_tab_operation` a bare
async generator. Every page command failed with `AttributeError: __aenter__`.
Eight existing tests caught it immediately, which is the argument for running the
whole file after a mechanical edit and not just the new test: the new test passed
in isolation while everything around it broke.
