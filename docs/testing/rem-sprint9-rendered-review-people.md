# Independent AI rendered review: People, person, Today

AI engineering reviewer using a marketing/UI technology-founder perspective; not a real human founder review. Fixture notebook only. Viewed twelve actual PNGs from `/tmp/rem-sprint-review/inventory.json`, not merely source or DOM text. This is sampled coverage, not an all-page pass.

## Actual pages and states viewed

For each of `people`, `person`, `today`, viewed `{view}-1440-light.png`, `{view}-1440-dark.png`, `{view}-390-light.png`, `{view}-390-dark.png`.

- People: default rows mode, five people, two waiting, Inès focal action, All/People waiting tabs, filter, Table toggle, recent group, collapsed other-contacts directory.
- Person: Mara detail with two open obligations in opposite directions, original-source date links, exchanges timeline, contact/organisation/unit rail, unit-scoped Pilot lead role, uncertainty notes, collapsed Full memory and sources.
- Today: snapshot mode, zero approval outcomes, four Needs you cards, first card expanded and remaining More controls, overnight role change, collapsed recall context/rewritten-pages/maintenance sections.

Inventory reports zero page errors and zero horizontal overflow for these captures; visual inspection agrees. No modal, Table mode, empty-filter result, done/undo state, expanded Full memory, private reveal state, or live send/approve state was visually reviewed in this round. Existing browser checks cover several of those flows separately.

## Significant findings

### P2: empty snapshot approval CTA still has primary emphasis

Evidence: all four Today PNGs show bright green `Approve all 0` above Needs you and a terminal-command hint, although the capture has no approval outcomes. `approvalHeader()` confirms the control is disabled when not live or no items. The visual styling gives a disabled empty action stronger emphasis than the real waiting work.

Impact: a returning reader's first apparent action is unavailable and affects zero items. This predates the sprint-owned People/org regions and is not evidence of a merge failure.

Recheck criterion: zero-outcome and snapshot states should communicate the unavailable approval action without the enabled primary-action appearance; a nonempty live state must retain its reviewable primary approval action. Reported to root before any edit; no edit made by reviewer.

### Cross-provider badge/action ambiguity, fixture-limited

Evidence: Mara's Today card shows an Outlook reply badge with an Open the Gmail thread action and Gmail archive-unavailable explanation, in all four Today captures.

Source check: the invented notebook combines older Outlook citations and a newest Gmail message under the same `mail:fixture:harbour-renewal` thread. `threadKind()` follows the cited original; the action follows queue reply metadata. Therefore this is a confirmed visible ambiguity in the fixture but not a proven integration defect. Do not silently rewrite provider semantics based on this screenshot alone.

Recheck criterion: a fixture with a single-provider thread should show consistent badge/action/explanation; any supported cross-provider conversation should distinguish original source from the active reply destination. No product change made.

## People/person assessment

No blocking visual issue found in the eight People/person captures. The People page communicates who needs attention, offers one focal next step, and keeps list/filter/table navigation visible at both widths. Person detail keeps identity, organisation, next action, reciprocal obligations and evidence above the long history; phone layout moves the supporting rail below history without sideways overflow. Both themes preserve readable hierarchy and clear primary actions. Unit membership and scoped Pilot lead role appear in the person rail. Original obligation source dates are visible, and Full memory remains explicitly disclosed.

The People focal summary is truncated on desktop and the row summaries are clipped by design; the focal full-width phone action and person destination preserve the next step. These are not significant defects in the sampled states.
