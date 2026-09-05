# Navigation Was Not Success

The proxy rejected every request, but `co browser go_to` exited successfully.
The page was empty. For an agent deciding whether to read the page or move on,
the command had supplied the wrong answer at exactly the decision point.

We had treated completion of `page.goto` as proof of navigation. A rejected
proxy challenge can return an HTTP 407 response without raising a driver
exception. Chrome can also commit its own network-error document. Neither
result is the destination the caller asked for, yet our code saved context and
printed “Navigated to” for both.

The fix checks those outcomes before announcing success. Proxy authentication
failure becomes `BrowserNavigationError: NAVIGATION_PROXY_AUTH_FAILED`;
Chromium network errors become `NAVIGATION_NETWORK_ERROR`. The existing daemon
exception boundary then produces a nonzero CLI exit. The messages deliberately
omit driver call logs and URLs, which can contain credentials. A blank body or
an ordinary HTTP 404 is still a legitimate page to inspect, not a reason to
invent a transport failure.

Three focused regressions failed before the change. With the fix, the async
core and daemon suites passed 58 tests. On the GCP acceptance machine, a real
headed browser navigated through a loopback proxy using the correct password
and read the expected marker, exiting 0. A fresh isolated session with the
wrong password was rejected by the proxy and exited 1 with the typed error.
No public site or purchased credit was needed for that check.

This closes a specific false-success path. It does not establish that every
proxy deployment or the separate paid-panel flow has passed release acceptance.
