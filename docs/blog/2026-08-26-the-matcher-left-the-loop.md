# The Matcher Left the Loop

*2026-08-26*

The browser action was declared `async`. Its DOM scan was awaited. Its pointer
movement was awaited. An unrelated tab could still freeze while the action tried
to understand “the publish button.”

The model call in the middle was synchronous.

## Async syntax does not move blocking work

ConnectOnion's element finder first extracts visible controls, gives each one a
stable locator, and asks a model to choose an index. That last step uses the
same synchronous `llm_do` API as the existing browser. Calling it from an async
method would occupy the one event-loop thread until the provider replied.
Per-tab locks would remain logically correct, but tab B could not run while tab
A waited on the network.

We kept one matcher rather than translating its prompt and ambiguity rules into
a parallel async implementation. The async core awaits DOM extraction on the
page, writes its debug artifact in a worker, then runs the existing matcher in a
worker thread with the extracted elements. The requesting tab retains its lock;
other tabs retain the event loop.

Cancellation has an honest limit here. Python can stop awaiting a worker-thread
result, but it cannot safely kill the thread already inside a provider call. The
worker owns no Patchright page and performs no browser mutation, so the browser
runtime remains safe while that call winds down.

## The real DOM found the routing bug

Unit tests covered main pages, iframes, shadow roots, bounding boxes, forced
clicks, and coordinate fallbacks. Native Chrome still found a case the fakes did
not: a `data:` page URL contained the text `editor`, which was also the iframe's
name. URL-substring fallback selected the main frame before the resolver reached
the exact iframe name.

Frame resolution now checks every exact name first and only then considers URL
substrings. The native gate extracts and acts on controls in the main DOM, a
named iframe, and an open shadow root. It also blocks one model match and
requires another tab to read its page within 500 milliseconds.

The important claim is no longer that the methods are coroutines. It is that
waiting for language on one tab does not take the browser away from everyone
else.
