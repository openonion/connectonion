# Rendered REM Sprint 9 review — AI reviewer

Reviewed from the perspective of a marketing/UI technology founder. This is an independent AI role review, not a human founder review. Invented fixture notebook only; no owner notebook was available or read.

## Actual coverage

Inspected these 20 rendered images, including full-page content, at desktop 1440×900 and phone 390×844, each in light and dark:

- Organisations list, `#c=orgs`: focal next action, counts, search, tabs, waiting rows.
- Fernhill Labs, `#r=orgs%2Ffernhill-labs.md`: relationship, owed rows, quiet waiting-on-them line, department→team→person tree, history, related project, collapsed Full memory.
- Pilot squad, `#r=orgs%2Fpilot-squad.md`: team-kind subtitle, rolled-up owed item and person, uncertainty rail, history, collapsed Full memory.
- Projects, `#c=projects`: lifted active Harbour card, session count, one primary, desktop three lanes, phone single selected lane, mapped Lantern card.
- Agent sessions, `#c=sessions`: unfinished session with resume action/follow-up, search, agent/outcome tabs, Today/Yesterday/dated groups, completed rows.

Images and inventory: `/tmp/rem-sprint-review`. The separate reviewer covers Today/People/person. This is sample-state review, not an all-page or all-interaction pass. Captures do not test sending, live approval, private-org reveal, search interactions, or session continuation execution; those remain browser-suite responsibilities.

## Significant findings and rendered recheck

| Priority | Issue and user impact | Evidence | Fix and recheck criteria |
| --- | --- | --- | --- |
| P2, fixed | Explicit nested units occupied one grid column, leaving most of the page unused and truncating the only person's name to “Mara O…” on phone. Reader could not confidently identify the member in the tree. | Initial `organisation-390-light.png` and dark counterpart showed Research and delivery/Pilot squad in a narrow half-width card; desktop also wasted width. | Added `.ov-teams:has(.ov-child-units) { grid-template-columns: minmax(0, 1fr); }` after mobile overrides. Flat free-text Team grids retain their layout. Recaptured and inspected organisation desktop/phone in both themes: “Mara Ostrowski” and “Pilot lead” now fully readable, nested structure clear, no overflow. |
| P2, fixed by root | Known unit `unit_kind=team` nevertheless asked “What kind of organisation this is,” contradicting its visible subtitle and hierarchy. | Initial Pilot squad images in all four viewport/theme combinations. | Root changed unknown-kind condition to require both missing `kind` and missing `unit_kind`, with scoped unit regression. Recaptured and inspected all four unit images: false unknown-kind prompt absent; genuinely unknown “What it is to you” prompt remains. |

No unresolved P1/P2 issue was found in these reviewed states after recheck.

## Nonblocking follow-ups

- Organisation count includes explicit department/team pages: the fixture shows “3 organisations · 3 waiting on you” for one company and its two units sharing the same rolled-up ask. This is current data/list scope, not evidence of lost obligations; product wording could later clarify “organisations and units.” Recheck with several companies and nested units before changing count semantics.
- English singular copy says “1 people you know,” “1 things you owe,” and “1 sources.” This is polish; values and actions are understandable. Recheck singular/plural labels when copy is next revised.
- Project hero says “Newest: 6 days ago” for its newest open item while also showing three recent coding sessions. The surrounding line is truncated on phone. A later copy pass could clarify “Latest open item.” Its active project is deliberately lifted out of lanes, so the page can say one active project while This week lane displays zero remaining cards.
- Unit detail breadcrumb returns to Organisations rather than showing the explicit parent path. Parent still exists in Full memory and the company page tree; adding a parent breadcrumb would improve orientation in larger hierarchies.

## Final capture evidence

The capture script completed with:

```json
{"directory": "/tmp/rem-sprint-review", "screenshots": 32, "pageerrors": [], "overflow": []}
```

The final inventory retains all 32 captures (8 routes × 2 widths × 2 themes). All four final unit texts omit the incorrect unknown-kind prompt. The eight hierarchy images were visually inspected again after fixes. No full test suite was run by this reviewer during capture/review.
