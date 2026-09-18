---
name: wiki-page-org
description: What an organisation's page in the notebook is made of — the fixed sections, when a company earns a page at all instead of staying a field on a person's, and the rules that keep it from becoming a second copy of everyone who works there. Composed into every stage that writes one.
---

# An organisation's page

A company is not a person with different headings. The difference is what the
facts belong to: a programme, an agreement, a fee schedule, a legal entity and
a decision about who the user will deal with there all belong to the
organisation and outlive whichever person happened to send the mail.

## When an organisation earns a page

Most do not. Measured over 180 real days of one mailbox: 182 correspondents,
168 of them writing from a work domain, but **111 of those domains held
exactly one person**. A page for each would be the one-line person page
repeated at company scale — the notebook doubles in size and says nothing new.

Create one when **either** is true:

- **Two or more people write from the same work domain.** That is the moment
  the institutional facts start being copied: one real domain held 24
  correspondents, and without a page the programme, the agreement and who
  handles contracts would sit on 24 pages and drift 24 ways.
- **Something is agreed with the entity rather than the person** — a signed
  contract, recurring money, a programme or account that will outlive this
  contact. A one-person client who signed a contract earns a page; a one-person
  vendor who sent a quote does not.

Otherwise the company stays a `Company:` field on the person's page. A mailbox
provider is never an organisation: `gmail.com` is where someone keeps their
mail, not who they answer to.

`co wiki scan orgs --days 180` lists the domains that pass the first test, with
how many people and how much mail each holds. It proposes; you judge.

Two things to judge, because the count alone will mislead you:

- **A notice sender is not a relationship.** Only correspondents — people who
  write to the user and are written back to — are counted toward the
  threshold; each row also carries `notices`, the one-way automated senders on
  that domain. A domain whose `people` are few and whose `notices` are many is
  a service, not a counterparty, and belongs on the page of whatever it serves.
- **One domain can be two tenants.** A university's staff and its students, an
  agency's shared address: that is two pages or one, and the mail says which.
  Say which you chose in `Uncertainties`.

## The shape

**Every section is always present, in this order**, and a section the evidence
does not support says `Unknown` rather than disappearing — the same rule as a
person's page, for the same reason: an empty slot is the next thing to find
out. **Every factual sentence carries a claim number** `[n]` into `Sources`.

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

- **`People here` is links, never copies.** The whole reason the page exists is
  that a fact about the organisation should be written once. If a sentence is
  true of the person and not of the employer, it belongs on their page.
  A person named in the mail who has no page yet is a line here without a
  link — that is a finding, not a failure.
- **The person's `Company:` field links here once this page exists**, and the
  institutional detail moves off their page. Their page keeps what is theirs:
  their role in it, how they write, what they owe the user.
- **`Our relationship` is the relationship with the entity**, which is often
  not the sum of the individual ones. The user mentors for UNSW; that is not
  Vern's relationship or Karen's, it is the university's.
- **`Terms` is where numbers live** — rates, dates, notice periods, what was
  signed and when. A term that changed keeps both values and the date it
  changed.
- **Two parts of one organisation that never touch may be two pages.** Say so
  in `Uncertainties` rather than flattening them, and split only when the mail
  shows they are really separate relationships.
- **A company's own marketing is not knowledge about it.** What the notebook
  keeps is what the user learned by dealing with them.
