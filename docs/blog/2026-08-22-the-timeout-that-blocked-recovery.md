# The Timeout That Blocked Recovery

The release browser opened a localhost page that `curl` could fetch with a 200
response and a complete 20 KB body. Playwright still did not observe
`DOMContentLoaded` within 30 seconds, so `go_to` correctly returned a timeout.
That should have left several useful choices: press Escape, inspect the current
URL, take a screenshot, retry, or close the owned tab.

None of them worked. The browser daemon sent the timeout to its first client,
then performed a context-liveness check before accepting the next connection.
That check was another synchronous browser round trip on the same single
Playwright worker. The page that had just failed to settle also blocked the
probe, turning one bounded request failure into an unbounded daemon failure.

Killing the daemon would have made the release test continue, but it is the
wrong recovery model for a shared persistent browser. One task's bad page must
not discard unrelated tabs, login state, or another agent's work. Treating the
timeout as proof that the browser had died was also false: Chromium was still
open and could be recovered by stopping the load.

The daemon now returns a browser timeout without immediately asking the same
browser another synchronous question. It records that a context existed and
accepts the recovery command sequence without inserting that probe between
steps. A fresh successful navigation restores normal liveness checks; explicit
closure and closed-target errors still release the daemon immediately.

The regression makes the old trap explicit. A fake page command raises
`TimeoutError`; its liveness method fails if called before recovery; the next
Escape command must still receive a response. The focused recovery set passes
five tests, and the complete browser-daemon file passes all 86.

A timeout is already an answer. Recovery code should not repeat the operation
that just stopped answering before it gives the caller a chance to recover.
