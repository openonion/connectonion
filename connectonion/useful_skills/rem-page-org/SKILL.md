---
name: rem-page-org
description: What an organisation's page in the notebook is made of — the fixed sections, when a company earns a page at all instead of staying a field on a person's, and the rules that keep it from becoming a second copy of everyone who works there. Composed into every stage that writes one.
---

# An organisation's page

Facts of the entity (programme, agreement, fees, legal entity, who the user
deals with) go here, not on the sender's page.

## When an organisation earns a page

Create one only when **either** is true:

- **Two or more people write from the same work domain.**
- **Something is agreed with the entity rather than the person**: a signed
  contract, recurring money, a programme or account that outlives this contact.
  A one-person client who signed earns a page; a one-person vendor who sent a
  quote does not.

Otherwise the company stays a `Company:` field on the person's page. A mailbox
provider (`gmail.com`) is never an organisation.

`co rem scan orgs --days 180` proposes domains passing the first test; you
judge. Its `two_way` (people who wrote to the user and were answered)
separates a counterparty from a vendor; read it against the names.

- **Brand names that only ever send are a vendor**, whatever the headcount
  (`Apple Developer`, `Xero Support`); so are event platforms and newsletters.
  Their mail goes on the page of what it is about (the project using it).
- **`two_way` of zero does not settle it**: a reply from the user's other
  mailbox leaves it at zero. Human names and subjects about the user's own work
  outweigh it; a brand name does not.
- **The user's own domain is not a counterparty.** Pass every own address to the
  scan with `--mine`.
- **One domain can be two tenants** (staff and students, a shared agency
  address). Choose one page or two from the mail and say which in
  `Uncertainties`.

## The shape

**Every section is always present, in this order**; a section the evidence does
not support says `Unknown`. **Every factual sentence carries a claim number**
`[n]` into `Sources`.

```markdown
# ExampleCo

## Domains
- example.test [1]

## Facts
- What they do: Unknown
- Website: Unknown
- Location: Unknown
- Legal entity: Unknown
- Your contacts: [Alex](../people/alex.md) [1]
- First contact: 2026-07-10 [1]
- Last contact: 2026-07-24 [2]

## Who they are
The named programme contact writes from example.test; legal identity is unknown. [1]

## Our relationship
The user requested one team; the programme has a two-team minimum. An exception
is not confirmed in the reviewed replies. [1][2]

## People here
- [Alex](../people/alex.md) — programme contact [1]

## Terms
- Two-team minimum; the one-team request is not accepted terms. [1][2]

## Open threads
Unknown — historical requests alone do not establish a current obligation. [2]

## Uncertainties
- Whether the exception was later accepted. [2]

## Sources
- [1] outlook:123456789abc — observed 2026-07-10
- [2] outlook:abcdef123456 — observed 2026-07-24
```

## Rules

- **The heading is the organisation's name.** A page mapped under its domain
  (`# rmit.edu.au`) is renamed to the name the material uses
  (`# RMIT University`); the domain stays under `Domains`.
- **One voice**: the owner is `the user`, never their name, `you` or `we`.
- **`Facts` is data**: those seven labels, one line each, every one present,
  a missing value exactly `Unknown`, every value cited, dates `YYYY-MM-DD`.
- **`People here` is links, never copies.** A sentence true of the person and
  not the employer belongs on their page. A named person with no page yet is an
  unlinked line.
- **Once this page exists, the person's `Company:` field links here** and the
  institutional detail moves off their page; it keeps their role, how they
  write, what they owe the user.
- **`Our relationship` is with the entity**, not the sum of individual ones.
- **`Terms` holds the numbers**: rates, dates, notice periods, what was signed
  and when. A changed term keeps both values and the date it changed.
- **Two parts of one organisation that never touch may be two pages.** Say so in
  `Uncertainties`; split only when the mail shows separate relationships.
- **A company's own marketing is not knowledge about it.** Keep what the user
  learned by dealing with them.
- **Lead with the entity-level finding** in `Our relationship`: accepted terms,
  a capacity constraint or an explicit condition, with sources. Keep programmes,
  offers and teams distinct; one team's reply does not close another's request.
- **Templates are not executed terms.** Compare the actual mail and documents:
  default ownership and an optional assignment can coexist. Keep version,
  conditions and execution unknown when unsupported; do not invent a conflict.
- **Record sourced current requests or agreed obligations.** Prerequisites,
  conditional offers and missing historical outcomes alone create no owed debt.
  Use `Nothing open as of YYYY-MM-DD [n].` for a supported closure; otherwise
  use `Unknown` with the evidence gap, rather than a task to settle history.
- **Dates use the notebook calendar.** A bulk notice or calendar acceptance does
  not establish first direct contact, employment, attendance or completion.
- **Notebook pages are context, not primary evidence.** Cite original headers
  for domains and named contacts; do not cite `investigation:page` as proof.
