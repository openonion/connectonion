---
name: wiki-investigate
description: Build one entity's page from everything every source holds about them, in one pass. The first-run mode — few pages, each complete — as opposed to walking the timeline and leaving many thin ones.
---

# Investigate one subject

You are given three things: **the page as it stands today**, **one subject's
material gathered across every source**, and the handles that were searched.
Your output is that same page, further along.

You are not writing from scratch. The page already exists, with every section
in place and the ones nobody has investigated marked `Unknown`. The structure
is settled; you are filling it and keeping it current.

**Read the current page first.** It tells you three different things, and they
need three different treatments:

| What you find | What to do |
|---|---|
| `Unknown — not investigated yet` | This is your work list. Go find it in the material. |
| A value, and the material agrees | Leave it. Do not reword what is already right. |
| A value, and the material has moved on | Update it, and keep the old state in `History` with its date. |
| A value the material now contradicts | Say so in `Uncertainties`, naming both. Do not silently pick one. |

An `Unknown` you looked for and did not find **stays `Unknown`, and the search
goes in `Uncertainties`**: "Searched Gmail and Outlook over 150 days for
szh526 and 艾玛; no signing entity or ABN appears." That sentence is what stops
the next run from spending another pass on the same dead end, and it is the
difference between "we do not know" and "nobody has looked".

The stage this replaces produced 143 pages with a median of 700 bytes, twenty
of them a single line, because it met each person a few messages at a time and
wrote what that batch happened to know. You are not in that position. If a
section of the page is thin, it is because the material is thin, and you say
so in `Uncertainties` rather than leaving the reader to guess.

## Identity is given, not guessed

The subject arrives with its handles already resolved — names, spellings,
addresses, paths. You do not have to work out who "odi" is; you were told.

So the rule that governs the ordinary maintenance pass — search first, judge
carefully, mark a possible twin — does not apply here in the same way. What
applies instead:

- **Every handle you were given belongs on the page**, in `Also known as:` for
  a person or `Paths:` for a project, including spellings that were wrong. That
  line is how the daily pass will recognise the subject without thinking.
- **Add handles you discovered.** A signature, a second address, a name in
  another script: put it on that line so the next sweep reaches material this
  one could not.
- **A handle that produced nothing is a finding**, and belongs in
  `Uncertainties` with what was searched and over what window.

## Read across sources before writing anything

The point of this stage is that the sources correct each other. Read all of the
material first; do not write the page from the first source and patch it with
the rest.

- **Mail gives identity and commitment** — the signature, the address, the
  legal entity, what was actually agreed and when.
- **Coding sessions give intent** — why the user was doing it, what they were
  weighing, what they asked for in the moment. They almost never carry a full
  name; they carry a first name or whatever dictation heard.
- **When two sources disagree, say so on the page.** A name spelled two ways, a
  count that changed, a term that was renegotiated: the disagreement is the
  interesting part. Do not silently pick one.
- **A fact one source states and another implies is stronger than either.**
  Cite both.

## What to produce

A **person's** page follows `wiki-page-person`, appended to these
instructions. Follow it exactly, including the headings and the `Contact`
labels: the roster behind `wiki_people` finds a person's addresses and aliases
by those labels, so a renamed section is an invisible one and the next batch
meets them as a stranger again.

**`Open threads` is not optional and is not prose scattered through the page.**
It is the section the user reads first. From a real investigation: "the
contract is still in draft, the listings are already co-hosted, and reported
income is A$0 because the agreement is unsigned" was all present in the page --
spread across three other sections, so it read as background rather than as the
thing to act on. Each entry names who owes what, and since when.

For a **project**, the same discipline in its own shape:

```markdown
# ConnectOnion

## What it is
## Paths            every directory, repo and alias it has been called
## Why it exists    the problem, in the user's own framing
## Where it stands  the current state, with a date
## How it is built  the shape a newcomer needs before touching it
## Open threads     who owes what, and since when
## Uncertainties    what was checked and not found
Sources
```

## Finish, then say what you did not finish

End the pass with a short account of coverage: which sources you read, how much
material each one held, and which handles found nothing. That account is what
tells a later run whether this page is worth re-investigating or is simply
about someone quiet.

## What this stage must not do

- **Do not spread one subject over several pages.** Everything you learned
  about them goes on their page. Investigating one person produced three pages
  — the person, plus two project pages restating the same negotiation — and
  the reader now has to hold three accounts of one story. Write a second page
  only when it is a subject in its own right that would still exist without
  this person, and even then put the account on their page and a link on the
  other. One investigation, one page, unless you can say why not.
- **Do not write `agenda/` or `opportunities/`.** Both are views over the Open
  threads and state you are already recording.
- **Do not extract decisions or principles here.** Note what was decided as
  part of the subject's story; lifting it into `decisions/` is
  `wiki-abstract`'s pass, and doing it twice produces two versions.
