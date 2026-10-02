# Why rem-page-skill says what it says

The rules live in `connectonion/useful_skills/rem-page-skill/SKILL.md`,
composed into every model turn that writes an installed skill's page. This file
holds the reasons behind them; it is not loaded at runtime (#1851). Almost all
of that Skill is rules, so little moved here.

## The first-time reader

This remains a skill page. The reader without company or technical context is a
design test for the opening, not a separate onboarding page.

## Exact headings

Mapping (`stub_skill`) and later evidence review use the same structure.
`tests/unit/test_rem_instructions.py::test_project_and_skill_templates_match_created_skeletons`
compares every `## ` line in the Skill with the created skeleton, which is why
the Skill's own subsections are bold labels, not `##` headings.

## Exit status, completion and quality are separate

A process can exit cleanly without producing the requested artifact, and an
artifact can exist without anyone having checked it. Folding the three into one
"success" is how a performance section comes to overstate a skill.

## Unknown is not zero

When no run records are available, a 0% completion rate or "never executed"
would be a claim the evidence does not make. Missing logs are a coverage gap.

## No complete-looking dashboard

Keeping gaps visible in `Uncertainties` is preferred over filling every metric,
because a filled-in dashboard reads as verified whether or not it is.

## Why the eval collector is limited

`co rem investigate skills/catalog/<page>.md` reads retained co eval summaries
before the model reviews the source and retained records; it never reads mail
or executes the skill. The eval collector matches explicit slash-command names.
The map's invocation cache also identifies recent matching Codex and Claude
turns: the review can search raw requests, tool results and replies for up to
three latest invocations. The supplied index states sample size, matched count
and missing files. Neither path establishes which installed version ran or
independently verifies an artifact or achieved goal.

## One page per name, the source linked (#1974)

On the owner's notebook in September 2026 the catalog held 420 pages for 163
skill names: one per installed copy, including copies inside temporary git
worktrees and `site-packages`, and 409 of them pasted the whole `SKILL.md` (one
page ran to 1,530 lines). A reader looking for "what is ship-feature and do I
use it" found three near-identical copies of its instructions and no answer.

So the map makes one page per name. Copies are compared by content hash and
listed in the map-owned `Source` block, where a drifted copy says it differs;
that is the evidence that links copies, so the Skill no longer says to keep them
distinct. A temporary or package copy is listed but never the page's `File`,
because it disappears or changes with the next checkout or upgrade. The source is
linked, not pasted: the page is for deciding whether to use the skill, and the
instructions are one click away.

## Usage is counted by a script

How often and when a skill was last invoked is a count, not a judgement, so the
map takes it from the session transcripts without a model: `Skill` tool calls
and `/name` commands in Claude Code, `$name` in a typed Codex message and a tool
call reading the skill's `SKILL.md`, once per turn. It is stated as invocations,
never as runs completed, because nothing in a transcript line says the task
succeeded.

## Merging never deletes

Pages from before are folded into the name's page by the map: written lines are
merged section by section, the old page is moved to `.state/archived/`, and its
record stays resolvable as an alias. The same mechanism merges a repository's
split project pages.

## A useful first page

Init investigates installed skills alongside people, projects and organizations.
The opening connects source instructions to a concrete starting point and a
cited finding that changes the reader's choice. A source-only review can explain
the required output and its verification step, while keeping execution
unverified. Optional Unknown-only sections disappear from investigated pages;
source provenance and observed invocation counts remain available.

Large text eval records and invocation turns are split into 40,000-character
pieces for file tools. Each new piece has an identity derived from its origin
and exact supplied body before digesting or arranging the evidence. Only cited
pieces from accepted changed pages persist in private state under the result
recording lock. Unchanged, refused and failed results do not accumulate bodies.
Original record time and capture time remain separate; a coverage summary has
no invented execution timestamp.

The reader shows a 640-character prefix, with truncation and record scope.
It never reopens today's mutable log to replace a lost old citation. Legacy
identifiers without retained body hashes remain unavailable; a newly inspected
capture is new evidence, not recovery of the old supplied packet. Identity and
source access do not validate the attached claim.

Invocation context contains public text, tool reports and final replies.
Provider thinking, analysis-channel messages and binary image attachments are
omitted; an image marker explicitly says it was not visually reviewed. A
screenshot path or assistant report is not visual proof. Any separate inspection
of an archived image must be described with its actual scope.

The skill reader opens on the first Insight line when available, with the usage
explanation in the full note. Recheck inherited claims against their exact task,
date and original result: adjacent runs can have different counts, failures and
outcomes. A manually corrected page does not demonstrate that the model will
reliably make the same correction.
