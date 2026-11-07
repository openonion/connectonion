---
name: rem-page-project
description: 'A project page a new teammate understands in one screen: what it is, why, where it stands, what is next.'
---

# A project's page

Write for a teammate with one minute: purpose in the user's words, dated current
state, next action, then reference. State known facts; open parts go in Open
threads, not hedges about missing evidence. Read/write/check/fix once, stop.
Search the repo for evidence, not a format. Keep core headings Facts, Insight,
What it is, Where it stands, Open threads, Paths, Uncertainties, Sources; other
headings appear only with evidence (omit all-Unknown optional sections). Order:

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

**Facts:** exact labels, all present, no others: Repository, Stack, Status, People,
Organisation, Started, Last activity. Missing = Unknown. Multiple values use
`; `, each `value (qualifier) [n]`; dates YYYY-MM-DD, every value cited.
- Repository = Remote origin from cited checkout state.
- Status = earned dated state (active/commits weekly, quiet since date, exploring),
  never licence/language/README topic; not Unknown with dated commits/messages.
- Last activity = latest current-line commit or project-specific message, date
  and what changed with short sha when applicable.
- Started = history packet First commit/date or user's stated beginning, never
  merely earliest observed session.
- People = the user with cited session, plus named contributors. One message or
  commit does not make someone an owner; Unknown only with no supported person.

**Insight:** 2–4 cited bullets, at most 30 words each, prefixes Now:, Changed:,
At stake:, Pattern:, Inference:. Compare user intent to repo evidence: conflicting
requirements, reversals, repeated rework or effort distribution. A finding that
changes the next decision, not advice, hedges or missing evidence. A quote/branch/date/README topic
alone is not an insight. Each is about the project. Implementation belongs in
What it is. None: `- Unknown`. Label
inference with evidence/reason; it need not occur verbatim in a source. Put
answered outside-research questions here/lead, remove them from Uncertainties.

**Quote first, paraphrase last.** Why it exists, Key decisions and Open threads
quote the user's exact decisive sentence, dated/cited. More than ten owner
messages with fewer than five quotes means retelling. Owner = the user, never
their name/he/his. Keep quotes exact.

**What it is:** 1–2 sentences on product, audience and function from the whole
project README or user description, never just the loudest recent thread.
**Why it exists:** problem/outcome, opened with dated exact words that began or
best explain it; newest request is not purpose. Otherwise quote README purpose
at its revision.
**Where it stands:** development first; marketing/outreach one bullet after it.
3–5 dated bullets newest first within each: finished work/milestones from current
line commits (short sha) and build/release messages; recent unmerged branches
with names/dates; phase/goal; latest reported run/test/deploy. Say when quiet.
Past decisions belong in Key decisions.
**Open threads:** only current pending asks, newest first:
`- YYYY-MM-DD — <who> asked: “<exact words>” [n] — open|blocked on <what>`.
Check later messages, commits and branches for outcomes; closed items move to
Where it stands/Key decisions with closing evidence. Over 30 days with no
outcome is history, omit here. Nothing open = bare Unknown.
**Latest issues:** dated symptom/status/evidence newest first; check for fixes.
A report is no diagnosis and a proposed fix is no resolution.
**Key decisions:** actual choices (price/scope/audience/architecture/drop), newest
first, at most sixteen; each reversal its own quoted line:
`- YYYY-MM-DD — <choice, under 12 words>: “<user's words>” [n]`.
Requests/current behavior alone are not choices; label proposals.
**Overview/Try it:** only from current-line docs/code. Overview = 3–7 narrow ASCII
steps in a text fence, from user start to outcome; every arrow needs a cited
source. Try it = entry point, tiny example and visible result, at most three
steps in source order. Never reuse architecture as overview.
**People and ownership:** contacts by area, named partners/clients/collaborators,
linked person pages; avoid inferring ownership from one contribution.
**Getting started:** role-specific commands/outputs only when verified.
**How it is built/Architecture map:** short components/data flow at cited revision;
label proposed versus built, no file tour.
**Paths:** mapped project folders and their purposes, including external data/design
locations; modules belong in How it is built. Never guess. Preserve mapped Paths,
Sessions, First seen, Last seen exactly; new paths need retained evidence.
**Uncertainties:** at most five questions that change the next step, ending ?
before citations. **Sources:** only `- [n] <source id> — <date>`. Each inspected
file has its own supplied ID; origins/bare paths are not IDs. Check inherited
claims/quantities/dates against originals; cite each joined clause's own source.

Mapping writes observed metadata only; other sections stay Unknown — not
investigated yet. Coding prompts prove intent, not implementation/passing tests:
verify repo or reported runs. Reorder older pages without dropping supported
content. Keep Investigation unchanged.
