---
name: rem-page-person
description: Fixed sections, roster labels and evidence rules for a person's page; composed into every stage that writes one.
---

# A person's page

Why these rules: docs/rem-skills/rem-page-person.md

Read supplied page/material. Write, check, fix once, stop; use this format.

This is a growing relationship memory; never shrink it to a summary. Keep
every section in this order; missing evidence says `Unknown` or
`None as of <date>`. Every factual sentence cites `[n]` into `Sources`.
Placeholders are not evidence.

```markdown
# <observed name>

<lead>. Last contact: <date> (latest in supplied sources).

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

- **Lead**: 2–3 cited sentences. Start with a supported current obligation or
  relationship finding; end with `Last contact: <date> (latest in supplied sources)`.
  `Nothing open as of <date>` needs closure evidence.
- **`Facts` first.** Keep every exact label; missing values are `Unknown`.
  Separate multiple values with `; ` and cite each as `value (qualifier) [n]`.
  Dates use `YYYY-MM-DD`; convert source instants in notebook time zone, but
  preserve stated event dates. Cite all except mapped `Email`, `Handles`,
  `Also known as`. Put contact details in their fields. `Links` are sites;
  `How we know them` is the introduction or first thread. Write `Last contact`
  as `<date> (latest in supplied sources) [n]`. `Email` uses the envelope sender; a
  different signature address needs an explicit cross-reference to be an alias.
- **`Insight`**: 2–4 cited bullets, at most 30 words each, starting `Now:`,
  `Changed:`, `At stake:` or `Pattern:`. Name a useful current relationship,
  change, risk or repeated pattern; skip generic praise. Thin evidence: `- Unknown`.
- **`Language` is observed**: the language they write to the user in.
- Attribute group replies to their sender using exact From/To/Cc metadata.
  Greetings do not bind names by recipient order; the owner's phone is not
  the contact's. Date historical plans and handoffs; missing completion
  evidence does not make them current pending work.
- **`Company` needs stated employment.** Student or mailbox affiliation proves
  none: `Unknown`. Link schools/groups in relationship text, not as employers.
- **`Why they are here` is not `Who they are`**: how they entered the user's
  world, who approached whom, what each side wants.
- **`Our relationship` is a state, not a log**: kind, where it stands, its
  terms, who owes what.
  Keep each local link with its relationship, citations and privacy markers;
  separate different events onto separate lines.
- **`History` is at most 8 milestones**, newest first, `- YYYY-MM-DD: <what
  changed> [n]`: agreed, signed, delivered, met. Not a send or a newsletter.
  Past 8, fold the oldest into one line per year.
- **Open threads keep exact asks.** Check later replies and separate terms.
  Reports, optional offers, prerequisites and missing historical outcomes do
  not create debts. Acceptance proves intent, not attendance or activation.
  Name debtor, request date and explicit due date; preserve permission to
  proceed without a reply. Closure needs evidence; otherwise say what outcome
  is unknown. Never hardcode a request's age.
- **Say things once.** Doubt goes in `Uncertainties`; omit collection counts
  and prior-page metadata.
- **Label inference.** Empty sections stay `Unknown`; don't infer "no prior
  history" or "cannot be assessed".
- **Keep what the map already knew.** `Email`, `Handles`, `Also known as`
  arrive filled; keep them. Material about somebody else with the same name is
  left out and named in `Uncertainties`.
- **`Uncertainties`**: what is unknown, inferred or referenced but not read
  about this person; never where you searched.
- **Sources**: `- [n] <source id> — <date>`; claims stay in sentences.
  Reuse numbers and list only cited sources.

## Exact headings

Never annotate headings or rename `Facts` labels. Preserve the runner's
`Investigation:` line unchanged.
