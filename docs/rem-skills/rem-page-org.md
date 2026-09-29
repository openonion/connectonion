# Why rem-page-org says what it says

The rules live in `connectonion/useful_skills/rem-page-org/SKILL.md`, composed
into every model turn that writes an organisation's page. This file holds the
reasons and measurements behind them; it is not loaded at runtime (#1851).

## A company is not a person with different headings

The difference is what the facts belong to. A programme, an agreement, a fee
schedule, a legal entity and a decision about who the user will deal with there
all belong to the organisation and outlive whichever person happened to send
the mail.

## When an organisation earns a page

Most do not. Measured over 180 real days of one mailbox: 182 correspondents,
168 of them writing from a work domain, but **111 of those domains held exactly
one person**. A page for each would be the one-line person page repeated at
company scale: the notebook doubles in size and says nothing new.

The two-people test marks the moment institutional facts start being copied.
One real domain held 24 correspondents; without a page, the programme, the
agreement and who handles contracts would sit on 24 pages and drift 24 ways.

A mailbox provider is never an organisation: `gmail.com` is where someone keeps
their mail, not who they answer to.

## Reading `co rem scan orgs`

`two_way` is the column that separates a counterparty from a vendor. Read
against the names, the real list separated cleanly:

```
ppl 2way notice  domain                    who
 26   11      1  unsw.edu.au               Tamara Berryman, Vern Chan, …   → a page
  3    0      0  cubpbc.com                Tara Sassine, Gemma Ingles      → a page: people, named
  2    0      0  corp.town.com             Jean-Denis Greze, Tony Vincent  → a page
 22    0      0  user.luma-mail.com        one sender per event            → no: a platform
  6    0      1  substack.com              FounderCoHo, a16z speedrun      → no: newsletters
  3    0      0  email.apple.com           Apple Developer, Apple Support  → no: a vendor's
  2    0     12  mail.anthropic.com        Anthropic, PBC ×2                  product mail
```

- Brand-name senders (`Apple Developer`, `MongoDB Cloud`, `Xero Support`,
  `Neon Changelog`) are mailboxes, not colleagues.
- `two_way` can be zero for a real client, because a reply sent from the user's
  other mailbox is not counted. That is why human names and subject lines about
  the user's own work outweigh it.
- The user's own company and agent addresses are the owner's profile, not an
  organisation they deal with; `--mine` drops them.
- A university's staff and its students, or an agency's shared address, can be
  two tenants of one domain.

## Every section is always present

The same rule as a person's page, for the same reason: an empty slot is the
next thing to find out.

## `People here` is links, never copies

The whole reason the page exists is that a fact about the organisation should
be written once. A named person with no page yet is a finding, not a failure.

## `Our relationship` is with the entity

It is often not the sum of the individual ones. The user mentors for UNSW; that
is not Vern's relationship or Karen's, it is the university's.
