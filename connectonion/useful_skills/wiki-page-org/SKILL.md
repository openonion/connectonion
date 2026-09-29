---
name: wiki-page-org
description: What an organisation's page in the notebook is made of — the fixed sections, when a company earns a page at all instead of staying a field on a person's, and the rules that keep it from becoming a second copy of everyone who works there. Composed into every stage that writes one.
---

# An organisation's page

Why these rules: docs/wiki-skills/wiki-page-org.md

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

`co wiki scan orgs --days 180` lists domains passing the first test, with
`people`, `two_way`, `notices` and `mails` per row. It proposes; you judge.
`two_way` (people there who both wrote to the user and were written back to)
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
# UNSW

## Domains
- unsw.edu.au [1]
- student.unsw.edu.au — the student body, not staff [4]
- Legal entity: The University of New South Wales, ABN 57 195 873 179 [7]

## Who they are
Public research university in Sydney. The user deals with two parts of it that
do not otherwise touch: UNSW Founders (the startup arm, Unit of
Entrepreneurship) and the Office of Global Affairs. [1][3]

## Our relationship
Startup partner to the Practice of WorkXStartup programme since July 2026 —
the user mentors a student team, UNSW handles administration and academic
support. Not a paid engagement; the return is access to the founder network
and to students. [2][3]

**Where it stands:** one team of 4–6 students agreed after the user pushed
back on two or three; sessions requested 3–5 pm; WIL agreement still with
Helena. [5][6]

## People here
- [Vern Chan](../people/vern-chan.md) — Global Program Manager; the way in,
  and who reroutes to whoever owns the next step [2]
- [Karen da Lapa-Soares](../people/karen-da-lapa-soares.md) — Senior
  Partnerships Officer; owns the programme's terms [5]
- Helena Asher — contract; no page yet [5]

## Terms
- Summer 2027 cohort: 11 Jan – 5 Feb 2027, six touchpoints, CBD campus [2]
- WIL agreement requested by 17 July 2026; IP/confidentiality arrangements
  were named as a next step and their outcome is not recorded here [2]

## Open threads
- **WIL agreement** — with Helena since 2026-07-21; the user has not signed [5]
- **3–5 pm slot** — asked of Natalie 2026-07-21, unanswered in this material [5]

## Uncertainties
- Whether the one-team exception was formally accepted, or only discussed.
- `student.unsw.edu.au` correspondents are course contacts and may belong to a
  different relationship entirely; not investigated.

## Sources
- [1] Domain of every staff address seen — high — observed 2026-07-10 —
  outlook:d337e0e0d09c
- [2] Programme dates, campus, WIL deadline — high — observed 2026-07-10 —
  outlook:ec65e5ff6168
```

## Rules

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
