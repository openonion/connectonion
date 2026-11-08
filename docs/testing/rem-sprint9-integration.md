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

Org UI final scoped recheck: `322 passed in 11.13s`.

5. `sprint9/org-hierarchy` (`3a0f4e9f`): no textual conflicts (runner merged
   automatically). Bound the org UI's existing tree seam to validated Parent
   children, explicit person Unit edges/roles and recursive unit cards. Root
   rosters include descendants once; obligation/person rollups deduplicate by
   identity. Old free-text Team remains a flat grouping and does not invent a
   linked unit. Same-name units stay distinct by path. Hidden child units, their
   members and scoped obligations stay outside public parent aggregates.
   Person rails show validated unit/role links. Added three unit integration
   cases plus desktop/phone light/dark nested navigation browser cases.
   Focused hierarchy/data/UI verification: `71 passed in 1.28s`.

Independent AI hierarchy review additionally found inherited private-unit
visibility and explicit dual membership edge cases. Hidden ancestors now hide
their descendant obligations; explicit memberships at both parent and child
retain their separate roles while rollup people still count once. Added focused
regressions for both. Unit names in organisation obligations use resolved
labels instead of exposing raw Unit wikilink syntax.

Hierarchy complete unit run: `18613 passed, 19 skipped, 2944 warnings in 135.08s (0:02:15)`;
final focused edge-case recheck: `73 passed in 1.43s`.

6. `sprint9/project-data` (`aaa4a5a6`): shared reader unit-test append
   conflict retained both person owed/reply/no-reply tests and all project
   metadata-scan/session-mention performance and Unicode cases. Snapshot
   enrichment merged automatically after org structure and before Today queue,
   with hierarchy obligation rollups retained afterward. No older person
   selector harness replaced the current one.

Closed the remaining AI-review evidence-navigation issue: person owed items
again expose their own cited originals through the existing evidence panel.
Citation numbers retain the obligation origin page's namespace and private
passages do not contribute source affordances. Added a focused privacy/source
identity regression and a real-browser evidence-panel case. Existing Looks
done assertions keep their exact behavior; only the isolated inline renderer
seam was added to that test's JS fixture.

Project-data complete unit run: `18677 passed, 19 skipped, 2944 warnings in 133.88s (0:02:13)`;
project/reader/person/org focused validation: `382 passed in 11.03s`.
The final hierarchy composition recheck also covers a parent unit's own page:
its direct member is rendered in the known unit with the parent-specific role,
while child membership and role remain independently visible.

## Full browser command (one invocation)

```sh
CO_REM_BROWSER_TEST=1 uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/e2e/cli/test_rem_reader_design_browser.py tests/e2e/cli/test_rem_reader_browser.py tests/e2e/cli/test_rem_open_snapshot_browser.py tests/e2e/cli/test_rem_thread_actions_browser.py -n 2 -o timeout=300
```

The full run is allowed to finish. Any post-triage rerun will name only failing
cases, not repeat the full suite. Pytest basetemp is removed after completion;
fixture screenshots needed for review are copied outside it first.

### Test-name and presentation migrations

The test inventory retains all added sprint cases and original behavior
coverage. The intentional selector/layout migrations use these names:

| Earlier name | Merged case and reason |
| --- | --- |
| test_sessions_topics_summaries_outcomes_and_person | test_sessions_link_filters_person_topic_project_and_dates_stay_honoured; topic pickers left the list, bookmarked filters remain |
| test_sessions_more_topics_and_unstructured_notebooks | test_sessions_unstructured_notebooks_say_they_are_still_being_summarised; raw sessions stay distinguishable without a topic-chip shelf |
| test_sessions_real_data_list_order_artifact_search_and_topic_limits | test_sessions_real_data_list_order_and_artifact_search; order and archive search remain, chip limits belong to removed controls |
| test_person_owed_card_says_nothing_is_open_or_lists_mine_before_theirs | test_empty_between_you_keeps_one_calm_line_and_real_threads_remain; retained original name with the branch's owed-card assertions |
| test_person_page_has_no_second_hero_and_keeps_the_prose_in_full_memory | test_person_lead_shows_two_sentences_without_a_second_hero; retained original name with complete intro disclosure, since the second hero was intentionally removed |

