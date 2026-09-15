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
  one could not. Company and project names belong in their own fields, not in
  the person's aliases, unless a source explicitly uses them as that person's handle.
- **A handle that produced nothing is a finding**, and belongs in
  `Uncertainties` with what was searched and over what window.
- **A page titled by a handle takes the person's name once the material gives
  it.** The map created `# vern.chan` from an address; a signature reading
  "Vern Chan" makes the title `# Vern Chan`, with `vern.chan` kept in
  `Also known as:`. The title is what the user will search for.

If the subject's address matches a mailbox owner named in the coverage, this
is the user's own profile. Describe their work, commitments and projects from
what they wrote. A notice addressed to them does not make its sender's role
or company theirs. Keep the same headings, but identify `Our relationship`
as the account owner and mark `How the user writes to them` as not applicable
to a self-profile; do not invent a relationship between the user and themself.

## Read across sources before writing anything

The point of this stage is that the sources correct each other. Read all of the
material first; do not write the page from the first source and patch it with
the rest.

- **Mail gives identity and commitment** — the signature, the address, the
  legal entity, what was actually agreed and when.
- **Attachments are where the terms are.** A `[attachment]` item is the text
  of a file someone sent — a contract, a deck, a spreadsheet — read out of the
  PDF or document. The mail says "please see attached"; the attachment says
  7.5% of Net Booking Revenue. Cite the file by its source id. An item that
  reads `[could not read PDF: …]` or `is not read` is a finding for
  `Uncertainties`: the file exists and was not read.
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
instructions by the notebook runner. If invoked directly through `co ai` and
the template is not appended, read `../wiki-page-person/SKILL.md` relative to
this Skill's directory before writing. Follow it exactly, including the headings and the `Contact`
labels: the roster behind `co wiki people` finds a person's addresses and aliases
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

## Supplement sources through their own tools

The supplied material lists exactly which sources the collector searched. Check
that coverage before claiming a complete investigation. Use the existing CLIs
for additional searches; do not invent a second mail client or credentials flow.

- Run `co email addresses` for the account's own email service. If authorized,
  inspect `co email inbox -n 100 --offset 0`, then subsequent offsets, and
  `co email sent -n 100 --to <address>`. Read relevant messages with
  `co email read <id>` and `co email sent read <id>`. This service is distinct
  from Gmail and Outlook. Its sent listing has no offset: report that coverage
  limit; do not claim it searched all sent history.
- Read relevant documents in the known project/source directories. PDFs, Word
  documents, spreadsheets, slides and calendar attachments are evidence, too.
  Follow file references from messages; do not sweep unrelated private folders.
- For a project, inspect the recorded repo/paths and its README, issues and PRs
  if access is available. Distinguish user intent in sessions from verified
  repository state. A directory name alone does not establish a project.
- Record each source as searched (with window/query), unavailable, or not
  searched. Authentication failures and unreadable files leave gaps open.

## What the sources did not hold: look on the open web

When every source is read and a field still says `Unknown`, some of what is
left the web holds. Take **only** these, and only where they read `Unknown`:

| Field | Where to look |
|---|---|
| Company | the domain of their address (`@unsw.edu.au` → unsw.edu.au), then that site |
| Role | the employer's own site, a conference page, a public bio |
| Phone | the company's contact page — a switchboard is a finding; a mobile is not yours to find |
| Signing entity | a company register (ABN lookup for Australia), the site's footer |
| Handles | the company site's "team" page, a public GitHub |

```
co browser go_to "https://<domain>"       # the site itself, first
co browser get_text                        # read it; do not guess from the URL
```

`co browser` is a shell command and it is the browser here: run it the way you
run any other command. Do not reach for a computer-use or `cua_repl` plugin
even if your environment offers one — on this runner it answers "No browser
is available", and that answer is about the plugin, not about the web.

One site, one read, one fact. **Do not open LinkedIn** — a run of automated
profile views got the account flagged and force-logged-out on 2026-08-23.
Do not look up `Who they are` or `Our relationship` on the web: those come from
the user's own material, and a web bio pasted there is somebody else's page.

Write a web fact with the page you read it from as its source
(`- Phone: +61 2 9385 1000 [W1]`, `[W1] unsw.edu.au/contact — observed <date>`),
and what you looked for and did not find in `Uncertainties`. A guess is worse
than a gap: the next pass would build on it. Five page loads is generous; ten
means the site does not have it.

You should have `co browser`, `co outlook` and `co gmail` wherever you are
running; if one of them fails to run or cannot reach the network, say so in
`Uncertainties` ("web: not reachable on this runner") and leave the fields
`Unknown`. Do not pretend to have looked.

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
