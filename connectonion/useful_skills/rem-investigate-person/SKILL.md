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
- **A page titled by an address is renamed** once the material names the
  person (signature, or the user's greeting): `# mei.l1990@outlook.com` →
  `# 李梅`, the address kept in `Also known as:`.
- **Not a person** (a service, bot, shared or test inbox, an account the user
  runs): the lead says what it is and `Role:` reads `Not a person: <what>`.
- The subject is the owner of a coverage mailbox → the user's own page: follow
  `rem-owner-page`.
- **A role in a list the user writes about someone else is that person's, not
  the user's.** A role is the subject's only when the subject states it or
  someone states it about them.
- Another page for the same person: name it in `Uncertainties`; do not merge.

## Reading the mail

- **`History` covers every thread in the material**: one dated line for each
  distinct subject, meeting, introduction or request, oldest first.
- **`How the user writes to them`** comes from the user's own messages to them
  (language, tone, length, how they open, what they ask); **`Cadence`** from the
  dates (`about weekly, July–September`). Each is `Unknown` only when there is
  no such message, or a single one.
- **Signature block first**: into `Contact` field by field (title, org,
  department, office, direct line, booking link, language). A changed signature
  is a dated move or promotion.
- **Address domain = employer** (`@unsw.edu.au` → UNSW), never a role;
  gmail/outlook/qq/163 → `Company: Unknown`. An org page for the domain (listed
  in the `investigation:org-pages` item) → `Company:` is that link,
  `[Name](../orgs/<file>.md)`, cited to the mail that shows it.
- `[attachment]` entries are the file's text; the terms are there; cite their id.
  An unreadable attachment → your final reply.
- Mail gives identity and commitments; sessions give intent. Sources disagree →
  say so; stated in one and implied in another → cite both.

## What to produce

Follow `rem-page-person` exactly, the lead above `Contact` included:
`co rem list people --aliases` reads its headings and `Contact` labels. **`Open threads` is mandatory**: who owes what,
since when.