Original punctuation/privacy and active/old/no-index metric test names now
live in test_rem_person_integration.py. The desktop/phone calendar/project/day
filter test remains separate from the new bookmarked-filter case. No rc60 task
receipt, approval or irreversible-send guard case was discarded.

All six fetched branch tips pass git merge-base --is-ancestor against the final
merge; the local first-parent order is d0ef1d42, 3676fe60, 79504f7b, d0498f4e,
2094ccdc, 9776b316.

Final integration-only recheck after the parent-page composition repair:
`29 passed in 1.24s`. The full browser suite runs without concurrent screenshot
capture or other browser suites; the independent rendered review starts only
after it exits.

## Completed full browser run and triage

Exact full-run final line: `60 failed, 311 passed in 389.32s (0:06:29)`.
The suite finished uninterrupted; it was not repeated. Archived 23 fictional
screenshots outside basetemp, then removed the pytest-of-changxing directory.
Both prepared-person-draft route variants and all new hierarchy width/theme
cases passed this full run.

Root-owned repairs/migrations: the standalone mapped-project date test pins
en-US, matching its literal date contract; the Projects hero's dated latest
item and first nonempty lane follow the final branch behavior. Sessions phone
controls retain 40px touch targets; desktop uses the intentional compact 32px
minimum. People table entry includes display mode in its animation identity,
so entering the table animates once and filtering does not replay it. Org
no-match results again offer one working clear action; old generic filter
selectors include the new org field. Generic record disclosure tests open org
Full memory before inspecting related-page and conversation disclosures.

No 50ms Sessions performance failure occurred in the full run; no timing-only
failure has been identified by source/targeted review.

# People/person browser triage (AI review)

The single full browser run reported no prepared-person-draft failures: both route variants passed.

| Original failure | Classification and cause | Change / recheck |
| --- | --- | --- |
| `test_mobile_record_keeps_freshness_and_primary_navigation_in_reach` | Product layout regression: person heading y=141.1875 exceeded compact-header requirement. Follow-on selector was obsolete. | Reduced mobile r4 headrow margin by 2px; `.r4-crumb a` is category navigation. Selected case passed. |
| `test_record_heading_is_visible_within_compact_mobile_chrome[375-people/mara-ostrowski.md]`, `[390-people/mara-ostrowski.md]` | Same product layout regression. | Same CSS fix; root targeted rerun verifies both variants. |
| `test_pages_about_the_user_read_as_you_and_the_markdown_keeps_its_words` | Test coupled to lowercase text: new evidence row capitalizes sentence start. Owner-neutral wording is correct. | Keep no-`the user` assertion and compare required sentence case-insensitively. Selected case passed. |
| `test_cached_prose_follows_interface_and_page_override[375]`, `[1440]` | Legitimate design change: People row shows an obligation rather than person intro. Header also dropped translation badge. | Assert Chinese obligation summary in People rows; retain intro checks on full memory/week/search. Restore pending badge to `.r4-crumb`. Both selected variants passed. |
| `test_cached_facts_translate_subtitles_and_connected_context[375]`, `[1440]` | Phone company remains in DOM but is intentionally hidden to leave room for obligation; desktop translation works. | Check `.org` text content and visibility only >=720px. Desktop selected variant passed; phone alignment applied after focused run, awaiting root rerun. Org blocks handled by org reviewer. |
| `test_chinese_cached_translation_never_exposes_labelled_words[375]`, `[1440]` | Test closed Full memory then operated page-language select inside closed disclosure. | Reopen before selecting; preserve all hidden-private assertions. Both selected variants passed. |
| `test_round_nine_ledger_and_record_threads_align_ages` (16 variants) | People passed. Org moved from `.next-exchanges` to owed cards; prose mutation did not update structured obligations. Phone intentionally puts age below title. | Build invented dated/undated obligations before render; keep project checks; assert org chip alignment on desktop and below-title placement on phone. 12/16 selected variants passed; four phone assertions aligned after focused run, awaiting root rerun. |
| `test_round7_local_done_copy_undo_reload_and_record_tag` | Static provider navigation is now a quiet link. Source resolves to Gmail after canonical obligation projection. | Assert Gmail link plus Mark done; preserve copy/done/undo/reload/count semantics. Provider label corrected after focused run, awaiting root rerun. |
| `test_done_skip_undo_and_offline_reconciliation[1280]`, `[375]` | Test harness bug: Patchright route callback directly invoked helper using `asyncio.run()` on an active event loop. | Run helper in worker with no running loop. Restore person returned-new-mail marker. Root targeted rerun verifies. |

