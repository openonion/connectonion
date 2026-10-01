---
name: rem-page-project
description: A project page with a short visual overview and evidence-backed detail.
---

# A project's page

Why these rules: docs/rem-skills/rem-page-project.md

**How to do it.** Read the page and the material in full. Never search example
pages, earlier outputs, logs, skills or the repository for a format; look beyond
the material only for a named gap. Write once, check once, fix in one edit, stop.

Write for a first-time reader (designer, programmer, operator, nontechnical
colleague): purpose and flow before implementation, plain language, terms
explained. Use exactly these headings:

```markdown
# <Name>

## Facts

## Insight

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

**Facts and Insight first**

- `Facts`, one line a field, labels exact, all present, missing exactly
  `Unknown`: `Repository`, `Stack`, `Status`, `People`, `Organisation`,
  `Started`, `Last activity`. Several values `; ` between, each
  `value (qualifier) [n]`; dates `YYYY-MM-DD`; every value cited.
- `Insight`: 2–4 cited bullets of at most 30 words, each starting `Now:`, `Changed:`, `At stake:`
  or `Pattern:`. The first is the resume card: where the user stopped, what is
  next, what blocks it (`Now: stopped 2026-09-28 mid Outlook import; next the
  attachment retry; blocked on Graph 500s [4][6]`). Then what moved recently,
  what is at risk, or a pattern (`Pattern: three restarts of the same parser
  since July [2][5][9]`). Never generic ("an important initiative"); thin
  material: `- Unknown`.

**The opening: one sentence, one diagram, one entry point**

- `What it is`: one plain sentence: the product, who uses it, to achieve what;
  never the most-discussed side thread, no history or stack inventory.
- `Overview`: a compact ASCII diagram in a fenced `text` block, 3–7 labelled
  steps, narrow-screen readable: the user's start, main actions, outcome.
  Product flow only; modules go in `Architecture map`.
- `Try it`: entry point and a tiny example with its visible result, at most
  three steps. Say if access is needed or no working entry point exists. Never
  invent a URL, screenshot or run; never publish credentials.

An unknown flow stays Unknown; a plausible diagram is not evidence.

**Current work and joining the team**

- `Where it stands`: 3–5 bullets, now, not a log: last activity date (say if
  quiet for months); current phase and goal; latest verified run or test result
  with date, or none found. The past goes in `Key decisions`.
- `Latest issues`: bugs, regressions, blockers, newest first: date, symptom,
  impact, status, evidence, next step. A report is not a diagnosis; a proposed
  fix is not a resolution.
- `People and ownership`: who to ask, by area, where known; link person pages.
  Never infer ownership from one commit or message.
- `Getting started`: per relevant role (designer, engineer, operator); commands
  and expected outputs only when verified.

**Background and technical detail**

- `Why it exists`: original problem, user needs, intended outcome, scope.
- `Key decisions`: dated choices, why, tradeoffs, sources; label proposals and
  superseded ones. Current behaviour alone is not a decision.
- `How it is built`: main components and responsibilities; link deeper docs.
- `Architecture map`: ASCII diagram of verified modules and data flow; cite
  inspected paths and revision outside it; label proposed apart from built.
- `Paths`: observed repositories, directories, design/doc locations, each with
  its purpose. Never guess paths.
- `Open threads`: next action, owner when known, date.
- `Uncertainties`: missing, unread, stale or conflicting evidence, said once
  here rather than as a tail on every bullet elsewhere.
- `Sources`: numbered, `- [n] <source id> — <date>`, nothing more; each inspected
  file its own entry. Mark inference; never copy facts from examples.

State a claim in one clause. How the page was made (the mapper, the collector,
counts of matched sessions, the prior page) goes nowhere in the body.

**Two stages, one page**

Mapping writes observed metadata only; other sections stay
`Unknown — not investigated yet` until investigation fills them from evidence.
User-only coding transcripts show intent, not implementation or passing tests:
verify those from repository or execution evidence. On an older page, add
missing sections and reorder to this shape, keeping supported content. Never
reuse the architecture diagram as the overview. Leave the `Investigation:` line
unchanged. Keep the mapped `Sessions`, `First seen` and `Last seen` fields in
`Paths` exactly.
