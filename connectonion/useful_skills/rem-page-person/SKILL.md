---
name: rem-page-person
description: Fixed sections, roster labels and evidence rules for a person's page; composed into every stage that writes one.
---

# A person's page

Why these rules: docs/rem-skills/rem-page-person.md

Read supplied material; write a growing memory in this order. Unsupported
values are `Unknown`; each factual sentence cites `[n]` in `Sources`.

```markdown
# <observed name>

<lead>. Last contact: <date> via <channel> in checked sources.

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

- **Lead**: 2–3 short cited sentences. Put the current event and any user action
  before role detail; end with last contact, channel and checked-source scope.
  Historical gaps go in `Uncertainties`; `Nothing open` needs closure evidence.
- **`Facts` first.** Keep exact labels, one per line; separate qualified
  values with `; `. Use notebook-timezone `YYYY-MM-DD`; keep event dates
  distinct. Cite values except `Email`, `Handles`, `Also known as`. Contact
  details go here. `Links` are cited sites, not email domains.
  `How we know them`: introduction or first thread.
- In Facts write `Last contact: YYYY-MM-DD (latest observed in checked sources)
  [n]`; the lead also states its checked scope. Other channels may be unknown.
- **`Insight`**: 2–4 cited bullets, at most 30 words each, starting `Now:`,
  `Changed:`, `At stake:` or `Pattern:`. State a useful consequence supported
  by its exact citations, not a generic role or repeated Fact. Use `At stake:`
  only for an evidenced unresolved ask, promised deliverable, deadline or
  consequence. A signed plan, quantity and proposed start prove none of these;
  do not invent launch, fulfillment, delivery work or an owner. Thin material:
  `- Unknown`.
- **`Language` is observed**: the language they write to the user in.
- Attribute group replies to their sender using exact From/To/Cc metadata.
  Greetings do not bind names by recipient order; the owner's phone is not
  the contact's. Date historical plans and handoffs; missing completion
  evidence does not make them current pending work.
- **`Company` needs stated employment.** Student or mailbox affiliation proves
  none: `Unknown`. Link schools/groups in relationship text, not as employers.
- An employee's “we signed” does not name the legal signer; keep `Signing entity`
  Unknown unless the source names it.
- **`Why they are here`**: how they met, who approached whom, each side's aim.
- **`Our relationship`**: kind, current state, terms and obligations.
  “We signed” alone makes this contact about a plan, not a contract with the user.
  Keep each local link with its relationship, citations and privacy markers;
  separate different events onto separate lines.
- **`History`**: at most 8 dated, cited milestones, newest first: agreements,
  signing, delivery or meetings. Fold older years; omit routine sends.
- **Open threads keep exact asks.** Check later replies; separate terms/forms.
  Reports/optional offers create none. Prerequisites aren't agreed commitments;
  missing historical outcomes aren't current debts.
  Accepting an invitation or trial proves intent; attendance/activation need
  separate evidence.
  Name debtor, request date and explicit due date; never hardcode its age.
  Preserve permission to proceed without a reply. Sparse mail proves no global
  no-debt state. `Nothing open` needs evidence closing each known ask; otherwise
  use `Unknown`. Name next contact only if arranged; a planned start is not one.
- Say things once; put doubt in `Uncertainties`; omit collection counts.
- **Label inference.** Empty sections stay `Unknown`; don't infer "no prior
  history" or "cannot be assessed".
- **Keep what the map already knew.** `Email`, `Handles`, `Also known as`
  arrive filled; keep them. Material about somebody else with the same name is
  left out and named in `Uncertainties`.
- **`Uncertainties`**: unknowns, inferences and unread references; omit search logs.
- **Sources**: `- [n] <source id> — <date>`; list only cited sources.

## Exact headings

Keep headings, `Facts` labels and the runner's `Investigation:` line exact.
