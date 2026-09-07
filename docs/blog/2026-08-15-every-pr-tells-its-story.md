# Every PR tells its story

*2026-08-15*

We shipped a credit-transfer API months ago. It worked — production traffic,
onboard verification, the lot. This week we noticed that as far as any user or
any AI driving our CLI could tell, **the feature did not exist**. No command
exposed it, no help text mentioned it, no doc described it.

The code was fine. The story was missing.

That failure has a shape we keep meeting. A feature ships; the doc site lags;
someone asks "can it do X?" and the honest answer is "yes, but nothing will
tell you that." Documentation written *after* the fact is documentation that
loses a race, every time, forever.

## The fix is structural, not motivational

Telling people (or AIs) "please remember to write docs" does not work — we
know because we are the ones it did not work on. So the requirement moves into
the path where work already flows:

**Every PR ships a dev-blog post in the same diff.** A file under
`docs/blog/`, checked by CI (`blog-gate`). No post, no merge. The posts sync
to the docs site, so the site stays current as a side effect of merging —
nobody has to ask, nobody has to remember.

A maintainer can waive the gate with a `no-blog` label for a typo or a
lockfile bump. The label is the maintainer's call, not the author's — a
requirement the author can waive is a suggestion.

## What a post is

Not a changelog. The PR description already lists what changed; repeating it
here would be noise wearing a hat.

A post tells the story a reader would want: the problem as someone actually
hit it, what the fix teaches, what was measured. It is allowed to be three
paragraphs. It is allowed to say "we got this wrong first." The best ones
will say exactly that.

This post is the first one through its own gate.
