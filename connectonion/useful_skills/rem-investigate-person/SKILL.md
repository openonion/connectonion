---
name: rem-investigate-person
description: Read a person’s identity, relationship and obligations from gathered evidence.
---

# Investigating a person

Why these rules: docs/rem-skills/rem-investigate.md

## Identity is given, not guessed

- The user's addresses (the mailbox names in coverage) are never the subject's;
  `Email`/`Handles` take only addresses the subject writes from.
- Given handles are search leads, not verified aliases. Put one in `Also known
  as:` only with a cited signature, cross-reference or reply thread tying it
  to this person; otherwise leave it unverified in `Uncertainties`. Company
  names go in their own field.
- The subject is the owner of a coverage mailbox → the user's own page: follow
  `rem-owner-page`.
- **A role in a list the user writes about someone else is that person's, not
  the user's.** A role is the subject's only when the subject states it or
  someone states it about them.
- Another page for the same person: name it in `Uncertainties`; do not merge.

## Reading the mail

- **The `investigation:facts` item first**: put each extracted value in its
  cited `Facts` field. Read `Signature`, `Calendar` and mail signatures for role,
  company, office, location and time zone. Date signature changes; keep both
  phones with qualifiers.
- `Phone` means the person's contact number, never a meeting dial-in, passcode
  or attendee's number. Calendar text is context, not their contact details.
- A domain identifies an organisation, not employment. Student affiliation
  is not an employer; unstated employer → `Company: Unknown`. Link a matching
  organisation in the relationship text, citing the mail.
- `[attachment]` entries are the file's text; the terms are there; cite their id.
  An unreadable attachment → your final reply.
- Mail gives identity and commitments; sessions give intent. Sources disagree →
  say so; stated in one and implied in another → cite both.
- Check asks/promises across topics before `Nothing open`; unrelated replies
  close none. Questions promise no deadline. Invites, confirmed logistics,
  arrival, empty forwards or samples do not prove completion.
- Thread context can resolve a group ask after recipients drop. Match the team
  and ask; one thread can mix both. Preserve requester, decision maker and debtor;
  context is not this person's statement, contact date or assigned work.
- Reread `Comparison scope` originals by exact `Provider thread`; they are not new contact.

## What to produce

Follow `rem-page-person` exactly, the lead above `Facts` included:
`co rem list people --aliases` reads its headings and `Contact` labels. **`Open threads` is mandatory**: who owes what,
since when.

**Insight, three shapes** (never copy these facts):
- `At stake: Mia requested the revised SOW on 2026-09-21; it is due 2026-10-03 [5]`
- `Changed: replies went from same-day to none since 2026-08-20, after the price went to A$15k [6][8]`
- `Pattern: every thread since June is invoices; she chases, the user answers in 2–4 days [2][7]`
