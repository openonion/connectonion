# Navigation Was Not Success

The proxy rejected every request, but `co browser go_to` exited successfully.
The page was empty. For an agent deciding whether to read the page or move on,
the command had supplied the wrong answer at exactly the decision point.

We had treated completion of `page.goto` as proof of navigation. A rejected
proxy challenge can return an HTTP 407 response without raising a driver
exception. Chrome can also commit its own network-error document. Neither
result is the destination the caller asked for, yet our code saved context and
printed “Navigated to” for both.

The empty page looked like a useful clue, but it was the wrong boundary to put
into the fix. A site is allowed to return nothing. A 404 page can contain exactly
the explanation an agent needs to read. Rejecting either would replace one
misleading answer with another. We needed to ask whether the browser had reached
a document from the destination, not whether that document looked useful.

That distinction led us back to the response and Chrome's internal error page.
We checked them before saving context or announcing success. On the GCP machine,
the correct proxy password still let the browser read our test marker. With the
wrong password, the command now exited 1. Then a tighter assertion failed: we had
expected a proxy-authentication error, but Chrome had surfaced a network error
instead of handing us the 407. The rejection was real; our expectation about how
the driver would describe it was too narrow.

The final check accepts either of those explicit failure paths, but never a
successful exit for the rejected navigation. Ordinary empty and 404 pages remain
readable. The focused suite passed 58 tests, and the real proxy check passed both
password cases. The useful change is small: an agent can now stop at the failed
navigation instead of trying to make sense of a page it never reached.
