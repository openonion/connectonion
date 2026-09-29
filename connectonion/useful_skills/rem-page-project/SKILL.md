---
name: rem-page-project
description: A project page with a short visual overview and evidence-backed detail.
---

# A project's page

Why these rules: docs/rem-skills/rem-page-project.md

**How to do it.** Read the page and the material in full. Never search example
pages, earlier outputs, logs, skills or the repository for a format; look beyond
the material only for a named gap, recording what you checked in
`Uncertainties`. Write once, check once, fix in one edit, stop.

Write for a first-time reader (designer, programmer, operator, nontechnical
colleague): purpose and flow before implementation, short opening, plain
language, terms explained. Use exactly these headings:

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

- `What it is`: one plain sentence: who uses it, to achieve what. No history,
  stack inventory or unexplained acronyms.
- `Overview`: a compact ASCII diagram in a fenced `text` block, normally 3–7
  labelled steps, about 5–10 lines, narrow-screen readable: the user's starting
  point, main actions or service interactions, outcome. At most one short
  sentence. Product/work flow only; modules go in `Architecture map`.
- `Try it`: main entry point and a tiny example task with its visible result,
  at most three steps; link a screenshot or walkthrough if one exists. Say if
  access is needed, if it is a prototype, or that no working entry point exists.
  Never invent a URL, screenshot or successful run; never publish credentials.

Keep caveats and link lists out of the opening; limitations go in
`Uncertainties`. An unknown flow stays Unknown; a plausible diagram is not
evidence.

**Current work and joining the team**

- `Where it stands`: observation date; last activity date (say if quiet for
  months); current phase, goal, success criteria; completed versus planned work;
  latest verified run or test result with date ("11 tests pass, 2026-09-18"), or
  none found. Passing results go here, not `Latest issues`. A snapshot, not a log.
- `Latest issues`: recent bugs, regressions, blockers, newest first: date,
  symptom, user impact, status, evidence, and a next diagnostic step or issue
  link when known. A report is not a verified diagnosis; a proposed fix is not a
  verified resolution. If none found, name the checked scope and date.
- `People and ownership`: who to ask about product, design, engineering,
  operations, where known; link person pages or verified contact routes. Never
  infer ownership from a commit or message alone.
- `Getting started`: short orientation, then paths per relevant role (designer:
  design file, user journey; engineer: repo, setup, validation commands;
  operator: operating guide). Prerequisites, commands and expected outputs only
  when verified. Omit irrelevant roles; long inventories go in `Paths`.

**Background and technical detail**

- `Why it exists`: original problem, user needs, intended outcomes, scope
  boundaries, and what it contributes to the company when supported.
- `Key decisions`: dated product, design or technical choices, why, tradeoffs,
  sources. Label proposals and superseded choices; separate recorded rationale
  from inference. Current behaviour alone is not a decision: describe it in
  `Where it stands` / `How it is built`, rationale unknown. With no source, say
  no recorded decision was found; keep sourced decisions even without rationale.
- `How it is built`: main components and responsibilities, enough to begin
  work; link deeper documents, do not reproduce them.
- `Architecture map`: ASCII diagram of verified modules and labelled
  connections/data flow; a compact directory tree if useful. Cite inspected
  paths and revision/date outside the diagram. Label proposed structure apart
  from implemented.
- `Paths`: observed repositories, directories, worktrees, design/doc locations,
  each with its purpose. Never guess paths.
- `Open threads`: next action, owner when known, date; refer to issue entries
  rather than repeating them.
- `Uncertainties`: missing, unread, stale or conflicting evidence; what to
  check next.
- `Sources`: numbered references: source id, observation date, confidence.
  Cite every investigated claim; each inspected file (sample inputs and outputs
  too) is its own entry. Mark inference; never copy facts from examples.

**Two stages, one page**

Mapping creates missing pages with observed metadata only; unsupported sections
stay `Unknown — not investigated yet`. Never manufacture diagrams, owners, demos
or decisions. Investigation fills the sections from evidence. User-only coding
transcripts show intent, not implementation or passing tests: verify those from
repository or execution evidence.

On an older page, add missing sections and reorder to this shape, keeping
supported content and identity. Never reuse an architecture diagram as the
overview. Mapping reruns preserve existing pages. Leave the `Investigation:`
line unchanged. Keep the mapped `Sessions`, `First seen` and `Last seen` fields
in `Paths` exactly; never drop them or substitute the investigation date.
