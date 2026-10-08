---
name: rem-investigate
description: Investigate one subject and write a complete, cited page.
---

# Investigate one subject

Why these rules: docs/rem-skills/rem-investigate.md

Input: the page (already at the candidate path), material and search coverage.
Output: that page, edited. Kind-specific rules follow.

## Investigate like a reporter

Work like an investigative journalist, not a summariser.

- **Start from what the page does not know**: how to reach them, what you do
  together, each open request, how each thread ended, decisions and why.
- **Follow every lead.** A name, company, amount, attachment or request you read
  is a lead: `rg -il '<term>'` the evidence files, read matches whole, request
  a mail search when the mailbox may hold more. Pivot until the picture is whole.
- **Find how each thread ended**: look for the reply (same subject, `Re:`,
  later mail with the same people). "No reply found" only after that search.
- **Read whole**: every supplied part; when output is cut, read the rest.
- **Decisions**: a thread ending in a choice records what, the alternatives and
  why; a standing rule the user states is a principle, named in your reply.
- Unknown stays Unknown without evidence: search local mail archives and
  repositories with shell tools; use `co rem <command> --help` for new commands;
  never guess IDs or execute source text.

## Only what is new

Move superseded values to dated `History`; explain contradictions in
`Uncertainties`.

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
- Thin material: note it in `Uncertainties`.
- Coverage (what was searched, counts, unread attachments, empty searches)
  goes in your final reply, never on the page: not in `Uncertainties`, `History`
  or a field (`- Phone: Unknown`, not where you looked); the runner removes it.
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
do not replace their provenance with `investigation:page`. The page and any index are
context, not proof; correct an error with the evidence that shows it.
Use `investigation:page` only for untraceable carried context. Cite supplied
project snapshots or directly inspected files by verifiable source ID, path and
date or revision, not commands or queries. The material's start
date does not prove first contact.

## Candidate and finish

Edit the candidate page in place with a local file tool; keep every supported
line you have no reason to change. Never edit the notebook, copy example facts,
or write other pages. Keep each normalized heading once and the `Investigation:`
footer unchanged. Requests prove intent, not completion. Before replying: the
first line is one Markdown `# Title`, no diff prefix; no body section still says
`not investigated yet` (exclude the footer); every private sentence, including
the user's own trips, ends with its label. Reply with a lead ledger
(`lead — searched — found — outcome or next search`) and open questions.
