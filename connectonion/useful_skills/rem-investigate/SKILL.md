---
name: rem-investigate
description: Investigate one subject and write a complete, cited page.
---

# Investigate one subject

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

## Improve, do not append

Edit like code: add, change, delete. Delete what is superseded, said twice or
settled; longer is not better.

**Aim for about 15k characters.** Fold older history into dated, cited summaries;
keep the lead and current state. Growth beyond 20,000 characters is refused.
`History`: one dated line per thread, how it ended; at most sixteen.

## Quote or summarise

Someone's words the user may act on are quoted, not retold. A paraphrase of
an ask, a term or an instruction is where pages go wrong: “可以放在 Connect
页面上……我们自己再转发一下也可以” became "use the Connect company page" (a
misheard ConnectOnion, now a page name) plus a cost nobody stated.

- **Quote** (exact words, original language, with date and `[n]`): a request,
  offer or promise; a number, price, date or condition in someone's terms; a
  decision, correction or instruction the user gave; how someone says to reach
  them; a statement of who someone is; an opinion or preference; wording that
  is ambiguous or may be misheard. One or two whole sentences, `“…”`, never a
  cut fragment and never a changed word; a condition in the same sentence
  ("but before we publish…") stays in the quote; non-English stays as written, with a short English gloss after
  it if needed. A lead sentence may introduce a quote, never restate it.
- **Quote the line that carries the weight**: the condition, hedge, limit or
  amount ("only if paid by Friday", "I think", "not before March"), not a greeting, a
  sign-off or boilerplate around it. An amount is always on the page.
- **A quote belongs to its message.** The speaker is that message's `From`;
  cite that message, with its date. In a thread of three or more, check who
  wrote which line and in what order before "X confirmed" or "X offered". A
  mail to many recipients is a notice, not an ask of the user.
- **Summarise**: Facts fields, roles, dates, counts, routine sequence (who sent
  what when), and anything read from code, files or a git snapshot.
- **Inference is labelled and rests on quotes.** An `Insight`, a pattern or a
  cost is never written as a fact; one incident is not a pattern. Nothing the
  sources do not say: no added channel, item or month.
- **An old open item keeps its date.** "On 2026-08-02 the user said he would
  send the deck", never "owes the deck". A broadcast mail is not last contact.
- Before writing `Unknown` or "not established", search the sources you
  already cite.

## Filling the page

- `Unknown — not investigated yet`: find it in the material, or write bare
  `Unknown`. Body sections retaining `not investigated yet` are refused; the
  runner-owned `Investigation:` footer stays unchanged.
- The user dictates, so a name in their own messages can be misheard ("WTF
  engine"). Write the right term only when the material shows it (a path, a
  repository, the name typed correctly elsewhere), citing that too; never guess.
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

Edit the candidate in place with a local file tool: add, change and delete. Never edit the notebook, copy example facts,
or write other pages. Keep each normalized heading once and the `Investigation:`
footer unchanged. Requests prove intent, not completion. Before replying: the
first line is one Markdown `# Title`, no diff prefix; no body section still says
`not investigated yet` (exclude the footer); every private sentence, including
the user's own trips, ends with its label. Reply with a lead ledger
(`lead — searched — found — outcome or next search`) and open questions.
