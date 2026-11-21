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
For the period's most important decision, quote the user's own words from that
period if a session message or mail the user wrote says it (copy it exactly,
in its language, and cite it); if none exists, say so in your reply.
The timeline item is the project's whole history, oldest first, month by month.
Walk it from the first month and read the originals at its `github:` ids;
look up commits for their full `git:` ids. The timeline itself is a reading guide.
Add the turning points — the start, what was merged, what was decided and why —
as dated, cited `Key decisions` lines spread across the whole history, not only
the latest weeks. For a monorepo sub-project, its history is the pull requests
in the timeline whose titles name it. Follow those through the older months
before following the latest session.

## Think like an open-source intelligence analyst

The owner, 2026-11-19: "你应该用开源情报的方式去写每一个段落…应该把骨架都写出来，既有丰富的细节，也要有整体的框架。"
A page after enrich should let the user brief someone on the subject in two minutes.

For a **person**, establish and cite, from their own words, the mail and public sources:
- **Career timeline**: each employer or venture, the role, the years, and what they did there: products,
  clients, size, results. Their own CV, LinkedIn snippet, company site, talks and registries come first.
- **Education and credentials**; **public work**: companies registered, talks, papers, repositories, press.
- **The people they overlap with**: co-founders, colleagues, investors, introducers. Link the ones the
  notebook has pages for.
- **Where they are online**: LinkedIn (snippet only), GitHub, their company's site.

For an **organisation**: what it does and for whom, when and where it was founded, who runs it, its units,
its size, funding and registration, its timeline, and the people the notebook knows there.

Every organisation the subject works or worked at, founded, studied at or advises is written as a link to
its page, `[Name](../orgs/<slug>.md)`, in `Company` and in each career line. The program creates a page
that does not exist yet and adds the person to it. A career line or Company without that link is refused.

Write each section as a **skeleton with detail**: a lead sentence that frames it, then the dated lines that
fill it in, newest first. `Who they are` looks like this:

```
Founder of [Kiln Labs](../orgs/kiln-labs.md), an IT consultancy for local councils, with about 30 years in enterprise IT. [3][7]
- 2019–now: Founder, [Kiln Labs](../orgs/kiln-labs.md) — runs infrastructure projects for three councils [3][7]
- 2008–2019: Head of IT, [Harbour Health](../orgs/harbour-health.md) — led the move to cloud, a team of 40 [7]
- 1994–2008: Systems engineer, then architect, [Northwind](../orgs/northwind.md) [7]
- Education: BEng, [UNSW](../orgs/unsw.md) (1993) [7]
- Worked with [Mara Ostrowski](../people/mara-ostrowski.md) at Harbour Health, 2015–2019 [8]
```

Say an unknown once ("Earlier career: not found in public sources [9]"); never pad and never guess from a
name match. Length is not a cost here: when the page grows past the limit, the program moves the oldest
History to the page's archive, word for word. Spend the space on substance.

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
- What someone asked, decided, promised or gave as a reason goes on the page
  in their own words: a short verbatim quote of that sentence, cited, not a
  paraphrase. A correspondent who wrote forty mails should be heard on the
  page. Quote the author of the original only (not a forwarded text, a
  title, a bot or an agent prompt), never a greeting, a sign-off or a
  command, and each sentence once.
- What is already right stays as written. Do not reorganise, merge pages or
  draw conclusions across pages — that is `rem-muse`. The lead changes only
  when a new fact changes what is live; even then keep its quotes.
- Never delete or swap out a quote, an owner instruction or a cited fact
  because you found a different one; add yours beside it. Never remove a
  line. When a source contradicts a line, correct it in place and keep the old
  value with when it stopped being true ("Head of Design [9] (was Senior
  Designer until 2026-10-01 [3])"), and say which in your reply.
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

Everything a lead established goes on the page in the section it belongs to: career lines and
organisations in `Who they are`, terms in `Our relationship`, threads in `History` and `Open threads`.
A lead that gave nothing new goes in your reply as followed.

Before you finish, compare your page with the page you were given: every
`“…”` quote and every `Sources` id it had must still be on the page, and every
`[n]` in the text must be defined under `Sources`. Restore any you dropped.
A dropped quote or source id is refused and sent back for repair. So is a
dropped cited line outside the lead, History and Uncertainties: it must still
be on the page, or be corrected in place with its old value kept.

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
