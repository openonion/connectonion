---
name: rem-page-project
description: A project page with a short visual overview and evidence-backed detail.
---

# A project's page

Why these rules: docs/rem-skills/rem-page-project.md

**How to do it.** Read the page and supplied material. Do not search examples,
logs or the repository for a format. Write once, check once, fix once, stop.

Write purpose and flow before implementation, in plain language for a new
teammate; explain terms. The map is an unfinished scaffold.
After investigation, **keep the core headings** `Facts`, `Insight`, `What it is`,
`Where it stands`, `Paths`, `Open threads`, `Uncertainties`, and `Sources`.
Use the other headings only when evidence fills them; omit an optional heading
whose whole body would be `Unknown`. Keep the following order for those shown:

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
- `Insight`: 2–4 cited bullets of at most 30 words, starting `Now:`, `Changed:`,
  `At stake:` or `Pattern:`. Lead with a verified state, mismatch or decision
  that changes the next step, not a recap of the last request. Read the local
  repository packet first. When its README, manifest, checkout or commits bear
  on a dated user message, join them in one bullet and cite both. If unrelated,
  name the precise unknown and next verification; do not infer no fix from
  commit subjects. `Changed:` needs a verified change. A local commit does not
  prove tests or deployment. Thin material: `- Unknown`.
  With requests only, surface precise operating constraints; preserve branch
  versus organization scope.

**The opening: one sentence, one diagram, one entry point**

- `What it is`: one plain sentence: the product, who uses it, to achieve what;
  never the most-discussed side thread, no history or stack inventory.
- When shown, `Overview` is a compact ASCII diagram in a fenced `text` block, 3–7 labelled
  steps, narrow-screen readable: the user's start, main actions, outcome.
  Product flow only; modules go in `Architecture map`.
- When shown, `Try it` is an entry point and a tiny example with its visible result, at most
  three steps. Say if access is needed or no working entry point exists. Never
  invent a URL, screenshot or run; never publish credentials.

An unknown flow is omitted; a plausible diagram is not evidence.

**Current work and joining the team**

- `Where it stands`: 3–5 bullets, now, not a log: last activity date (say if
  quiet for months); current phase and goal; latest verified run or test result
  with date, or none found. The past goes in `Key decisions`.
- When shown, `Latest issues` lists bugs, regressions, blockers, newest first: date, symptom,
  impact, status, evidence, next step. A report is not a diagnosis; a proposed
  fix is not a resolution.
- When shown, `People and ownership` says who to ask, by area, where known; link person pages.
  Never infer someone else's ownership from one commit or message; the user's
  own sessions in the project's folders make the user its owner.
- When shown, `Getting started` is per relevant role (designer, engineer, operator); commands
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
  Recheck inherited clauses, quantities and dates against original sources.
  Joined claims need both messages; cite each clause.

State a claim in one clause. How the page was made (the mapper, the collector,
counts of matched sessions, the prior page) goes nowhere in the body.

**Two stages, one page**

Mapping writes observed metadata only; other sections stay
`Unknown — not investigated yet` until investigation fills them from evidence.
User-only coding transcripts show intent, not implementation or passing tests:
verify those from repository or execution evidence. On an older page, add
missing core sections and reorder to this shape, keeping supported optional
content. Never reuse the architecture diagram as the overview. Leave the
`Investigation:` line unchanged. Keep the mapped `Sessions`, `First seen` and
`Last seen` fields in `Paths` exactly.
