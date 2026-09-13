---
name: wiki-page-person
description: What a person's page in the notebook is made of — the fixed sections, the labels the roster reads back, and the rules a thin page always breaks. Composed into every stage that writes one, so there is one definition rather than a copy per stage.
---

# A person's page

This is the page the user will open most, and the one most likely to come out
thin. It is the memory of a relationship, and it grows with every interaction;
never shrink it back to a summary.

**Every section below is always present, in this order.** A section the
evidence does not support says `Unknown`, or `None as of <date>` — it is never
dropped. An empty slot is information: it tells the user what to go find out.
A page that omits a section instead hides the gap, and the one-line person
page is exactly what that produces.

**Every factual sentence carries a claim number** `[n]` pointing into the
`Sources` list at the foot. A sentence you cannot number is a sentence you
cannot keep.

```markdown
# Emma (飘啊飘)

## Contact
- Email: szh526@gmail.com [2]
- Phone: Unknown
- Company: Independent Sydney Airbnb host / short-stay operator [1]
- Role: Property owner-operator; the user's STR pricing-agent client and
  online co-hosting counterparty [1][3]
- Signing entity: ZEHAO SHEN — ABN 37 387 221 177, 6007/117 Bathurst St,
  Sydney NSW 2000 [2]
- Handles: "飘啊飘" (Gmail display name) [2]
- Also known as: Emma, 飘啊飘, Emma Shen — every spelling any source has used
  for her, including ones that were wrong; this line is how the next batch
  recognises her
- Language: Mandarin for pricing and operations; English for contract
  redlines [6][8]

## Who they are
- Sydney short-term-rental host; the user's first and still active client for
  the AI pricing agent, onboarded around July 2026. [1]
- Runs a multi-property portfolio — 7 property types across 3 buildings
  confirmed 2026-07-10. [9]
- Legally careful counterparty: her redlines use precise clause drafting
  (indemnity carve-outs, service-fee-on-cessation, interim-provider rights).
  *Inferred from their precision; not confirmed that a lawyer drafted them.* [5]

## Why they are here
She came in as a pricing customer and the relationship widened from there: the
user pitched automated Mandarin pricing recommendations for her Airbnb
portfolio, and by August the same relationship had become a co-hosting
collaboration. She is here for revenue per property, and she reads every
contract before she signs it. [1][3][5]

## Our relationship
Two relationships at once: an operating pricing client, and a contract
counterparty on the Technology & Online Operations Collaboration Agreement. [1][3]

**Where it stands:** signed by both parties 2026-08-07 [12]. Deal shape: 8% of
Net Booking Revenue with cleaning fees excluded from the base; per-property
90-day commercial review; either party may remove a property on 14 days'
notice with no exit fee beyond accrued fees. All 7 of her requested changes
were adopted. [11][12]

**How she plays it:** negotiated hard on liability and exit, accepted the
cleaning-fee concession, then signed the same day. Businesslike and durable —
she pushes, but she closes. [4][5][12]

## History
- 2026-07-10 — Confirmed pricing scope: 7 property types, 3 buildings
  (38 York St / QVB, 243 Pyrmont St, 1 Brushbox St). [9]
- 2026-08-06 — The user sent v9 with a section-by-section Mandarin explainer;
  she replied ~1.5h later in English with 7 clause-change requests. [4][5]
- 2026-08-06 — Ody sent v10 adopting all 7, compressed to 10 core sections. [11]
- 2026-08-07 — The user signed; she returned the signed document 8:43 PM AEST. [12]

## Open threads
- **"线上运营合作合同 — 清洁费已调整，新版请过目"** (t1.MTlmZDVhOTE0NjFiYTlhYQ) —
  closed. Contract executed 2026-08-07; no action owed by either side. [12]
- **Nothing open as of 2026-08-07.** Next contact will be operational:
  pricing recommendations and onboarding the sourced properties.

## How they communicate
Register-switching: English for legal matters — numbered, precise, "Regards,
Emma" — and brief practical Mandarin for operations ("收到"). Organised and
itemised; sends her own structured lists. Fast turnaround, and comfortable
proposing exact contract language rather than describing a concern loosely. [5][8]
> "Please see attached signed document." (2026-08-07) [12]

## How the user writes to them
Opens "Emma，你好，", signs just "Aaron". Long contract mails are sectioned
`== N. 标题 ==` with every clause translated into what it means for her.
Leads with the reassuring conclusion, then the math ("先说清楚这不是涨价").
Flags anything that could be misread before it happens, invites pushback
explicitly, and routes clause detail to Ody. [4][6][7]

## Cadence
Near-daily, same-day replies through the 2026-08-05→07 contract sprint, on top
of the ongoing pricing relationship since ~July 2026. Expect it to settle back
to operational pace now that the contract is signed. [3][5][12]

## Uncertainties
- Property count: 7 confirmed 2026-07-10; other notes reference ~12 as of
  August — not verified here.
- No phone number on file.
- Whether her redlines were lawyer-drafted is inferred, not confirmed.
- The signed document itself was not opened; signature is confirmed from the
  thread only.

Related: [LaneStay pricing](../projects/lanestay-pricing.md), [Ody Zhou](./ody-zhou.md)

## Sources
- [1] First and active STR pricing-agent client, onboarded ~July 2026 —
  high — observed 2026-07-10 — outlook:9f2c1a4b7e30
- [2] Signing entity ZEHAO SHEN, ABN 37 387 221 177 —
  high — observed 2026-08-06 — outlook:1adf5a91461b
- [4] v9 terms and the plain-language Mandarin explainer —
  high — observed 2026-08-06 — outlook:7c8e2d10a4f5
- [5] Her 7 English clause-change requests —
  high — observed 2026-08-06 — outlook:bf2cd2898fb3
- [11] v10 adopting all 7 requests — high — observed 2026-08-06 — outlook:4032690ac32e
- [12] Both signatures; contract executed — high — observed 2026-08-07 — outlook:92634a3a8c50
```

