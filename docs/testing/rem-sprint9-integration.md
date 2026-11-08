# Sprint 9 ordered integration

Fixture-only integration on the new Mac, starting from `ce727ddc` on
`release/1.9.3rc60`. No owner notebook used; no push.

## Ordered merge decisions

1. `sprint9/people-person` (`0f363a42`): reader merged automatically. Browser
   test append conflict resolved by retaining rc60 task receipt/deliverable
   cases and all new person/People cases. Shared unit JavaScript harness uses
   personSub/personOrg/personProject for the new layout and retains taskResult
   for rc60 task cards; contactLine was removed by the intentional redesign.
   Independent AI source review caught a prepared-draft CTA pointing at Today;
   repaired using the existing review card and its live/static/privacy guards.

## Verification

Each merge runs Node syntax checks for every reader script block and the
complete unit command requested by the owner. Logs are retained outside pytest
basetemp; basetemp is removed after each complete suite. Browser full suite
will be invoked once with two workers after all six merges.

### Initial environment and coverage repairs

Initial full unit run: `6 failed, 18512 passed, 19 skipped, 2944 warnings in 137.17s (0:02:17)`.
The merge's lazy startup harness lacked `peopleMode`, `notDoneKeys` and
`notDoneStorageKey`; its fixture now represents the new storage state.
Four terminal color failures came from inherited `TERM=dumb`; SIGHUP shutdown
failed because this harness inherits `SIG_IGN` for SIGHUP. Later suite launches
use `TERM=xterm-256color` and restore default SIGHUP before executing the exact
requested uv/pytest arguments. No product or test assertions changed for those
five environment failures. Focused ordinary-terminal recheck: 93 passed, with
only the ignored-SIGHUP case still failing before signal normalization.

The empty-between-you and person-lead browser cases retain their original names
with the new owed-card/full-memory assertions. Removed person-lead punctuation
and privacy cases and active/old/no-index metric cases were restored in
`test_rem_person_integration.py` against current rendered paths. The existing
no-reply reason coverage remains, and a new primary-action regression prevents
asking for another reply where the draft explicitly says none is needed.

2. `sprint9/projects-sessions` (`43d132e7`): reader CSS append conflict
   retained both scoped style blocks; browser append conflict retained rc60
   task-card cases, People/person additions and every Projects/Sessions case.
   Branch versions of Sessions selectors follow the day-grouped list and four
   tabs; obsolete picker/topic-chip assertions become bookmarked-filter
   assertions. Retained a separate desktop/phone calendar/project/day-group
   case, including month filtering and touch target/overflow checks.

People/person final complete unit run: `18530 passed, 19 skipped, 2944 warnings in 148.90s (0:02:28)`.
The additional Skip-dialog lifecycle repair passed the focused 19-case run.

Projects/Sessions complete unit run: `18532 passed, 19 skipped, 2944 warnings in 139.87s (0:02:19)`.

3. `sprint9/org-data` (`bc8437a8`): no conflicts. Retained rc60 CLI changes
   and added structured organisation fields, membership/project links,
   obligations, diagnostics, fixtures and all data tests.

Organisation data integration also resolves Company wikilinks on People/person
surfaces through explicit snapshot affiliations, preserving page-written
Markdown and translated labels. Added four fictional label/destination cases.
Protected rc60 Today/approval/task-card functions remain byte-for-byte identical
to `ce727ddc` (including overview, queueCard, taskResult, primaryAction,
threadActions, replyDraftCard, openWriter and all approval helpers).

Organisation data complete unit run: `18554 passed, 19 skipped, 2944 warnings in 132.12s (0:02:12)`;
focused org-data/person compatibility: `38 passed in 1.11s`.

4. `sprint9/org-ui` (`c902ddc1`): reader conflicts combined category routes,
   Projects board and org insertion blocks, and People/person plus org record
   layouts (including private-org early return). Restored the board function
   closing brace shared by the insertion conflict. Browser append conflicts
   retain every rc60/task/People/Projects/Sessions/org case and restore the org
   list test's shared width/theme decorators. Renamed only org-region
   firstName/byUrgency/owedRow to orgFirstName/orgByUrgency/orgOwedRow, preventing
   function-hoisting overrides of People behavior. Org primary actions retain
   Mark done labels for replied/no-reply items; added three semantic action
   regressions. Domain metadata and last-night markers remain visible in the
   new row/header design; the original domain test now uses those selectors.

Org UI complete unit run: `18562 passed, 19 skipped, 2944 warnings in 134.13s (0:02:14)`.
Separate AI review caught same-name private/public aggregate leakage; org rows
now keep hidden pages outside public aggregates until revealed. Org Chinese
wording is scoped through orgT instead of overwriting global Today/People
translations. Added visibility-boundary and translation-isolation regressions;
focused complete reader/person/org recheck follows these repairs.
