---
name: wiki-investigate
description: Build one entity's page from everything every source holds about them, in one pass. The first-run mode — few pages, each complete — as opposed to walking the timeline and leaving many thin ones.
---

# Investigate one subject

You are given **one subject and all of its material at once**: every mail,
every session, every mention, gathered across every source by the subject's
known handles. This is not a slice of a timeline. It is the whole file on one
person or one project, and your output is one page that is finished.

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
- **A handle that produced nothing is a finding.** "Searched Gmail for
  zhouodywork@gmail.com: no mail before 2026-07" belongs in `Uncertainties`.
  Silence about a source you were asked to check reads as "there was nothing
  there", and those are different.

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

For a **person**, the page shape in `wiki-maintain` — fixed sections, `Unknown`
where the evidence is absent, a claim number on every factual sentence. Read
that shape from there; it is the same page, built better.

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
  about them goes on their page. A project they drove gets its own page and a
  link, not a duplicate account of the same events.
- **Do not write `agenda/` or `opportunities/`.** Both are views over the Open
  threads and state you are already recording.
- **Do not extract decisions or principles here.** Note what was decided as
  part of the subject's story; lifting it into `decisions/` is
  `wiki-abstract`'s pass, and doing it twice produces two versions.
