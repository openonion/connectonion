# The name stopped at the URL

The owner remembered a pull request that renamed Wiki and asked whether it
had reached the latest preview. I found the merged request, then checked the
published 1.9.0a18 wheel. Its package was called `connectonion.rem`. That
looked like an answer until I opened the reader code: the link it gave the
owner still ended in `/wiki`.

The original request had left that URL to O Chat, a separate repository.
I followed it there and found another merged request. The browser now said
“Rem” and offered working `co rem` commands, but its author had deliberately
kept the route while the SDK still depended on it. Each side was waiting for
a change across the repository boundary. Reading either merge alone would
have missed the unfinished handoff.

Then I checked the README. An earlier request had introduced the feature,
but a later rewrite had removed the introduction. One memory icon remained,
with `co wiki` in its tooltip. I could have repaired that line and stopped.
The comment above it said the block was generated, so I followed that source
back to the homepage. Its connection data still named the old command. A
future refresh would have undone the edit in front of me.

The fix needed to follow the same path I had just traced. The homepage now
supplies the current name, the README introduces co rem, and the SDK's live
link has a matching O Chat route. An old bookmark redirects there with its
page selection intact. I checked that handoff in a browser instead of
assuming that a renamed folder made a working destination.

That path also showed where spelling was carrying existing state. The
browser's saved reader session and the Host's signed transport still use
Wiki names internally. I kept them compatible: the owner's notebook and
chat history should not become collateral work in a public rename. The
remaining release step is ordered for the same reason: deploy the new
browser route before publishing a preview that sends people to it.

The lesson was in the owner's question. A merged rename was evidence about
one repository. To know whether the feature had actually changed its name,
I had to follow the link the owner would click, including the generator that
would write it again next week.
