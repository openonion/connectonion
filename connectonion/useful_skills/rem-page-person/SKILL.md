---
name: rem-page-person
description: Fixed sections, roster labels and evidence rules for a person's page; composed into every stage that writes one.
---

# A person's page

Read supplied page/material. Write, check, fix once, stop; use this format.

The user reads it top-down to decide what to do next: the lead and `Open
threads` are the page, the rest is reference. Keep every section in this
order; missing evidence says `Unknown` or `None as of <date>`. Every factual
sentence cites `[n]` into `Sources`. Placeholders are not evidence.

```markdown
# <observed name>

<lead>. Last contact: <date>.

## Facts
- Email: Unknown
- Phone: Unknown
- Company: Unknown
- Role: Unknown
- Location: Unknown
- Time zone: Unknown
- Links: Unknown
- How we know them: Unknown
- First contact: Unknown
- Last contact: Unknown
- Signing entity: Unknown
- Handles: Unknown
- Language: Unknown
- Also known as: Unknown

## Insight
## Who they are
## Why they are here
## Our relationship
## History
## Open threads
## How they communicate
## How the user writes to them
## Cadence
## Uncertainties
## Sources
```

Rules:

- **Lead: three cited sentences, then `Last contact: <date>, <channel>.`**
  (1) Who they are to the user: role, organisation, why they matter. (2) What
  is live: the most consequential open item, who owes whom, the ask as a short
  exact quote with its date and any due date; with nothing open, how the last
  thread ended. (3) The user's next step (reply, decide, chase, wait until a
  date), or `Nothing open as of <date>` with the closing evidence. Never open
  on a gap or a doubt.
- **One voice**: the owner is `the user` in every sentence, never their name,
  `you` or `we`.
- **`Facts` is data, written first.** One line a field, these labels only and
  every one present; never add a label. A missing value is exactly `Unknown`.
  Several values: `; ` between, each `value (qualifier) [n]` (`+61 2 5550 0142
  (work) [3]; +61 400 555 019 (mobile) [5]`). Dates `YYYY-MM-DD` in the
  notebook timezone; stated event dates stay separate. Every value is cited
  except `Email`, `Handles`, `Also known as`. A contact detail never goes in a
  sentence instead of its field. `Links`: LinkedIn, personal or company site.
  `How we know them`: who introduced whom, or the first thread.
- **`Insight` is 2–4 cited bullets of at most 30 words, each starting `Now:`,
  `Changed:`, `At stake:` or `Pattern:`**: what no other section says outright:
  what moved, what is at risk, a pattern over time (reply speed, topics, who
  chases whom). Never restate the lead or an open thread; never generic
  ("key stakeholder"); thin material: `- Unknown`.
- **`Language` is observed**: the language they write to the user in.
- **`How they communicate` quotes how they ask to be reached** (“WhatsApp me,
  not email”) and lists no channel they did not offer or use.
- **`Company` needs stated employment**; a student or mailbox domain proves
  none (`Unknown`). Link schools/groups in relationship text.
- **`Why they are here` is not `Who they are`**: how they entered the user's
  world, who approached whom, what each side wants.
- **`Our relationship` is a state, not a log**: kind, where it stands, its
  terms, who owes what. A term (amount, ratio, date, condition) is quoted with
  its date: `“<exact words>” (YYYY-MM-DD) [n]`. Keep each local link with its
  citations and privacy markers. Separate events, separate lines.
- **`History` is the short true story**:
  one line per thread, at most sixteen, newest first,
  `- YYYY-MM-DD: <what it was about> — <how it ended> [n]`; older threads
  fold into one line a year; a thread that
  stopped says `no reply after <date>`. Not a send or a newsletter.
- **`Open threads` lists only what someone still owes**, one line each, the
  user's debts first, then by due date:
  `- The user owes <Name>: <what> — “<exact ask>” (YYYY-MM-DD) [n] — due <date>`
  or `- <Name> owes the user: …`, `- <A> owes <B>: …`, ending `— open as of
  <date>` when no due date was set. A later reply, a delivered item or a passed
  event date closes a thread: it moves to `History`. An ask with no movement
  for 60 days goes to `History` as `went quiet`. Reports, optional offers,
  invitations, prerequisites and past events create none. Keep an explicit
  due date and any permission to proceed without a reply. Closure:
  `Nothing open as of <date>`.
- **Say each thing once, plainly.** A fact lives in one section; the lead and
  `Insight` point to it. Status is a dated fact (`no reply since 2026-10-12`),
  never "is not established", "unconfirmed" or "in the supplied mail". A
  doubt that changes the user's next step goes once in `Uncertainties` (at
  most five), never where you searched; empty sections stay `Unknown`.
- **Keep what the map already knew.** `Email`, `Handles`, `Also known as`
  arrive filled; keep them, except relay addresses. Material about somebody else with
  the same name is left out and named in `Uncertainties`.
- Say their name or "they"; "he"/"she" only where their own words show it.
- **Sources**: `- [n] <source id> — <date>`; claims stay in sentences. Never an
  assistant's memory file. Reuse numbers and list only cited sources.

## Exact headings

Never annotate headings or rename `Facts` labels: code reads them by name. Preserve the runner's
`Investigation:` line unchanged.
