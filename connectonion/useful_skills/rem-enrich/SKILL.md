---
name: rem-enrich
description: Find the leads a page has not followed — links, attachments, names, older threads — follow them, and add what they establish.
---

# Enrich one page

Input: a written page, its reading ledger and search coverage.
Output: the page with new cited facts, and a lead list in your final reply.
Follow the page kind's `rem-page-*` rules and `rem-investigate`'s quote and
evidence rules unchanged.

Enrich is discovery. The page was written from what init happened to read;
your job is to find **what else exists** and where it points. Finding a
direction to investigate is worth more than polishing a sentence.

## Leads from the last round

The prior-runs item holds the last enrich's open leads and the last muse's
open questions. Follow those first. Mark each followed, open or blocked again;
do not repeat a lead already followed.

## A project's history

A long history arrives one period per turn: add only that period's turning
points in each turn, then follow the other leads in the last turn.
The timeline item is the project's whole history, oldest first, month by month.
Walk it from the first month and read the originals at its `github:` ids;
look up commits for their full `git:` ids. The timeline itself is a reading guide.
Add the turning points — the start, what was merged, what was decided and why —
as dated, cited `Key decisions` lines spread across the whole history, not only
the latest weeks. For a monorepo sub-project, its history is the pull requests
in the timeline whose titles name it. Follow those through the older months
before following the latest session.

## 1. Find the leads

Read every cited original whole, then list what it points to that the page has
not followed. A lead is anything that could hold more:

- **A link**: a website, LinkedIn or GitHub profile, a shared document, a
  repository, a calendar or booking page, a product or company site. Open it.
- **An attachment** not yet read: a contract, invoice, CV, deck, screenshot.
- **A name**: a person, company, project, product or place mentioned but
  without a page or not linked from this one.
- **A thread** whose start or end the page does not have: `Re:` with no
  original, a request with no reply, a reply quoting earlier mail.
- **An older period**: first contact earlier than the page's First contact;
  mail before the window init read.
- **Another channel**: the same person in sessions, GitHub issues, WhatsApp,
  another mailbox or address. The subject's agent mailboxes and aliases
  (`<name>@mail.openonion.ai`, `0x…@mail.openonion.ai`, a relay or handoff
  address) are their channels too: search mail from and to each one as you
  would their own address.
- **A number or date** that implies another record: an invoice number, an
  order, a meeting, a deadline someone must have acted on.
- **The reading ledger itself**: every kind of source it lists that the page
  cites none of (sessions, GitHub items, attachments, another address) is a
  lead; open at least the ones about this subject in each kind.

## 2. Follow them

Most promising first: what could change the lead, Open threads or Facts.

- Open links and read the page; a URL you read is a source (`[n] <url> —
  <date read>`). Note what it says about the subject, never what it implies.
  A quote from a web page is one run of its text as written; never join two
  fields or labels into one quote.
- Search the archives (`rg -il`, `co rem search`) for every name, number and
  subject line; read matches whole.
- Read unread attachments; cite their ids.
- Stop a lead when it is empty or turns out to be about someone else; record it
  as followed so the next run does not repeat it.

## 3. Add what they establish

- Additions and corrections only: cited facts, dated history lines, the end of
  a thread, contact details exactly as the source writes them.
- What is already right stays as written. Do not reorganise, merge pages or
  draw conclusions across pages — that is `rem-muse`. The lead changes only
  when a new fact changes what is live; even then keep its quotes.
- Never delete or swap out a quote, an owner instruction or a cited fact
  because you found a different one; add yours beside it. Remove a sentence
  only when a source contradicts it, and say which.
- Cite with the id on the material's `Source:` line (`gmail:` or `outlook:`
  plus 12 hex characters), never a provider's raw message id or thread id.
- The owner is `the user`, never their name, even when mail is signed with it.
- A link that only confirms what the page says is cited once, not quoted.
- A web page about someone with the same name is not this person unless
  something ties them (the same address, company, photo caption, link from
  their mail).
- A personal contact detail found on the web (a mobile or WhatsApp number, a
  home address, a private email) goes on the page only if the subject
  published it themselves for people to contact them (their own site or
  profile's contact section), and it ends with `[personal]` before its claim
  number: `+61 4xx xxx xxx (WhatsApp, on their site for contact) [personal]
  [9]`. A number only on a company page is the company's: qualify it so.
  A number the subject publishes on their own site or profile is theirs even
  when a company page also lists it: write it once, as theirs, with
  `[personal]`, and cite both. Anything else found about their private life
  stays off the page.
- Anything you add to `Uncertainties` is a question ending in `?`.

Keep the page near the page rules' size (about 15,000 characters). As it
fills, add only what changes Facts, the lead, `Open threads` or `History`;
other findings go in your reply as followed leads, so muse can use them.

Before you finish, compare your page with the page you were given: every
`“…”` quote and every `Sources` id it had must still be on the page, and every
`[n]` in the text must be defined under `Sources`. Restore any you dropped.
A dropped quote or source id is refused and sent back for repair.

## Final reply

After the edit, list every lead, one line each:

```
- followed | <lead> | <where it came from [n]> | <what it gave, or "nothing">
- open     | <lead> | <where it came from [n]> | <why it matters> | <how to follow it>
- blocked  | <lead> | <where it came from [n]> | <what stopped you: login, paywall, gone>
```

Open leads are the next run's work and muse's material; be specific: not
"look into his company", but "read the 2025-11 thread `Re: SOW v2`
referenced in [7]; the page has no reply".