Selected People command used `-n 2 --basetemp=/tmp/rem-people-triage`; exact final line before three final selector/geometry corrections:

```text
6 failed, 19 passed in 21.69s
```

Six failures were phone translated-company visibility (1), phone org age position (4), stale Outlook expectation versus recorded Gmail (1). All six alignments are applied. No further run started; root will run combined original-failure subset. No timing-only failure identified. No owner notebook read.

## Final People subset

Root's original-60 subset confirmed the earlier 25-case alignments. It exposed these remaining People-related fixture/harness issues, now fixed:

- `test_summary_omits_empty_relationship_history_and_unknown_facts` (2): replacing Mara prose left structured `organisations` and `units` from the original snapshot, so the subtitle correctly retained the real fixture's organisation. Explicitly clear stale metadata alongside replacing prose; preserve privacy/history/no-unknown-field checks and affiliation fallback behavior.
- `test_round10_calm_record_sections_and_unassigned_person_threads` (2): calm organisation redesign uses the sentence “You owe Northgate University nothing”, rather than an Open threads heading. Test that plain sentence, absence of fake owed heading/card, overflow, and all existing project/person calm and unassigned-thread assertions.
- `test_done_skip_undo_and_offline_reconciliation` (2): Patchright `wait_for_function` does not accept `isolated_context`. Use bounded polling with main-world `evaluate` to inspect `pendingThreads`. Every skip/done/undo/reload/offline/new-mail assertion remains and passes.

Exact final line of the six-case scoped rerun:

```text
6 passed in 11.79s
```

Log: `/tmp/rem-people-second.log`. Basetemp `/tmp/rem-people-second` removed after the run. No People failures remain in the scoped recheck. These were deterministic fixture/test API issues, not timing-only failures.

# Independent AI org browser triage

Fixture-only review of the completed original full browser log. No full run stopped or repeated. Scoped temporary directories removed afterward; logs retained.

## Product fixes

- `test_written_pages_show_the_complete_source_action_on_phone`: custom org page lacked the complete first-screen source action. Added a 44px header View sources link to the original Sources section.
- `test_record_heading_is_visible_within_compact_mobile_chrome[375-orgs/fernhill-labs.md]` and `[390-orgs/fernhill-labs.md]`: actual H1 y=145 exceeded compactness requirement. Reduced mobile org header top margin by 6px; both pass.
- `test_org_context_citation_is_flush_and_uncertainty_has_an_icon_gap`, `test_org_collapses_full_memory_and_omits_self_provenance`, `test_org_avoids_repeating_header_threads_and_context_snippets`, `test_connected_context_without_snippet_is_compact_and_top_aligned[1440]` and `[375]`: new org screen omitted source-backed connected context/conversations. Restored existing recordContext inside collapsed Full memory; tests open it before checking citation geometry/provenance/deduplication. Uncertainty wording and marker remain checked in full note.

## Legitimate design changes; tests aligned

- `test_every_view_fits_a_phone[dark]`: intentional org green-black palette rgb(14,17,15), replacing legacy rgb(14,17,32). Theme/overflow checks preserved.
- `test_consecutive_marked_sentences_hide_in_the_lead_and_full_note`: structured org overview replaces generic focus-statement. Check overview exposes no labelled words; Full memory preserves three private passages, grouped citations, code and hide/reveal behavior.
- `test_activity_discloses_five_complete_rows_and_filters[1440-orgs/fernhill-labs.md]` and `[390-orgs/fernhill-labs.md]`: Lately intentionally uses eight rows plus older disclosure. Inject twelve histories; assert eight initially, twelve after Show all, complete content and no overflow. Project variants retain generic five-row/filter contract.
- `test_cached_facts_translate_subtitles_and_connected_context[375]` and `[1440]`: org list is ov-row, not sheet c-what; translated What remains in detail rail, connected evidence in Full memory. Preserve translation and original-language-return assertions. Scoped mobile follow-up failed earlier on People mobile company-label assertion, owned by other reviewer.
- `test_round_nine_ledger_and_record_threads_align_ages` sixteen variants: org now uses ov-owed/ov-owe, not next-exchanges/thread. Assigned other reviewer; selector guidance supplied. No hierarchy case failed original full run.

