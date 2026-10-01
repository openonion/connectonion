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
- **A page titled by an address or handle is renamed** the moment the material
  names the person: their signature, or what the user calls them in a greeting
  (`# mei.l1990@outlook.com` → `# 李梅`; `# vern.chan` → `# Vern Chan`). The old
  title stays in `Also known as:`. Leaving the address as the title when the
  name is in the material is wrong.
- **Not a person** (a service, a bot, a shared or test inbox, a calendar or
  agent account the user runs): the lead's first sentence says what it is and
  `Role:` reads `Not a person: <what it is>`; every section still present, the
  rest describing what it sends. A real notebook wrote the user's own agent
  inbox up as a correspondent whose identity was "not established".
- The subject is the owner of a coverage mailbox → the user's own profile: work
  from what they wrote; `Our relationship` = account owner; `How the user
  writes to them` = not applicable.
- On the owner's own page, `Role` and `Company` come only from the owner's
  signature or what they say about themselves ("I run…", "my role"). Mail the
  owner wrote *to* someone describes that person ("you", a bio or claims list
  written for them): it belongs on their page, never the owner's. Two real
  first runs gave the owner a recipient's role this way.
- Another page for the same person: name it in `Uncertainties`; do not merge.

## Reading the mail

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
