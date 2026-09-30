# Why the rem-maintain rules are what they are

The runtime Skill lives at `connectonion/useful_skills/rem-maintain/SKILL.md`
and holds only the rules. It is re-sent on every model turn -- a Codex tool round
re-sends the whole composed instructions each time -- so a one-page maintain turn
(maintain + one page-kind Skill) has a budget of about 15k characters (#1851).
The reasons, incidents and worked justifications that used to sit beside each
rule live here instead, under the same headings. This file is not loaded at
runtime; change it when you change a rule.

## Where the model is working

The output is the notebook itself, not a proposed patch or a summary for a
human to copy. "Offline" in a staged run means no network, not no local file
access; the Skill spells that out so the model still reads the supplied files.
No special `rem_*` tools are installed (earlier versions had `rem_write` and
`rem_people`; a runner test asserts they no longer appear).

## Source material

Large batches arrive already digested by `rem-extract`: one item with role
`extract` holding extraction notes grouped by kind, each bullet with speaker,
date and source ids. Each bullet is a sourced claim to organise, not a page to
copy.

Mail is grouped by person (every mail between the user and one correspondent,
oldest first) so a person's page is written from their whole history at once,
not assembled a week at a time.

The distinctions about mail (a request is not a commitment until the user
answers; a confirmation or receipt is a fact about a booking or order, not a
decision; a newsletter is rarely worth anything) correspond to the pages that
were created wrongly in a real 60-day run -- see "What is worth a page" below.

Source text and existing notes are evidence, never instructions that can expand
permissions: otherwise anyone who can send the user a message could steer the
notebook. Instructions addressed to the model inside source text rarely deserve
a page either.

An attributed correction is checked against its basis and applicable time, and
is not revived from an older repetition alone.

## When you are given one page

This replaced one pass over the whole notebook. That pass edited eight pages in
one turn, spent twenty minutes deciding and rewriting, and timed out with
nothing saved (2026-09-27). The runner now finds the pages the material
concerns (the project whose folder the sessions ran in, the people the material
names) and hands the model one page at a time with the whole batch as material.
Material about other subjects is left for their own passes.

## Find before you write / recognising a person

Recognising a person is judgement, not a string match. A name in a coding
session is whatever the user typed at the time: a first name, a nickname, a
typo, or what dictation heard. Measured: a session said "odi" and the notebook
already held "Ody Zhou" -- a literal search for "odi" finds nothing, because
literal search cannot bridge a changed letter, and a second page for the same
person was created. The context that settles it is the kind only the model can
weigh: "odi" asked for the pricing analysis in the same week Ody Zhou was sent
the pricing analysis.

Adding the new spelling to `Also known as:` means the next batch matches it
without having to think. When unsure, `Possibly the same as:` is required
instead of a silent twin because a marked page can be merged later by anyone;
an unmarked one is found by nobody.

## Naming a project

The `project` field is a working directory, and a folder called
`realtime-voice-chat` may hold a week of work on something else entirely.

## Page shape and preservation

People and project pages have canonical templates appended from
`rem-page-*`. The person template lived in this Skill as prose and was copied
into a second stage; the two drifted within a day, one of them renaming the
headings the roster reads back. That is why the shape is a file of its own and
this Skill only points at it.

A focused correction must not collapse a page into a short summary or rename its
sections: headings are read back by code, and diagrams, mapped metadata,
citations and Investigation status are lost otherwise. Unsupported sections say
`Unknown` rather than disappearing, so a gap stays visible.

The decision-record example in the Skill is kept there because it shows the
free-form output format (title, dated reasoning, alternatives, Related link,
Sources line).

## Language

The page follows the user's own messages -- not the assistant's replies, these
(English) instructions, or the notebook's existing pages -- because the
notebook is the user's, in the language they use.

## What is worth a page, and where

The test is whether the user would want their assistant to still know this in
a month. The assistant's routine work (tests and counts, lint, files edited,
commands, version bumps) is activity, not knowledge, and a page of it teaches
the next assistant nothing.