## Exact scoped results

`/tmp/rem-org-triage.log`: `17 passed in 14.09s` (source/privacy/provenance/activity, four hierarchy theme/width cases, two compact org H1 cases, both theme all-view overflow).

`/tmp/rem-org-translation.log`: `1 failed, 2 passed in 3.52s` (stronger org-repeat assertion and desktop translation passed; mobile failed People company label before org checks).

Final follow-up `/tmp/rem-org-second.log`: `4 passed in 3.93s`.

Remaining connected-context two failures were test disclosure-state errors: two additional render calls rebuilt Full memory collapsed. Reopened after each render; original layout/privacy assertions retained.

Remaining quiet-lead-citations two failures were scroll/hover timing: citations moved into disclosed Full memory; automatic hover scrolling delivered a scroll event after pointerover, and the intended scroll-dismiss handler removed the tooltip. Explicitly scroll citation into view and await two animation frames before independent hover/focus/evidence/focus-restoration checks. No product tooltip changes. A fixture-only event trace confirmed scroll then pointerover produces the expected tooltip after settling.

Custom second-run temporary directory removed; log retained.

## Final targeted reconciliation

All original 60 full-run failures were selected explicitly by node ID. First
combined recheck: `11 failed, 49 passed in 82.36s (0:01:22)`. Those remaining
cases exposed further stale fixture metadata, disclosure lifecycle and browser
harness assumptions. People6: `6 passed in 11.79s`; org evidence4:
`4 passed in 3.93s`; no-match navigation1: `1 passed in 2.01s`.

Last combined browser recheck selected exactly those remaining eleven:
`11 passed in 14.83s`. All original 60 failures are therefore resolved by
targeted rechecks; the entire 371-case suite was deliberately not repeated.
No timing-only under-load failure remains. Tooltip scrolling required explicit
scroll-settlement synchronization, not a looser assertion or longer timeout.
The navigation wait retains the exact destination heading assertion.

Final independent capture: 32 fixture-only screenshots across Today, People,
person, Projects, Sessions, organisation list, organisation and unit pages;
1440px/390px, light/dark, English. Capture inventory reports zero page errors,
zero external requests and zero document overflow. This is named sample
coverage, not an all-page pass. Files: `/tmp/rem-sprint-review/`.

## Final verification and remaining failures

Exact final complete unit line:

```text
18678 passed, 19 skipped, 2944 warnings in 145.44s (0:02:25)
```

The rendered review found a known team incorrectly called an unknown
organisation, and nested unit cards truncated names despite available width.
Fixed the unit-kind condition with two regression variants; nested explicit
trees use full width while flat Team groups retain their grid. Final scoped
unit line: `31 passed in 1.27s`. Final browser layout recheck line:
`4 passed in 3.55s`. Root/unit screenshots were recaptured and re-inspected.

The last combined original-failure browser recheck remains:
`11 passed in 14.83s`; all original 60 failures resolved across the49+11
combined rechecks. The single entire browser run's exact line is recorded
above (60 failed,311 passed); no second full run occurred.

Remaining failures by name: **none**. Timing-only failures under load: **none
identified**. No owner notebook was used, no external message sent, no push.
All required default pytest basetemp directories and reviewer-specific test
basetemps were removed. Logs/screenshots retained outside basetemp are
fictional fixtures.

Independent AI rendered reviews (not human-founder reviews):
- [People/person/Today,12 actual states](rem-sprint9-rendered-review-people.md)
- [Org/list/unit/Projects/Sessions,20 actual states plus8 rechecks](rem-sprint9-rendered-review-org-projects.md)

The Today observations in the review are pre-existing/fixture-limited and
remain unchanged per rc60 ownership. All significant in-scope integration
findings were repaired and rechecked.
