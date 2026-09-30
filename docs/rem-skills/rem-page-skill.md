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
without a model or mail. It matches explicit slash-command names, so a
tool-based invocation or another harness's run is not seen, and a summary
record says nothing about which source version ran or whether the goal was
achieved.

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
