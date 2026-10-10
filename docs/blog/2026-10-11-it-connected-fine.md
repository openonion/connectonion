---
description: co search said "could not connect" on half of real queries. It had connected fine, then stopped waiting at 20 seconds while the server took up to 46 and charged for the answer.
tags: [Search, CLI]
---

# It connected fine

`co search -e co` failed four queries in a row with the same message:

```
Search failed (network_error): co: could not connect (ReadTimeout).
```

The natural thing to do was check the network. The network was fine. We
sent the same four queries straight to `oo.openonion.ai/api/v1/search` with
the same key, and all four came back with HTTP 200. They took 11.9, 31.9,
45.5 and 8.1 seconds.

The client gave up at 20. That number came from the search engines a
`co search` usually calls: Serper, Brave and DuckDuckGo, which answer in
about a second. The managed engine is a different kind of thing. It is a
model doing a grounded search: it runs searches, reads the pages, and writes
an answer with sources. It took 8 to 46 seconds, so a 20-second limit fails
about half the time.

Two smaller things made it worse. The word `ReadTimeout` was right there in
the message, but the sentence around it said "could not connect", and people
read the sentence. And the server didn't stop when the client did. It
finished the search and charged for it, about four cents, for an answer no
one saw.

## Two changes

The managed engine now waits up to 90 seconds, measured from the slowest
answer we saw rather than borrowed from the other engines. The others keep
their 20.

A read timeout now has its own message, separate from connection errors:

```
Search failed (timeout): co: timed out after 90s; the search may still be charged.
```

A test checks that the request is sent with a read timeout of at least a
minute. Another raises `ReadTimeout` from the fake server and checks that
"could not connect" doesn't appear in the message and the charge is
mentioned. Both failed on main.
