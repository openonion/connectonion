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
  another mailbox or address.
- **A number or date** that implies another record: an invoice number, an
  order, a meeting, a deadline someone must have acted on.

## 2. Follow them

Most promising first: what could change the lead, Open threads or Facts.

- Open links and read the page; a URL you read is a source (`[n] <url> —
  <date read>`). Note what it says about the subject, never what it implies.
- Search the archives (`rg -il`, `co rem search`) for every name, number and
  subject line; read matches whole.
- Read unread attachments; cite their ids.
- Stop a lead when it is empty or turns out to be about someone else; record it
  as followed so the next run does not repeat it.

## 3. Add what they establish

- Additions and corrections only: cited facts, dated history lines, the end of
  a thread, contact details exactly as the source writes them.
- What is already right stays as written. Do not reorganise, merge pages or
  draw conclusions across pages — that is `rem-muse`.
- A link that only confirms what the page says is cited once, not quoted.
- A web page about someone with the same name is not this person unless
  something ties them (the same address, company, photo caption, link from
  their mail).

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
