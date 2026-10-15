---
name: rem-page-project
description: A project page a new teammate understands in one screen: what it is, why, where it stands, what is next.
---

# A project's page

Write for a teammate who has one minute. The first screen answers, dated and
cited: what the project is, why it exists in the owner's words, where it
stands now, and what is still open. Reference detail follows. A page that
tours files and hedges every line fails even when every line is true.
Read the page and material. Write once, check once, fix once, stop.
Search the repo for evidence, not for a format: this Skill is the format.

Keep the core headings `Facts`, `Insight`, `What it is`, `Where it stands`,
`Open threads`, `Paths`, `Uncertainties` and `Sources`. Show any other heading
only when evidence fills it; omit one whose whole body would be `Unknown`.
Keep this order for those shown:

```markdown
# <Name>

## Facts

## Insight

## What it is

## Why it exists

## Where it stands

## Open threads

## Latest issues

## Key decisions

## Overview

## Try it

## People and ownership

## Getting started

## How it is built

## Architecture map

## Paths

## Uncertainties

## Sources
```

**Facts**: one line a field, labels exact, all present, missing exactly
`Unknown`: `Repository`, `Stack`, `Status`, `People`, `Organisation`,
`Started`, `Last activity`. Several values `; ` between, each
`value (qualifier) [n]`; dates `YYYY-MM-DD`; every value cited.
- `Status`: a phrase the evidence earns: `active — commits weekly on
  origin/main`, `quiet since 2026-08-10`, `exploring, nothing chosen`.
- `Last activity`: the newer of the latest commit on the current line and
  the latest message that names this project, with what it was:
  `2026-10-15 — Gemini 4 Argon made selectable (commit e25df6e) [n]`.
- `Started`: the first commit or the owner's words that began it; the first
  observed session is not a start.

**Insight**: 2–4 cited bullets of at most 30 words, starting `Now:`,
`Changed:`, `At stake:` or `Pattern:`: what changes a teammate's next
decision. A reversed choice, a requirement that moved, or a conflict between
the owner's words and the code (the owner says 8% of net, the PDF says gross).
A branch, commit date or README topic is not an insight. None: `- Unknown`.

**What it is**: one or two sentences: the product, who it serves, what it
does, from the README or the owner's description of the whole project, never
the loudest recent thread.

**Why it exists**: the problem and intended outcome, opened with the owner's
words that started it or best state its purpose:
`YYYY-MM-DD — “<exact words>” [n]`. The newest request is not why a project
exists; without such words, cite the README's purpose statement.

**Where it stands**: 3–5 bullets about now, newest first, each dated: the
latest finished work (commit subjects on the current line, the owner's
latest messages; quiet for weeks — say so); work in flight (recent unmerged
branches, by name and date); the phase and goal; the latest run, test or
deploy result someone reported, or none found. History goes in `Key decisions`.

**Open threads**: only what is pending now, newest first:
`- YYYY-MM-DD — <who> asked: “<exact words>” [n] — open|blocked on <what>`.
Before listing an ask, look for its outcome in later messages, commit
subjects and branch names. One closed by a commit or a later message moves to
`Where it stands` or `Key decisions` with that evidence. An ask more than 30
days old with no outcome found is history, not an open thread: leave it out.
Nothing open: bare `Unknown`, never a "no pending work" line.

**Latest issues**: bugs, regressions, blockers, newest first: date, symptom,
status with its evidence. Check the history for a fix before calling one
open. A report is not a diagnosis; a proposed fix is not a resolution.

**Key decisions**: `- YYYY-MM-DD — <choice, under 12 words>: “<the owner's
exact words>” [n]`. A reversal is its own line quoting the reversal. A
request alone or current behaviour alone is not a decision; label proposals.

**Overview** and **Try it**, when the README, docs or code at the current line
show them: `Overview` is 3–7 narrow ASCII steps in a `text` fence (user start,
actions, outcome); `Try it` is an entry point, a tiny example and the visible
result, at most three steps, in the source's order. A plausible diagram is
not evidence; an unknown flow is omitted.

**People and ownership**: who to ask, by area, linking person pages. One
commit or message never makes someone an owner.

**Getting started**: per role, commands and outputs only when verified.

**How it is built** and **Architecture map**: main components and data flow
from files at the current line, citing the revision; label proposed apart
from built. Short: a page is not a code tour.

**Paths**: the project's own folders (repository, data or design locations
outside it) with their purpose; modules belong in `How it is built`. Never guess.

**Uncertainties**: at most five, each one that would change the next step;
provenance limits are said once here, not on every bullet.

**Sources**: numbered, `- [n] <source id> — <date>`, nothing more; each
inspected file its own entry. Use supplied `source` IDs; `git:` origins and
paths are not IDs. Check inherited clauses, quantities and dates against
exact originals; cite each joined clause's own message.

**Two stages, one page**

Mapping writes observed metadata only; other sections stay
`Unknown — not investigated yet` until investigation fills them from evidence.
User-only coding transcripts show intent, not implementation or passing tests:
verify those from the repository or a reported run. On an older page, reorder
to this shape, keeping supported content. Never reuse the architecture
diagram as the overview. Leave the `Investigation:` line unchanged. Keep the
mapped `Sessions`, `First seen` and `Last seen` fields in `Paths` exactly.
