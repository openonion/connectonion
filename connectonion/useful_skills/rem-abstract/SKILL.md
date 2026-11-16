---
name: rem-abstract
description: Lift the notebook one layer — settled questions out of what happened, and recurring reasons out of settled questions. Reads pages, never sources, so it loads no source Skill.
---

# Abstract the layer above

Your input is **pages the notebook already holds**, never raw messages. If you
find yourself wanting the original mail or session, stop: that material belongs
to `rem-investigate`.

Three lifts, and they run in order: decisions, knowledge, principles. `principles` cannot be written until
`decisions` exist.

## Lift one: decisions, out of what happened

A page in `decisions/` records **one question that got settled** — not one pull
request, not one thread, not one meeting.

The test for whether something is a decision at all:

> **Was an alternative rejected?**

"Fixed a typo" has no rejected alternative and is not a decision. "Used a
launchd interval tick rather than a calendar trigger" has one, and a reason.
Expect to discard most of what you read.

Both must be on the pages you were given. **If the page would have to say that
the alternative or the reason is unknown or inferred, the verdict is
`not-a-decision`**: do not write the page. Review refuses one that says so.

Every offered captured line starts with a short ID in brackets, such as
`[d0123456789ab]`. Account for each line: either quote it in a decision page,
or give its verdict in your final message. One verdict per line, on its own line:

```text
VERDICT d0123456789ab not-a-decision
VERDICT dabcdef012345 merged decisions/storage.md
```

`not-a-decision` means no alternative was rejected, or the pages do not say
which alternative or why. `merged` means this line
belongs to the same settled question as another line; name the decision page
you wrote or updated this round. That page must pass review. These verdicts
finish the line without another attempt. A missing verdict leaves it for retry.
Use only IDs supplied in this packet; keep the IDs out of the notebook pages.
Also put the verdict lines in `report.md` at the path named by the task.
Repeat the verdict lines in your final message; a link to the report alone is not a verdict.

Copy the owner’s verbatim words into the body, immediately followed by its `[n]`.
Keep the quote and its citation on the same line, before `## Sources`.
Copy the quote exactly as captured in the supplied `## Decisions` or
`## Key decisions`; preserve its original source ID when renumbering citations.
Under `## Sources`, define each `[n]` with its original source ID, and end every
line with the page you read it on; a line without it is unfinished:
`- [n] <source ID> — originating page: <path>`. That section holds source definitions; the
owner’s quoted choice belongs beside the decision in the body.

The entry key is the question, so **several artifacts collapse into one page**,
and a later reversal **edits that page** rather than opening a second:

```markdown
# Where the notebook is stored: Markdown or SQLite

Markdown. Chosen 2026-09-02 for portability; the user corrected the reason to
inspectability on 2026-09-07 and kept the choice:
“Use Markdown so I can inspect the pages.” [1] SQLite was discussed and not
adopted. Revisit only if plain-text search stops holding up.

## Why
Pages have to be readable and fixable without the tool that wrote them. SQLite
would have made search cheaper and every other kind of inspection harder.

## What it cost
Search is linear. At 143 pages that is not yet a problem.

## Sources
- [1] codex:s1:347 — owner, 2026-09-07; originating page: `sessions/storage.md`, `## Decisions`.
```

Four parts (the lead, then `## Why`, `## What it cost` and `## Sources`), and
the second one is load-bearing: **`## Why` is the raw
material of the next lift.** Record the question, the alternatives, why the
others lost, and whether it was ever reversed.

## Lift two: principles, out of decisions

A principle is **a reason that keeps coming back**; never extract one from a
single source. A rule the user stated themselves ("from now on…") is already a
principle, written by `rem-maintain`; this lift finds the ones never said.

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

## Knowledge lift: after decisions, before principles

A page in `knowledge/` records **something learned that holds beyond one
decision**: how something works, what went wrong and why, or a method that
worked. Draw it from **at least two notebook pages** in `decisions/`,
`sessions/` or `projects/`, and name those pages under `## Drawn from`.
Read their settled experience, then write knowledge before lifting recurring
reasons into principles. Principles still need three decisions minimum.

This is not an Investigate topic page describing a subject from raw sources.
Create a new knowledge page, or append a clearly headed section to an existing
one. Never rewrite, replace or delete existing knowledge text, including a page
written by Investigate. Keep that page's title, sections and source definitions
exactly; put new evidence and its source definitions in the appended section.

Use the same quote and citation rule as decisions: copy the owner's verbatim
words into the body, immediately followed by `[n]`, and define the original
source ID under `## Sources`, keeping the originating page path as context.
For an appended section, use its own `### Sources` and fresh citation numbers.
Do not turn a paraphrase into a quote or reopen raw sources.

For example, after reading a scheduling decision and a project trial:

```markdown
# Checking whether a scheduled job actually ran

A saved schedule does not show whether the job ran. Check a run receipt after
the due time; in the trial a tick worked after calendar triggers failed.
“The calendar trigger never fired; the interval tick did.” [1]
“Check the run receipt after the due time.” [2]

## Drawn from
- [Scheduling trigger choice](../decisions/scheduling-trigger.md)
- [Scheduler trial](../projects/scheduler-trial.md)

## Sources
- [1] codex:schedule:12 — originating page: `decisions/scheduling-trigger.md`.
- [2] codex:trial:31 — originating page: `projects/scheduler-trial.md`.
```