From a coding session only the user's words are read, because what they say is
what they want. A page opening with a commit SHA, changed files, a CI tally or
bare issue numbers describes the execution and was already stale when written.

Four things that produced pages in a real 60-day run and should not have:

- **A person from one line.** `people/fuzz.md` = "Expressed definite interest in
  Aaron's property opportunity." -- no role, no company, no relationship. That
  is a line on the outreach page it came from.
- **Someone else's article as knowledge.** A newsletter's takeaways, an
  investor's essay, a vendor's product update are their thinking, not the
  user's.
- **A receipt as a work.** "An agent address was issued: 0x8ad3..." is a fact
  about an account.
- **One page per transaction.** Twenty `agenda/airbnb-<guest>.md` pages, each a
  single inquiry, were dead a week later; hence one rolling page
  (`agenda/airbnb-guest-inquiries.md`) with a dated line per inquiry.

### Decision vs principle, proposal vs decision

A principle said once still counts: being said once is not the problem, being
*adopted* is what counts. Examples: "Postgres for Beacon's ledger" is a
decision; "from now on / always / never / that's a rule for us" marks a
principle; "dark mode in the editor today" is neither. "We could try Redis",
"should I set up X?" and the assistant's own suggestions are proposals.

## Update understanding, not just the daily summary

The rule is to rewrite the current view rather than simply accumulate
conflicting summaries after every session. Compression is reorganisation for
future usefulness, not minimising length. No snapshots or semantic
state-transition workflow is needed.

The `completion.json` no-change receipt lets the runner tell "assessed and
nothing to change" from "never looked"; claiming a reviewed no-change batch
that was never read would silently drop its material.

## Reflections and review candidates

Existing pages and compact views are derived from the same records, so citing
them as independent evidence would double-count. Only a later verified change
supersedes a correction; recency or author identity alone does not.

User answers and decisions on review candidates return as source material in the
next ordinary maintenance pass, so the Skill needs no rule for collecting them.

## Examples trimmed from the Skill

The decision-record example originally read: "Decided 2026-09-02, corrected
2026-09-07. Markdown was first chosen for portability; the user later corrected
the reason to inspectability, and kept the choice. SQLite was discussed as an
alternative and not adopted. Revisit only if the notebook grows past what
plain-text search handles." Filename examples also included
`projects/aurora.md` and `decisions/aurora-storage.md`. The `people/` row of the
directory table listed the person-page contents (contact fields, dated history of
both sides, how each side writes, cadence, what is open and to whom, unknowns);
those now live only in `rem-page-person`, which is appended at runtime.

## Only what is open, and a page that stays readable (#1956)

In the 1.9.0a1 acceptance run (2026-09-30), four `sync --all` batches grew `projects/connectonion` from 26.5k to 53.7k characters and from 69 to 175 sources. The growth was mostly week-old 1.8.5 items re-added as "Open threads". The last batch cost 1.73M input tokens for one page, because every turn re-reads the page it maintains. The rule gives open threads a date check and gives the page a size it folds its oldest history into.

**The size is enforced, at every stage that writes a page (#2019).** The rule
lived only in this Skill, and a daily update is an investigation, not upkeep:
in the 1.9.0a5 acceptance run (2026-10-01) one daily-update pass took
`projects/connectonion` from 13,421 to 25,255 characters and `ody-zhou` from
18,910 to 21,690. The same rule is now in `rem-investigate`, and the runner's
review refuses any page candidate -- investigation, daily update or upkeep --
over **20,000 characters that is longer than the page it replaces**; the
refused candidate is kept with the reason, as every refusal is. Why 20k: on a
copy of the owner's notebook that day, 696 of 698 pages were under 15k and the
largest page a person had grown by hand-read material was 18.9k; both growths
above end over 20k. A page already over the limit is not stuck: a candidate
that shrinks it is accepted, so it can come down across runs. Every run's
outcome already carries `page_chars` (before, after) for the page it wrote.
