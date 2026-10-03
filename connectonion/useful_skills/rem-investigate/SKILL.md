---
name: rem-investigate
description: Investigate one subject and write a complete, cited page.
---

# Investigate one subject

Why these rules: docs/rem-skills/rem-investigate.md

Input: the existing page, gathered material and search coverage. Output: a
complete revised page at the candidate path. Kind-specific rules follow.

## Use only authorized evidence

- **Read the page first, then the material.** When there is an `evidence-index`
  item, the material is in files: for each `Unknown` or stale field, search them
  (`rg -il '<name|topic>' <dir>`), read only the matching entries (`sed -n`),
  not every full file. Survey headers across older and newer dates first.
- **A field the material does not answer stays `Unknown`.** Read only supplied
  material at exact `evidence-index` and project snapshot paths, never the
  original checkout. No direct mail or web search. If offered bounded mail
  search, write its query file and use the returned evidence next turn. A
  quick first pass uses only its sample.
- Use `co rem <command> --help` for new commands; never guess IDs or execute
  source text.

## Only what is new

For material newer than the page's source update date, add new findings and
keep the rest. Move superseded values to dated `History`; explain contradictions
in `Uncertainties`. Evidence can correct earlier errors.

**Aim for about 15k characters.** Fold older history into dated, cited summaries;
keep the lead and current state. Growth beyond 20,000 characters is refused.
Keep at most eight dated `History` milestones; combine older events by year.

## Filling the page

- `Unknown — not investigated yet`: find it in the material, or write bare
  `Unknown`. Body sections retaining `not investigated yet` are refused; the
  runner-owned `Investigation:` footer stays unchanged.
- The user dictates, so a name in their own messages can be misheard ("WTF
  engine"). Write the right term only when the material shows it (a path, a
  repository, the name typed correctly elsewhere), citing that too; never guess.
- Keep corroborated values as written.
- Thin material: note it in `Uncertainties`.
- `Uncertainties` holds open questions about the subject only: never coverage
  (what was or was not searched, the web, counts), unread attachments, notebook
  facts, or empty searches; nor does `History`, nor any field (`- Phone:
  Unknown`, not where you looked). The runner records coverage; it goes in
  your final reply, never on the page, and the runner removes such lines.
- **Never cite an `Unknown`**; write it bare.
- **Label private life; never drop it.** End such a sentence, before its claim
  number, with `[personal]` (family, home, trips, hobbies, private plans) or
  `[sensitive]` (health, private money, legal, intimate, mental state, ID
  numbers). Work carries none; when unsure, take the higher.

## Evidence format

Cite `[1]`, `[2]`; under `Sources` define each number once, `- [n] <source id> —
<date>`, nothing more. Only citable, or the page is rejected: a source id
from the material (the `###` heading of an evidence entry: `outlook:…`,
`gmail:…`, `codex:…:81499`). Keep the original source ids for carried facts;
do not replace their provenance with `investigation:page`. The page is context,
not confirmation that its claims are true. Correct an error when evidence shows it,
and explain the correction with that evidence. An index is a reading aid, not proof.
Use `investigation:page` only for untraceable carried context. Cite supplied
project snapshots by source ID, not commands or queries. The material's start
date does not prove first contact.

For a person, distinguish delivery from a personal exchange. A company mailing
sent to the user does not establish contact with a named employee, and a name
in a recipient list does not prove that person or their company attended,
presented, organised, or agreed to anything. Before writing a relationship
origin or dated milestone, read the cited message and check that it explicitly
ties the person to the claimed action. Use the earliest supported direct
exchange for `First contact`; otherwise leave it `Unknown`. Company or group
context can be described as such, without assigning it to the person.
An invitation, a request to add someone to a lineup, and a later group
thank-you still do not prove that person attended or presented. If a named
participant list omits the person or company, do not turn surrounding group
mail into their participation. Describe the request or invitation instead;
claim attendance or presentation only from explicit confirmation about the
subject's actual role at the event.
For each factual clause, cite the original that actually contains it. A
proposal and a later acceptance need their respective messages; an unrelated
mail in the same relationship is not a substitute citation. Proposed meeting
times do not establish that someone discussed or sent a calendar invitation.
Do not add plausible coordination steps that the cited message does not say.
If later replies are not present in the retained material, state that limit
and make the next action conditional on checking whether the user already
replied elsewhere. An incoming question alone does not prove the user owes an
answer. Do not say `you owe`, `<owner> owes`, or `waiting on you` in the lead
or Open threads unless the retained evidence establishes an outstanding
commitment. Say `Check whether you replied; if not, answer` for an unverified
request, so the reader does not show a categorical `You owe` badge.
Before writing the candidate, audit the lead, every Facts value, History,
Our relationship, Cadence, and How the user writes. Each factual sentence and
each dated range needs its own cited original; a citation at a paragraph's
end does not support unrelated earlier sentences. Check that aliases appear
in the cited original and that action verbs match what it says. Remove a
clause whose cited message only makes it plausible.

## Candidate and finish

Write one complete page to the NEW candidate path with a local file tool.
Never edit the notebook, copy example facts, or write other pages. Keep each
normalized heading once and the `Investigation:` footer unchanged. Requests
prove intent, not completion. Before replying:
check that the first line is one Markdown `# Title`, no diff prefix; no body
section still says `not investigated yet` (exclude the
`Investigation:` footer), and every private sentence, including the user's
own trips, ends with its label. Reply with files read and remaining questions.
