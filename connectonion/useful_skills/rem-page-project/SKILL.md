---
name: rem-page-project
description: A project page a new teammate understands in one screen: what it is, why, where it stands, what is next.
---

# A project's page

Write for a teammate who has one minute. Say what is, dated; never what the
evidence lacks ("no test result is reported", "unverified"): a gap that
changes the next step is one question under `Uncertainties`. The first screen answers, dated and
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
`Started`, `Last activity`, and no other label. Several values `; ` between, each
`value (qualifier) [n]`; dates `YYYY-MM-DD`; every value cited.
- `Status`: a phrase the evidence earns: `active — commits weekly on
  origin/main`, `quiet since 2026-08-10`, `exploring, nothing chosen`;
  never a licence, language or README topic, and never `Unknown` while
  commits or messages are dated.
- `Last activity`: the newer of the latest commit on the current line and
  the latest message that names this project, with what it was:
  `2026-10-15 — Gemini 4 Argon made selectable (commit e25df6e) [n]`.
- `Started`: the history packet's `First commit` line (`2026-10-14 — first
  commit ee2ca3d [n]`) or the owner's words that began it; the first observed
  session is not a start.
- `People`: `the user (sessions in these folders)`, cited to one of the
  user's messages (never `investigation:page`), and anyone the messages or
  commits name working on it; `Unknown` only with neither.

**Insight**: 2–4 cited bullets of at most 30 words, starting `Now:`,
`Changed:`, `At stake:` or `Pattern:`: what changes a teammate's next
decision. Compare the owner's words with the repository first: a requirement
the code contradicts or has not caught up with (the owner says 8% of net, the
PDF says gross), a reversed choice, a requirement that moved, what keeps
being reworked (README rewritten six times in two days), where the effort
went (80 of 111 messages on the launch video). What the code
does belongs in `What it is`; a branch, commit date, README topic or a quote
alone is not an insight. Each is about the project, not one message's
wording; a finding, never advice (`should`, `verify`) and never a hedge about
what the evidence lacks (`unverified`, `not established`). None: `- Unknown`.

**Quote first, paraphrase last.** `Why it exists`, each `Key decisions` line
and each `Open threads` ask quote the owner's words: the one sentence that
carries the choice, not the whole message. With more than ten owner
messages, fewer than five quotes means you retold. The owner is `the user`,
never their name, `he` or `his`.

**What it is**: one or two sentences: the product, who it serves, what it
does, from the README or the owner's description of the whole project, never
the loudest recent thread.

**Why it exists**: the problem and intended outcome, opened with the owner's
words that started it or best state its purpose:
`YYYY-MM-DD — “<exact words>” [n]`. The newest request is not why a project
exists; without such words, quote the README's purpose, dated by its revision.

**Where it stands**: development first: what was built, fixed, tested or
released, from commits and the owner's build and release messages; launch,
marketing and outreach work is one bullet after it. 3–5 bullets, newest first
within each, each dated: the
latest finished work and milestones (releases, features shipped: commit
subjects on the current line with short sha, the owner's
latest messages; quiet for weeks — say so); work in flight (recent unmerged
branches, by name and date); the phase and goal; the latest run, test or
deploy result someone reported. History goes in `Key decisions`.

**Open threads**: only what is pending now, newest first:
`- YYYY-MM-DD — <who> asked: “<exact words>” [n] — open|blocked on <what>`.
Before listing an ask, look for its outcome in later messages, commit
subjects and branch names. One closed by a commit or a later message moves to
`Where it stands` or `Key decisions` with that evidence. An ask more than 30
days old with no outcome found is history, not an open thread: leave it out.
Nothing open: bare `Unknown`, never a line about what the material does not show.

**Latest issues**: bugs, regressions, blockers, newest first: date, symptom,
status with its evidence. Check the history for a fix before calling one
open. A report is not a diagnosis; a proposed fix is not a resolution.

**Key decisions**: the choices the owner made, newest first by date (check
the order before you finish), at most sixteen:
price, scope, audience, positioning, architecture, what to drop.
`- YYYY-MM-DD — <choice, under 12 words>: “<the owner's exact words>” [n]`.
A reversal is its own line quoting the reversal. A request alone or current
behaviour alone is not a decision; label proposals.

**Overview** and **Try it**, when the README, docs or code at the current line
show them: `Overview` is 3–7 narrow ASCII steps in a `text` fence (user start,
actions, outcome); `Try it` is an entry point, a tiny example and the visible
result, at most three steps, in the source's order. Every arrow is a step a
cited source states; a plausible diagram is not evidence.

**People and ownership**: who to ask, by area, and the partners, clients or
collaborators the messages name on this project, linking person pages. One
commit or message never makes someone an owner.

**Getting started**: per role, commands and outputs only when verified.

**How it is built** and **Architecture map**: main components and data flow
from files at the current line, citing the revision; label proposed apart
from built. Short: a page is not a code tour.

**Paths**: the project's own folders (repository, data or design locations
outside it) with their purpose; modules belong in `How it is built`. Never guess.

**Uncertainties**: at most five questions, each ending `?` before its
citations, each one that would change the next step.

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
