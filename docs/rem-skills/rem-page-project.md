# Why rem-page-project says what it says

The rules live in `connectonion/useful_skills/rem-page-project/SKILL.md`,
composed into every model turn that writes a project page. This file holds the
reasons behind them; it is not loaded at runtime (#1851). Almost all of that
Skill is rules, so little moved here.

## The input is the page and bounded material

Measured on real runs, searching for example pages, earlier outputs, logs,
other skills or repository files to copy a format from, not the writing, used
up the turns, and the page was never written. The runner now gathers a small
repository packet first, so the model can compare a request with a README,
package version, checkout ref and recent commits without an unbounded search.
A commit is not evidence of passing tests or deployment. The Skill still says
write once, check once, fix once.

## The first-time reader

This remains a project page, not a separately named onboarding page. Reading it
through the eyes of someone new to the project is a design test for the page,
not a second page to maintain.

## Core and optional headings

Mapping (`stub_project`) creates the complete unfinished skeleton. A written
page keeps core headings and supported detail; it omits optional headings
that would only say `Unknown`. Names and order still come from one shape;
`tests/unit/test_rem_instructions.py::test_project_and_skill_templates_match_created_skeletons`
compares every `## ` line in the Skill with the mapped skeleton. That is why
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
unknown flow stays absent rather than being drawn.

## `Key decisions`

Current behaviour is easy to restate as if someone had chosen it. A rationale
caveat does not turn observed behaviour into a recorded choice; only a source
that records the choice does.

## Coding transcripts

User-only coding transcripts record what the user wanted. The separately
cited repository packet can establish project identity, manifest version and
local commits. Neither source alone proves a public release or passing test.

## An insight must change the next decision

An isolated real five-day candidate run produced a shorter, cited project
page, but its lead still restated the owner's latest request. A second bullet
listed another request and a third warned that the checkout was stale. The
packet had repository evidence, yet none of those bullets joined it to the
owner's question. The page was accurate but offered no new decision. The writer
now reads the repository packet first and uses a relevant cross-source
comparison in the lead when evidence permits one. If the sources do not
establish an outcome, it says what to verify instead of implying success or
failure from a commit title.

## Mapped `Paths` fields

`Sessions`, `First seen` and `Last seen` are window-scoped counts and dates
that belong to mapping. The risk is investigation dropping them while expanding
the prose, or substituting the investigation date for mapping's dates.
