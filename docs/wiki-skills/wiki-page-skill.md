# Why wiki-page-skill says what it says

The rules live in `connectonion/useful_skills/wiki-page-skill/SKILL.md`,
composed into every model turn that writes an installed skill's page. This file
holds the reasons behind them; it is not loaded at runtime (#1851). Almost all
of that Skill is rules, so little moved here.

## The first-time reader

This remains a skill page. The reader without company or technical context is a
design test for the opening, not a separate onboarding page.

## Exact headings

Mapping (`stub_skill`) and later evidence review use the same structure.
`tests/unit/test_wiki_instructions.py::test_project_and_skill_templates_match_created_skeletons`
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

`co wiki investigate skills/catalog/<page>.md` reads retained co eval summaries
without a model or mail. It matches explicit slash-command names, so a
tool-based invocation or another harness's run is not seen, and a summary
record says nothing about which source version ran or whether the goal was
achieved.
