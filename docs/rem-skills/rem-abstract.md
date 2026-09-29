# Why rem-abstract says what it says

The rules live in `connectonion/useful_skills/rem-abstract/SKILL.md`. This
file holds the reasons and measurements behind them; it is not loaded at
runtime (#1851).

## Pages, never sources

Reaching for the original mail or session in this stage is how a decision page
becomes a transcript. The split is also checked in code: `instructions("abstract",
"codex")` equals `instructions("abstract")`, because a stage that reads pages has
no business knowing which store they came from.

## Why the lifts run in order

A principle is not a thing anyone ever said, so it cannot be written until the
decisions it abstracts exist.

## Most of what you read is not a decision

Measured on a real repository: of 400 merged pull requests in five weeks, about
30 carry the "was an alternative rejected?" signal.

## `## Why` is load-bearing

A decision page that records only what was chosen grows nothing above it; the
reasons are the raw material of the principles lift.

## Grouping by the reason

A principle is never stated once, in any source, which is why it cannot be
extracted from one. Three real decisions from a single day, grouped by reason
rather than topic:

```
calendar triggers did not fire      → measured three times, changed to a tick
account/read answered null          → measured, read the credential instead
-c mcp_servers={} left servers on   → measured, gave it an empty CODEX_HOME
                                      ↓
        Do not trust an API's report of itself; measure the behaviour.
```

## Three decisions minimum

Two is a coincidence and one is an opinion; a page written from either is a
one-off dressed up as a rule. Naming the decisions lets a reader check the
abstraction rather than believe it. A notebook with one principle per decision
has none.

## No `agenda/` or `opportunities/`

Both are computed from Open threads and state on entity pages. Writing them in
this stage creates the same commitment twice, in two wordings.
