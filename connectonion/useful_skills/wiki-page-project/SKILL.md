---
name: wiki-page-project
description: A project page with a short visual overview and evidence-backed detail.
---

# A project's page

This remains a project page, not a separately named onboarding page. As a design
test, read it through the eyes of someone seeing the project for the first time:
a designer, programmer, operator or nontechnical colleague. They should understand
the purpose and flow before reading implementation details. The page can be long; the opening must be short.
Use the reader's language, explain unfamiliar terms, and keep these exact headings
so mapping and investigation share one structure.

```markdown
# <Name>

## What it is

## Overview

## Try it

## Where it stands

## Latest issues

## People and ownership

## Getting started

## Why it exists

## Key decisions

## How it is built

## Architecture map

## Paths

## Open threads

## Uncertainties

## Sources
```

**The opening: one sentence, one diagram, one entry point**

- `What it is`: one plain-language sentence saying who uses this project and
  what it helps them achieve. No history, stack inventory or unexplained acronyms.
- `Overview`: a compact ASCII diagram in a fenced `text` block, normally 3–7
  labelled steps and about 5–10 lines. Show the user's starting point, main
  actions or service interactions, and resulting outcome. Keep it readable on a
  narrow screen. Use one short explanatory sentence only if needed. This is the
  product or work flow; reserve technical modules for `Architecture map` below.
- `Try it`: the main product/demo entry point and a tiny example task with its
  expected visible result. Prefer at most three short steps. Link a screenshot
  or walkthrough if available. Say whether access is needed or the demo is only
  a prototype; if there is no working entry point, say so. Never invent a URL,
  screenshot or successful run, and never publish credentials.

Do not fill the introduction with every caveat or link. Put supporting citations
next to claims and detailed limitations in `Uncertainties`. An unknown flow stays
Unknown; a plausible diagram is not evidence.

**Current work and joining the team**

- `Where it stands`: observation date, current phase, this phase's goal and
  success criteria, and the most important completed versus planned work. Keep
  this a short current snapshot rather than an exhaustive change log.
- `Latest issues`: recent concrete bugs, regressions and blockers, newest first.
  Record date, symptom, user impact, status and evidence; include a diagnostic
  next step or issue link when known. A report is not a verified diagnosis, and
  a proposed fix is not a verified resolution. If none were found, name the
  checked scope and date instead of claiming the project has no problems.
- `People and ownership`: who to ask about product, design, engineering and
  operations, where known. Link existing person pages or verified contact routes.
  Do not infer ownership merely from a commit or message.
- `Getting started`: a short shared orientation, followed by relevant paths for
  different roles. A designer may need the design file and user journey; an
  engineer the repository, setup and validation commands; an operator the
  operating guide. Include prerequisites, where commands run and expected
  outputs only when verified. Omit irrelevant role branches. Keep the main
  starting links here; put longer reference inventories in `Paths`.

**Background and technical detail**

- `Why it exists`: the original problem, user needs, intended outcomes and scope
  boundaries. Explain what the project contributes to the company when supported.
- `Key decisions`: dated important product, design or technical choices, why
  they were made, meaningful tradeoffs and sources. Label proposals and superseded
  choices; distinguish recorded rationale from your inference.
- `How it is built`: explain the main components and responsibilities, using
  enough detail for someone to begin work. Link deeper documents rather than
  reproducing them all.
- `Architecture map`: an ASCII diagram of verified technical modules and their
  connections/data flow. Label arrows; include a compact directory tree if useful.
  Cite inspected repository paths and revision/date outside the diagram. Label
  proposed structure separately from implemented structure.
- `Paths`: observed repositories, local directories, worktrees and supporting
  design/documentation locations. Explain what each is for; do not guess paths.
- `Open threads`: the broader action list, with next action, owner when known
  and date. Refer to issue entries rather than duplicating full issue descriptions.
- `Uncertainties`: missing, unread, stale or conflicting evidence, plus what to
  check next. Keep uncertainty explicit instead of making the page look complete.
- `Sources`: numbered claim references, with source identifier, observation date
  and confidence. Every investigated factual claim needs a matching citation.
  Mark inference explicitly. Never copy facts from examples.

**Two stages, one page**

Mapping creates missing pages and fills only observed metadata. Unsupported
sections remain `Unknown — not investigated yet`; do not manufacture diagrams,
owners, demos or decisions to fill the template. Investigation reads evidence
and fills the same sections. User-only coding transcripts record intent, not
proof that implementation or tests succeeded: verify those from repository or
execution evidence.

When investigating an older page, add missing sections and reorder them to this
shape while preserving supported content and identity. Do not reuse a technical
architecture diagram as a user-flow overview. Mapping reruns preserve existing
pages. Leave the runner-owned `Investigation:` line unchanged.
