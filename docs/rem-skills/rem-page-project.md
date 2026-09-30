# Why rem-page-project says what it says

The rules live in `connectonion/useful_skills/rem-page-project/SKILL.md`,
composed into every model turn that writes a project page. This file holds the
reasons behind them; it is not loaded at runtime (#1851). Almost all of that
Skill is rules, so little moved here.

## The input is the page and the material

Measured on real runs, searching for example pages, earlier outputs, logs,
other skills or repository files to copy a format from, not the writing, used
up the turns, and the page was never written. Polishing line by line spends the
turns the page needed, which is why the Skill says write once, check once, fix
in one edit.

## The first-time reader

This remains a project page, not a separately named onboarding page. Reading it
through the eyes of someone new to the project is a design test for the page,
not a second page to maintain.

## Exact headings

Mapping (`stub_project`) creates the skeleton and investigation fills it. Both
share one structure only if the headings match exactly;
`tests/unit/test_rem_instructions.py::test_project_and_skill_templates_match_created_skeletons`
compares every `## ` line in the Skill with the created skeleton. That is why
the Skill uses bold labels, not `##` headings, for its own subsections.

## `What it is` is the product; `Where it stands` is now

On the 1.9.0a2 notebook the connectonion page's `What it is` described co rem,
the thread most sessions were about that month, not the repository's product;
and `Where it stands` ran to 11 bullets of history (#1974). The most-discussed
thread is a fact about the user's month, not about the project, so it goes in
`Open threads`. `Where it stands` is 3–5 bullets because a snapshot that
needs more is a log, and the log already has homes (`Key decisions`,
`Latest issues`).

## The opening stays short

Every caveat and link in the introduction buries the one sentence, diagram and
entry point a newcomer needs. A plausible diagram is not evidence, so an
unknown flow stays Unknown rather than being drawn.

## `Key decisions`

Current behaviour is easy to restate as if someone had chosen it. A rationale
caveat does not turn observed behaviour into a recorded choice; only a source
that records the choice does.

## Coding transcripts

User-only coding transcripts record what the user wanted, not what the
repository or tests ended up doing.

## Mapped `Paths` fields

`Sessions`, `First seen` and `Last seen` are window-scoped counts and dates
that belong to mapping. The risk is investigation dropping them while expanding
the prose, or substituting the investigation date for mapping's dates.
