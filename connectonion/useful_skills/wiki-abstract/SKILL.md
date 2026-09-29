---
name: wiki-abstract
description: Lift the notebook one layer — settled questions out of what happened, and recurring reasons out of settled questions. Reads pages, never sources, so it loads no source Skill.
---

# Abstract the layer above

Why these rules: docs/wiki-skills/wiki-abstract.md

Your input is **pages the notebook already holds**, never raw messages. If you
find yourself wanting the original mail or session, stop: that material belongs
to `wiki-investigate`.

Two lifts, and they run in order. `principles` cannot be written until
`decisions` exist.

## Lift one: decisions, out of what happened

A page in `decisions/` records **one question that got settled** — not one pull
request, not one thread, not one meeting.

The test for whether something is a decision at all:

> **Was an alternative rejected?**

"Fixed a typo" has no rejected alternative and is not a decision. "Used a
launchd interval tick rather than a calendar trigger" has one, and a reason.
Expect to discard most of what you read.

The entry key is the question, so **several artifacts collapse into one page**,
and a later reversal **edits that page** rather than opening a second:

```markdown
# Where the notebook is stored: Markdown or SQLite

Markdown. Chosen 2026-09-02 for portability; the user corrected the reason to
inspectability on 2026-09-07 and kept the choice. SQLite was discussed and not
adopted. Revisit only if plain-text search stops holding up.

## Why
Pages have to be readable and fixable without the tool that wrote them. SQLite
would have made search cheaper and every other kind of inspection harder.

## What it cost
Search is linear. At 143 pages that is not yet a problem.

Sources: PR #1234, PR #1288 (the correction), codex:s1:347
```

Four sections, and the second one is load-bearing: **`## Why` is the raw
material of the next lift.** Record the question, the alternatives, why the
others lost, and whether it was ever reversed.

## Lift two: principles, out of decisions

A principle is **a reason that keeps coming back**; never extract one from a
single source.

Read the `## Why` of every decision page and group them by the reason, not by
the topic (three decisions that each measured behaviour instead of trusting an
API's self-report become "Do not trust an API's report of itself; measure the
behaviour").

**Three decisions minimum**; never write a principle from one or two. Name the
decisions that produced it:

```markdown
# Do not trust an API's report of itself; measure the behaviour

Three times the documented or self-reported answer disagreed with what the
system did, and each time the measurement was right.

Drawn from:
- [Scheduling rides a tick, not a calendar](./scheduling-tick-vs-calendar.md)
- [Codex login is read from the credential](./codex-login-from-credential.md)
- [Codex isolation uses an empty CODEX_HOME](./codex-isolation-empty-home.md)

Reach for it when a check would otherwise be "the API says it is fine".
```

When a fourth decision joins, add it to that list — do not open a second page.

## What this stage must not do

- **Do not invent an abstraction to fill a category.** An empty `principles/`
  is the correct state until three decisions agree.
- **Do not restate a decision as a principle.** If the page reads like the
  decision with the specifics removed, it is a summary, not a lift.
- **Do not write `agenda/` or `opportunities/`.** Both are views computed from
  the Open threads and state already on entity pages.
