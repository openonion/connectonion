---
name: rem-page-person
description: What a person's page in the notebook is made of — the fixed sections, the labels the roster reads back, and the rules a thin page always breaks. Composed into every stage that writes one, so there is one definition rather than a copy per stage.
---

# A person's page

Why these rules: docs/rem-skills/rem-page-person.md

**How to do it.** Read the existing page and all supplied material. Write the
whole page, check it once against the rules below, fix errors in one edit, and
stop. Do not copy a format from other pages, outputs, logs, skills or the repo.

The page is the memory of a relationship and grows with every interaction;
never shrink it back to a summary. **Every section is always present, in this
order**; one the evidence does not support says `Unknown`, or
`None as of <date>`. **Every factual sentence carries a claim number** `[n]`
into `Sources`; a sentence you cannot number is not kept. Placeholders are
never evidence.

```markdown
# <observed name>

<lead>. Last contact: <date>.

## Facts
- Email: Unknown
- Phone: Unknown
- Company: Unknown
- Role: Unknown
- Location: Unknown
- Time zone: Unknown
- Links: Unknown
- How we know them: Unknown
- First contact: Unknown
- Last contact: Unknown
- Signing entity: Unknown
- Handles: Unknown
- Language: Unknown
- Also known as: Unknown

## Insight
## Who they are
## Why they are here
## Our relationship
## History
## Open threads
## How they communicate
## How the user writes to them
## Cadence
## Uncertainties
## Sources
```

Rules:

- **The lead comes first**, 2–3 cited sentences: balance (who owes what since
  when), then their relationship and `Last contact: <date>` with its channel.
  `Nothing open as of <date>` needs supported closure; otherwise write
  `Open status: Unknown` and name the missing discussion or outcome.
- **`Facts` is data, written first.** One line a field, labels exact, every
  one present; a missing value is exactly `Unknown`. Several values: `; `
  between, each `value (qualifier) [n]` (`+61 2 5550 0142 (work) [3];
  +61 400 555 019 (mobile) [5]`). Dates `YYYY-MM-DD`. Every value is cited
  except `Email`, `Handles`, `Also known as`. A contact detail never goes in a
  sentence instead of its field. `Links`: LinkedIn, personal or company site.
  `How we know them`: who introduced whom, or the first thread.
- **`Insight` is 2–4 cited bullets of at most 30 words, each starting `Now:`, `Changed:`,
  `At stake:` or `Pattern:`** — what the inbox does not say outright: what they
  are to the user's work now; what moved recently; what is at risk or owed;
  a pattern over time (reply speed, topics, who chases whom). Never generic
  ("key stakeholder", "valuable relationship", "maintains regular
  communication"); thin material: `- Unknown`.
- **`Language` is observed**: the language they write to the user in.
- **`Company` comes from the address domain and the signature block.** A
  mailbox provider (gmail, outlook, qq) is not a company. Where an organisation
  page exists, link it: `- Company: [UNSW](../orgs/unsw.md) [2]`.
- **`Why they are here` is not `Who they are`**: how they entered the user's
  world, who approached whom, what each side wants.
- **`Our relationship` is a state, not a log**: kind, where it stands, its
  terms, who owes what.
- **`History` is at most 8 milestones**, newest first, `- YYYY-MM-DD: <what
  changed> [n]`: agreed, signed, delivered, met. Not a send or a newsletter.
  Past 8, fold the oldest into one line per year.
- **An open thread names who owes whom what, and since when.** Supported closure:
  `Nothing open as of <date>` and next expected contact; missing evidence:
  `Unknown — <missing discussion or outcome>`.
- **Say a thing once, in one clause.** Doubt goes once in `Uncertainties`,
  never as a tail on every bullet ("no result was reported"). How the page was
  made — the mapper, the collector, how many mails matched, the prior page —
  goes nowhere in the body.
- **Mark inference as inference.** Never write "no prior history" or "cannot be
  assessed"; a section with nothing stays `Unknown`.
- **Keep what the map already knew.** `Email`, `Handles`, `Also known as`
  arrive filled; keep them. Material about somebody else with the same name is
  left out and named in `Uncertainties`.
- **`Uncertainties`**: what is unknown, inferred or referenced but not read
  about this person; never where you searched.
- **Numbered sources**: `- [n] <source id> — <date>`, nothing more; the claim
  is in the sentence. Reuse a number for a repeated source; list only what a
  sentence cites.

## The headings are copied exactly

Nothing else goes on a heading line; never rename or annotate a `Facts` label.
The `Investigation:` line at the foot of the page is the runner's: leave it
exactly as you found it.
