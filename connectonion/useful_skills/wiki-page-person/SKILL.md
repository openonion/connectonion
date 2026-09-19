---
name: wiki-page-person
description: What a person's page in the notebook is made of — the fixed sections, the labels the roster reads back, and the rules a thin page always breaks. Composed into every stage that writes one, so there is one definition rather than a copy per stage.
---

# A person's page

This is the page the user will open most, and the one most likely to come out
thin. It is the memory of a relationship, and it grows with every interaction;
never shrink it back to a summary.

**Every section below is always present, in this order.** A section the
evidence does not support says `Unknown`, or `None as of <date>` — it is never
dropped. An empty slot is information: it tells the user what to go find out.
A page that omits a section instead hides the gap, and the one-line person
page is exactly what that produces.

**Every factual sentence carries a claim number** `[n]` pointing into the
`Sources` list at the foot. A sentence you cannot number is a sentence you
cannot keep.

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

Rules that make this page work, and that a thin page always breaks:

- **`Contact` is fields, not prose.** A phone number inside a sentence cannot
  be found, and `Unknown` is the only way the user learns that the mailbox
  never carried one. Never write a contact detail into the summary instead.
- **`Company` comes from the address domain and the signature block**, both of
  which are already in the material — `@unsw.edu.au` is UNSW, and the four
  lines under "Thank you," give the department, the office and the direct
  line. A mailbox provider (gmail, outlook, qq) is not a company: that is
  `Unknown`. Where an organisation page exists, `Company` links to it —
  `- Company: [UNSW](../orgs/unsw.md)` — and the institutional facts live
  there, not repeated here. What stays on this page is what is theirs: their
  role inside it, how they write, what they owe the user.
- **`Why they are here` is not `Who they are`.** Identity is what they do;
  this is how they entered the user's world — who approached whom, and what
  each side wants out of it. It is the section most often missing and the one
  the user asks for most.
- **`Our relationship` is a state, not a log.** Say what kind of relationship
  it is, where it stands today, its concrete shape (numbers, terms, who owes
  what), and how the person plays it. The dated log lives in `History` and is
  evidence for this section, not a substitute for it.
- **An open thread names who owes whom what, and since when.** "Discussion
  status is not recorded" is not an open thread — it is a gap dressed up as a
  finding. If the user owes a reply and has owed it for twelve days, say that.
  If nothing is open, say `Nothing open as of <date>` and name the next
  expected contact.
- **Mark inference as inference.** A judgment drawn from how someone writes is
  worth keeping, and worth labelling, so a later pass does not harden it into
  a fact.
- **`Uncertainties` is where a thin page becomes honest** instead of short.
  What is unknown, what is inferred but unconfirmed, what was referenced but
  not read.
- **Numbered claims.** Each entry: the claim, confidence (high / medium /
  low), the date it was observed, and the source id. Reuse a number for a
  claim you already listed; never list the same claim twice under two numbers.
  Only list claims a sentence actually cites.
- A person with one message and no identity does not get a page at all. A
  person with a second message gets their page extended, not rewritten.


## The headings are copied exactly

Nothing else goes on a heading line. A stage handed this shape with notes
beside the headings wrote `## Our relationship          state and shape, not a
log` into a real page, and `co wiki people` then found no `Our relationship` at
all. The labels under `Contact` are read back the same way: `Email:`,
`Phone:`, `Company:`, `Role:`, `Signing entity:`, `Handles:`, `Language:`,
`Also known as:`. A renamed label is an invisible one, and the next batch meets
the person as a stranger.

The `Investigation:` line at the foot of the page is not yours. The runner
writes it after every pass — `investigated 2026-09-14 (outlook, gmail, codex)`
— and reads it to pick the next subject. Leave it exactly as you found it; a
pass that rewrote it in its own words (2026-09-14) got a second, machine
stamp appended and the line then said two different things.
