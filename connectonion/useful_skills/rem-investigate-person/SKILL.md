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
- A given handle, other than the page's address, that found nothing: one
  `Uncertainties` line.
- A page titled by a handle gets the person's name once known (`# vern.chan` →
  `# Vern Chan`, handle kept in aliases).
- The subject is the owner of a coverage mailbox → the user's own profile: work
  from what they wrote; `Our relationship` = account owner; `How the user
  writes to them` = not applicable.
- Another page for the same person: name it in `Uncertainties`; do not merge.

## Reading the mail

- **Signature block first**: into `Contact` field by field (title, org,
  department, office, direct line, booking link, language). A changed signature
  is a dated move or promotion.
- **Address domain = employer** (`@unsw.edu.au` → UNSW), never a role;
  gmail/outlook/qq/163 → `Company: Unknown`. An org page for the domain → link
  `Company:` to it.
- `[attachment]` entries are the file's text; the terms are there; cite their id.
  An unreadable attachment → `Uncertainties`.
- Mail gives identity and commitments; sessions give intent. Sources disagree →
  say so; stated in one and implied in another → cite both.

## What to produce

Follow `rem-page-person` exactly: `co rem list people --aliases` reads its
headings and `Contact` labels. **`Open threads` is mandatory**: who owes what,
since when.
