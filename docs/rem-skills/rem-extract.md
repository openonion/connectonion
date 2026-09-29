# Why the rem-extract rules are what they are

The runtime Skill lives at `connectonion/useful_skills/rem-extract/SKILL.md`
and holds only the rules; it is re-sent on every model turn, so its reasons
live here (#1851). This file is not loaded at runtime; change it when you
change a rule.

## Two passes

Extraction is the first of two passes. The second (`rem-maintain`) reads only
the extraction notes and never the raw messages, so a fact left out here is
gone, and a fact invented here becomes a page. That is why the Skill prefers a
precise bullet over a summary, and nothing over a guess, and puts no cap on
length.

The literal `Nothing worth keeping.` is parsed: `connectonion/rem/extract.py`
defines it as `NOTHING`, and `service.py` / `investigate.py` compare against it
to skip the maintain pass. Any other wording ("nothing to keep") would be
treated as notes.

## Coding sessions: intent, not execution

A coding session arrives as the user's messages only, and that is the whole
point of reading one: what the user says is what they want -- the requirement,
the decision, the correction, the standard they hold the work to. The
assistant's replies were execution and are not in the batch.

A bullet naming a commit SHA, branch, changed file, test count, CI result,
command, or bare issue/PR number describes the execution and is wrong before it
is stale. The two tests in the Skill (could this be written without the user
having said anything? will it be true next month?) catch it. A machine detail
survives only inside the user's own condition -- "he refuses to ship 1.8 unless
the default engine stays free" keeps the version because the user set it.

The harness's own text (a transcript quoted back, a skill body, an instruction
file) sometimes still reaches the batch under `role: user`; it is not the user
speaking.

## Mail grouped by person

Mail arrives with both sides, because the other side is a person, and grouped by
person, oldest first, so a correspondent's whole history is in front of the
model at once. Writing from all of it is what lets the timeline, the way they
write, and the user's way with them appear end to end.

## People: be generous

This is where a thin notebook fails. A person page is the user's memory of a
relationship, and the maintainer can only write what extraction hands it --
including how each side communicates (openings, sign-offs, register, cc habits,
reply speed, language, verbatim quotes), e.g. the user writing "Hi Vern," then
"On capacity: ... On timing: ...", direct, saying when something would stretch
them.

## Transactional streams

Booking inquiries, applications and ticket requests are one bullet each under a
shared heading so the maintainer keeps them on one rolling page; one page per
guest was dead a week later.

## What to drop: three kinds of mail

Each produced pages in a real 60-day run:

- **Someone else's article** -- a newsletter, Substack post, investor's essay or
  vendor update is their thinking, not the user's knowledge, even from a
  personal address.
- **A receipt, confirmation or issued credential** -- "Your agent address is
  0x8ad3..." or "Reservation confirmed" is a fact about an account or booking.
- **A one-line stranger** -- "Fuzz expressed interest" with no role, company or
  relationship.

## The People block shape

The sub-bullets mirror the person page's fixed sections. A sub-bullet left out
cannot appear on the page; because the sections are fixed, a missing one shows
as a visible `Unknown` rather than quietly disappearing.

`Open` and `Uncertain` get their own rules because they are the ones a batch
usually has evidence for and a summary usually drops. "Follow-up status is not
recorded" is a gap dressed up as a finding. `Uncertain` is how a thin person
stays honest instead of short.

The Emma example in the Skill is kept as the output-format reference, trimmed
for runtime size in #1851.

### The full example before trimming

The runtime example was shortened in #1851; this is the original, which shows
how much a well-evidenced block can carry:

```
## People
- **Emma (飘啊飘)** — szh526@gmail.com
  - Contact: email szh526@gmail.com; phone Unknown; signing entity ZEHAO SHEN,
    ABN 37 387 221 177, 6007/117 Bathurst St, Sydney NSW 2000; Gmail display
    name "飘啊飘"; Mandarin for operations, English for contract redlines.
    (outlook:1adf5a91461b)
  - Who they are: independent Sydney Airbnb host running a multi-property
    portfolio — 7 property types across 3 buildings as of 2026-07-10.
    (outlook:9f2c1a4b7e30)
  - Why they are here: came in as a pricing customer for the user's STR
    pricing agent (~July 2026); by August the same relationship widened into
    an online co-hosting collaboration. She wants revenue per property and
    reads every contract before signing. (outlook:9f2c1a4b7e30,
    outlook:7c8e2d10a4f5)
  - Relationship state: pricing client *and* contract counterparty. Agreement
    signed by both parties 2026-08-07 — 8% of Net Booking Revenue excluding
    cleaning fees, per-property 90-day review, 14-day removal right. She
    negotiated hard on liability and exit, then signed the same day.
    (outlook:4032690ac32e, outlook:92634a3a8c50)
  - History:
    - 2026-08-06 — the user sent v9 with a sectioned Mandarin explainer; she
      replied ~1.5h later in English with 7 clause-change requests.
      (outlook:7c8e2d10a4f5, outlook:bf2cd2898fb3)
    - 2026-08-07 — the user signed; she returned the signed document 8:43 PM
      AEST. (outlook:92634a3a8c50)
  - How they write: register-switching — English for legal matters (numbered,
    precise, "Regards, Emma"), brief practical Mandarin for operations
    ("收到"). Itemised, fast, proposes exact contract language.
    Quote: "Please see attached signed document." (2026-08-07)
  - How the user writes to them: opens "Emma，你好，", signs "Aaron"; sections
    long contract mails `== N. 标题 ==` and translates every clause into what
    it means for her; leads with the reassuring conclusion then the math.
  - Cadence: near-daily same-day replies through the 2026-08-05→07 sprint, on
    top of the pricing relationship since ~July 2026.
  - Open: nothing owed by either side as of 2026-08-07 — contract executed.
    Next contact is operational (pricing recommendations, onboarding).
  - Uncertain: property count — 7 confirmed 2026-07-10, other notes say ~12;
    no phone number anywhere in the batch; whether her redlines were
    lawyer-drafted is inferred from their precision, not confirmed.
```

The one-line form for other headings also had an Agenda example:

```
## Agenda
- The user promised Alice Chen the Aurora storage proposal by Friday
  2026-09-11. — user, 2026-09-07, codex:s1:512
```

## Bad and good

For someone else's article: Bad: `## Knowledge — Antifragile agents: systems
that gain from disorder... — newsletter, 2026-08-14`. Good: nothing.