Rules that make this page work, and that a thin page always breaks:

- **`Contact` is fields, not prose.** A phone number inside a sentence cannot
  be found, and `Unknown` is the only way the user learns that the mailbox
  never carried one. Never write a contact detail into the summary instead.
- **`Why they are here` is not `Who they are`.** Identity is what they do;
  this is how they entered the user's world — who approached whom, and what
  each side wants out of it. It is the section most often missing and the one
  the user asks for most.
- **`Our relationship` is a state, not a log.** Say what kind of relationship
  it is, where it stands today, its concrete shape (numbers, terms, who owes
  what), and how the person plays it. The dated log lives in `History` and is
  evidence for this section, not a substitute for it.
- **An open thread names who owes whom what, and since when.** "Discussion
  status is not recorded" is not an open thread — it is a gap dressed up as a
  finding. If the user owes a reply and has owed it for twelve days, say that.
  If nothing is open, say `Nothing open as of <date>` and name the next
  expected contact.
- **Mark inference as inference.** A judgment drawn from how someone writes is
  worth keeping, and worth labelling, so a later pass does not harden it into
  a fact.
- **`Uncertainties` is where a thin page becomes honest** instead of short.
  What is unknown, what is inferred but unconfirmed, what was referenced but
  not read.
- **Numbered claims.** Each entry: the claim, confidence (high / medium /
  low), the date it was observed, and the source id. Reuse a number for a
  claim you already listed; never list the same claim twice under two numbers.
  Only list claims a sentence actually cites.
- A person with one message and no identity does not get a page at all. A
  person with a second message gets their page extended, not rewritten.


## The headings are copied exactly

Nothing else goes on a heading line. A stage handed this shape with notes
beside the headings wrote `## Our relationship          state and shape, not a
log` into a real page, and `wiki_people` then found no `Our relationship` at
all. The labels under `Contact` are read back the same way: `Email:`,
`Phone:`, `Company:`, `Role:`, `Signing entity:`, `Handles:`, `Language:`,
`Also known as:`. A renamed label is an invisible one, and the next batch meets
the person as a stranger.
