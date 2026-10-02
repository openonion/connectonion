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

CI/SEO requests also select at most two tracked workflow files, prioritizing
matching filenames within the same 9,000-character text budget. All Git reads
use one resolved commit SHA. This gathers configuration, without executing a
workflow or inferring the result of a run.

Accepted session-writer pages retain the cited repository packets privately
under `.state/project-sources`, keyed by a hash of origin and exact bounded
text. The reader uses that captured text rather than reopening a changed file
or mutable Git ref. Capture time is separate from event time. Existing pages
whose packets were never retained cannot recover historical evidence from a
new checkout. File-only investigation now also snapshots supplied files and
checkout state before digesting or arranging temporary evidence. It retains
only accepted, cited originals under the recording lock, then refreshes the
reader. Extra files discovered outside the supplied inventory have no
automatic historical capture; current files never substitute for old citations.

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

A recovered historical project page joined a slow-crawler request with a later
1,000-property target but cited only the first message. Both messages existed;
source-id validation could not establish that each clause was supported. The
instruction now requires checking inherited numbers, dates and joined clauses
against their original sources. A generic live rereview still retained the old
error, so the observed page was corrected against both messages; that manual
correction does not prove the model reliably follows the instruction. With user-only material it also preserves precise operating scope,
such as a branch exclusion versus an organization-wide exclusion, so the lead
offers a decision instead of several unverified completion questions.

## Mapped `Paths` fields

`Sessions`, `First seen` and `Last seen` are window-scoped counts and dates
that belong to mapping. The risk is investigation dropping them while expanding
the prose, or substituting the investigation date for mapping's dates.

## Project scope and pending work

An actual documentation page cited a merge reminder for a remote-browser
architecture discussion and an adjacent framework-status input for an SEO
proposal. All IDs existed: identity-safe retrieval did not validate the claims.
The lead also adopted a backend GPU/model request from the same workspace as
the site's latest progress. Each claim must be checked against its exact input
and actual subject, including inherited content; cwd and tool attribution only
explain where material was found.

The previous session rule put a request in `Open threads` whenever no later
input said it was complete. User-only archives omit replies and results, so
that rule converted missing evidence into a current task. Only confirmed
pending status belongs there. Requirements can still yield useful findings:
for example, repeated rendered-code checks followed by proposed publication
checks reveal a concrete quality need without claiming CI was implemented.

An explicit `Facts` activity date is included in the shared census; mapped
`Last seen` remains its original mapping window, not a replacement for later
supported activity. Writers must exclude unrelated workspace topics from that
date. Reader and CLI counts use the same census, without file modification time.
The reader labels the mapping count `Mapped sessions` to distinguish it from
the fuller archived input coverage used during investigation.
