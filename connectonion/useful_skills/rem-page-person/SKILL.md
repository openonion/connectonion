---
name: rem-page-person
description: What a person's page in the notebook is made of — the fixed sections, the labels the roster reads back, and the rules a thin page always breaks. Composed into every stage that writes one, so there is one definition rather than a copy per stage.
---

# A person's page

Why these rules: docs/rem-skills/rem-page-person.md

**How to do it.** Your whole input is the page as it stands and the material
about this person: read both in full, then write the page. Do not look for
example pages, earlier outputs, logs, other skills or the repository to copy a
format from; the shape is below. Look beyond the material only for a gap you can
name (a phone number, an employer), and record what you checked in
`Uncertainties`. Write the whole page in one go, check it once against the
rules, fix what is wrong in one edit, and stop.

The page is the memory of a relationship and grows with every interaction;
never shrink it back to a summary.

**Every section below is always present, in this order.** A section the
evidence does not support says `Unknown`, or `None as of <date>`; never drop it.
**Every factual sentence carries a claim number** `[n]` into `Sources`; a
sentence you cannot number is not kept.

The following is structure only. Placeholders are never evidence. Use only supplied or actually inspected sources.

```markdown
# <observed name>

## Contact
- Email: Unknown
- Phone: Unknown
- Company: Unknown
- Role: Unknown
- Signing entity: Unknown
- Handles: Unknown
- Language: Unknown
- Also known as: Unknown

## Who they are
- Unknown — not investigated yet

## Why they are here
- Unknown — not investigated yet

## Our relationship
- Unknown — not investigated yet

## History
- Unknown — not investigated yet

## Open threads
- Unknown — not investigated yet

## How they communicate
- Unknown — not investigated yet

## How the user writes to them
- Unknown — not investigated yet

## Cadence
- Unknown — not investigated yet

## Uncertainties
- Unknown — not investigated yet

## Sources
- Unknown — not investigated yet
```

Rules:

- **`Contact` is fields, not prose.** Never put a contact detail in a sentence
  or the summary instead of its field; a missing one stays `Unknown`.
- **`Language` is observed**: the language the person writes to the user in,
  from their own messages (`English`, `Mandarin; English for contracts`). Do not
  wait for them to declare it. `Unknown` only when nothing they wrote is in the
  material.
- **`Company` comes from the address domain and the signature block**
  (`@unsw.edu.au` is UNSW; the signature gives department, office, direct line).
  A mailbox provider (gmail, outlook, qq) is not a company: `Unknown`. Where an
  organisation page exists, link it — `- Company: [UNSW](../orgs/unsw.md)` — and
  keep institutional facts there. This page keeps what is theirs: their role,
  how they write, what they owe the user.
- **`Why they are here` is not `Who they are`.** Identity is what they do; this
  is how they entered the user's world: who approached whom, and what each side
  wants.
- **`Our relationship` is a state, not a log**: what kind of relationship, where
  it stands today, its concrete shape (numbers, terms, who owes what), and how
  the person plays it. The dated log goes in `History`.
- **An open thread names who owes whom what, and since when** ("the user has
  owed a reply for twelve days"). "Status is not recorded" is a gap, not a
  thread. If nothing is open: `Nothing open as of <date>`, plus the next
  expected contact.
- **Mark inference as inference.**
- **A section the material says nothing about stays `Unknown`.** Never write
  "no prior history", "relationship not yet established" or "cannot be
  assessed". Say once, in `Uncertainties`, what the material was (one calendar
  invitation, one receipt).
- **Keep what the map already knew.** `Email`, `Handles` and `Also known as`
  arrive filled from the mapped addresses; keep them. Material about somebody
  else (same first name) is left out and named in `Uncertainties`; it never
  empties this person's fields.
- **`Uncertainties`** lists what is unknown, inferred but unconfirmed, or
  referenced but not read.
- **Numbered claims.** Each entry: the claim, confidence (high / medium / low),
  date observed, source id. Reuse a number for a repeated claim; never list one
  claim under two numbers. List only claims a sentence cites.
- A person with one message and no identity gets no page. A person with a
  second message gets their page extended, not rewritten.


## The headings are copied exactly

Nothing else goes on a heading line. The labels under `Contact` are read back
exactly: `Email:`, `Phone:`, `Company:`, `Role:`, `Signing entity:`, `Handles:`,
`Language:`, `Also known as:`. Never rename or annotate one.

The `Investigation:` line at the foot of the page is not yours: the runner
writes it (`investigated 2026-09-14 (outlook, gmail, codex)`) and reads it to
pick the next subject. Leave it exactly as you found it.
