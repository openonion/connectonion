# REM product and design audit — 2026-10-01

REM is named for rapid eye movement sleep. Its product promise is to work while
the owner sleeps, consolidate permitted material into trustworthy memory,
connect relevant context, and help the owner remember and use it when awake.
This audit ranks the largest breaks in that loop. Rank reflects harm to that
promise, not implementation effort.

## Evidence and scope

The review covered the 1.9.0a10 reader's [home](../releases/assets/v1.9.0a10/home-desktop.png),
[People](../releases/assets/v1.9.0a10/people-desktop.png) and
[person on a phone](../releases/assets/v1.9.0a10/person-phone.png), plus the
[morning preview comparison](rem-morning-preview/REVIEW.md), reader code, and
the linked reports from real first runs. The screenshots use an invented
notebook; real-run issues describe their observations separately. This review
does not claim that a redesigned fixture proves real-world memory quality.

## Ten largest problems

| Rank | Problem and consequence | Evidence | Issue and next proof |
| --- | --- | --- | --- |
| 1 | **REM cannot distinguish new knowledge from a page rewrite.** The run log identifies a changed file, not the claim that changed. The preview labels it accurately as an updated page, so the morning brief cannot yet answer what REM learned overnight. | The first card of the [morning preview](rem-morning-preview/REVIEW.md) has only current page text. | [#2096](https://github.com/openonion/connectonion/issues/2096): preserve before/after claims and cited reasons; suppress semantic no-ops. |
| 2 | **The notebook contains too much noise.** Automated senders, duplicate people, and empty stubs bury the few relationships worth remembering. Better typography cannot rescue a polluted memory. | Real-run inventory in [#2057](https://github.com/openonion/connectonion/issues/2057); mapped-only rows in the People view. | [#2057](https://github.com/openonion/connectonion/issues/2057): enforce page eligibility and archive map-only junk without touching investigated pages. |
| 3 | **REM does not reliably know who “you” are.** Owner addresses and the owner's organisation can become other people or empty organisations, so connections and obligations become wrong. | Fresh first-run evidence in [#2078](https://github.com/openonion/connectonion/issues/2078). | [#2078](https://github.com/openonion/connectonion/issues/2078): fold or ask about owner identities before page creation. |
| 4 | **Context is filed, not legible as a map.** One explicit link in the preview is a start, but the owner cannot see how people, projects, conversations, and open threads move together. | [#2066](https://github.com/openonion/connectonion/issues/2066); the reader's category and article views. | [#2066](https://github.com/openonion/connectonion/issues/2066): evidence-backed relationship map and exact conversation history. |
| 5 | **The memory cannot be asked or acted on in the reader.** The offline snapshot exposes pages but has no source-backed answer, correction, or approved next action. | Current `co rem open` behaviour and [#2071](https://github.com/openonion/connectonion/issues/2071). | [#2071](https://github.com/openonion/connectonion/issues/2071): owner-only live read, cited answers, then approved actions. |
| 6 | **The owner is shown a memory but is not helped to retain it over time.** A reveal click has no durable state and cannot guide the next morning's prompt. | [Morning preview](rem-morning-preview/REVIEW.md). | [#2097](https://github.com/openonion/connectonion/issues/2097): explicit recall feedback and private, reversible scheduling. |
| 7 | **Corrections lack a complete memory lifecycle.** If an owner corrects REM, the correction needs provenance, temporal scope, and protection against old evidence reintroducing the mistake. | Open design and regression list in [#1611](https://github.com/openonion/connectonion/issues/1611). | [#1611](https://github.com/openonion/connectonion/issues/1611): human and agent reflections enter one reviewable update flow. |
| 8 | **The record pages still read as long Wiki articles.** On a phone, the essential state, evidence, history, and actions form a long vertical document; the page has no decisive “aha” about the relationship. | [Person phone screenshot](../releases/assets/v1.9.0a10/person-phone.png); [#2065](https://github.com/openonion/connectonion/issues/2065). | [#2065](https://github.com/openonion/connectonion/issues/2065): purpose-built person and project views, visual hierarchy, and before/after review. |
| 9 | **Retrieval follows the file cabinet, not the owner's question.** Category-first navigation and literal search help with known names but not “what changed”, “who needs me”, or “what connects to this project”. | [People screenshot](../releases/assets/v1.9.0a10/people-desktop.png); [#2098](https://github.com/openonion/connectonion/issues/2098). | [#2098](https://github.com/openonion/connectonion/issues/2098): task-based entry points with typed, explainable results. |
| 10 | **An overnight pass is not predictably bounded.** A first run exceeded its stated time and token estimate; a memory product cannot quietly consume the night and budget before it produces a useful morning. | Measured first-run report in [#2080](https://github.com/openonion/connectonion/issues/2080). | [#2080](https://github.com/openonion/connectonion/issues/2080): measured budget, reliable stop, and concise progress/partial-result states. |

## Release sequence and maturity bar

The [morning preview PR](https://github.com/openonion/connectonion/pull/2095)
is a first slice of ranks 1, 4, 6, and 8: it puts remembered context first,
shows an explicit link, offers a recall pause, and fixes one phone layout defect.
It does not close those issues. A later release can claim each fix only after
its issue's acceptance tests and a real notebook review pass.

REM is ready to be called mature when an owner can complete a first run without
identity duplication or junk pages; let a bounded night pass run; see verified
changes with sources the next morning; ask and correct the memory; retrieve the
right context for a task; and practice recall over several days. Those journeys
must work on desktop and phone, with empty, interrupted, and conflicting-data
states reviewed. Green fixture tests alone do not establish this bar.
