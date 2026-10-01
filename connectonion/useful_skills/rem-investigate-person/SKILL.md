---
name: rem-investigate-person
description: The steps for investigating a person's page, composed after rem-investigate when the subject is under people/.
---

# Investigating a person

Why these rules: docs/rem-skills/rem-investigate.md

## Identity is given, not guessed

- The user's addresses (the mailbox names in coverage) are never the subject's;
  `Email`/`Handles` take only addresses the subject writes from.
- Every handle you were given, wrong spellings too, goes in `Also known as:`;
  add the ones you discover (signature, second address, other script). Company
  names go in their own field.
- A page titled by a handle gets the person's name once known (`# vern.chan` →
  `# Vern Chan`, handle kept in aliases).
- The subject is the owner of a coverage mailbox → the user's own page: follow
  `rem-owner-page`.
- **A role in a list the user writes about someone else is that person's, not
  the user's.** A role is the subject's only when the subject states it or
  someone states it about them.
- Another page for the same person: name it in `Uncertainties`; do not merge.

## Reading the mail

- **The `investigation:facts` item first**: addresses, phones, links and
  contact dates our code read, each with its source id; every one goes in its
  `Facts` field, cited to that id. Its `Signature` and `Calendar` lines give
  role, company, office, location and time zone. Then each signature block
  you read, field by field. A changed signature is a dated move or promotion.
  Two phones are two values with their qualifiers.
- **Address domain = employer** (`@unsw.edu.au` → UNSW), never a role;
  gmail/outlook/qq/163 → `Company: Unknown`. An org page for the domain (listed
  in the `investigation:org-pages` item) → `Company:` is that link,
  `[Name](../orgs/<file>.md)`, cited to the mail that shows it.
- `[attachment]` entries are the file's text; the terms are there; cite their id.
  An unreadable attachment → your final reply.
- Mail gives identity and commitments; sessions give intent. Sources disagree →
  say so; stated in one and implied in another → cite both.

## What to produce

Follow `rem-page-person` exactly, the lead above `Facts` included:
`co rem list people --aliases` reads its headings and `Contact` labels. **`Open threads` is mandatory**: who owes what,
since when.

**Insight, three shapes** (never copy these facts):
- `At stake: the user has owed Mia the revised SOW for 12 days; her signing date is 3 October [5]`
- `Changed: replies went from same-day to none since 2026-08-20, after the price went to A$15k [6][8]`
- `Pattern: every thread since June is invoices; she chases, the user answers in 2–4 days [2][7]`
