# rc55 browser failure reconciliation

Integration base: `sprint4/rem-rc55`, `11432e70`. Input:
`../rc55-browser-failures.txt`, 46 failing parameter cases from 314 Chrome tests.
Read `CLAUDE.md`, inspected `git diff origin/main..HEAD -- connectonion/rem/`
and traced the relevant changes with `git log -S` and commit diffs. No test was
deleted, no Chrome process was launched, and no commit was made.

The table accounts for all 46 cases, including the previously merged fixes.
Names below are complete pytest function names. Unless a filename is specified,
they belong to `tests/e2e/cli/test_rem_reader_design_browser.py`. Counts include
all failing parameters in the input, not additional tests in the suite.

| Cause and history | Tests covered | Intended? | Change made / retained |
| --- | --- | --- | --- |
| Background queue status replaces manual investigation/import/translation controls (`b1927e56`; queue/off refinements in `645ed30e`) | **18 cases:** `test_private_mapped_project_explains_why_it_waits_on_desktop_and_phone`; `test_written_unknown_sections_are_distinct_from_uninvestigated_pages`; `test_investigation_command_targets_the_notebook_being_viewed`; `test_skill_name_matches_are_not_presented_as_installed_version_runs`; `test_mapped_person_distinguishes_map_date_from_missing_note_fact`; `test_mapped_guidance_explains_before_command_with_secondary_copy` ×4; `test_empty_sessions_offer_one_copy_action_without_filters` ×4; `test_cached_prose_follows_interface_and_page_override` ×2; `test_round11_reader_languages_and_written_page_translation_fallback` ×2; `test_a_mapped_page_leads_with_what_is_known` in `test_rem_open_snapshot_browser.py` | Yes | Assert queue/off states and absence of obsolete commands. Preserve private-project command coverage, including the selected notebook root. Check written gaps by name and mapped gaps by count. Check the pending-translation badge and enabled/off notice states. Retain the merged empty-sessions update. |
| Owner has separate You navigation and is excluded from People (`a409b633`) | **2 cases:** `test_people_open_as_a_sheet_that_sorts_filters_and_opens_a_row`; `test_first_map_shows_results_next_step_and_held_count_on_phone` | Yes | Expect five other people; exclude the owner from the computed browse count. Count actual data rows. First-map next step now checks the visible queue status instead of the removed preview button. |
| Expanded relationship columns use an automatic table layout (`f61098ea`) and can stretch the sticky name past the scroller width | **1 case:** `test_the_people_sheet_fits_1440_and_says_when_it_is_cut` | No: sticky-name regression | Bound the expanded name column to 240px on desktop/tablet. Preserve the original geometry and overflow assertions; Chrome must confirm the rendering result at 900px after maximum horizontal scroll. |
| First-build age comes from the earliest notebook run, independently of the recent log window (`fbdd25e3`) | **3 cases:** `test_partial_pass_keeps_written_memory_beside_failure`; `test_round10_first_build_and_translation_notice` ×2 | Yes | Set `first_run_at` when a fixture intentionally models a first build. Keep successful-page and failed-run assertions. Retain the already merged first-build and translation-notice update. |
| Session cards separate outcomes from tags; pages show a visible transcript, full final reply and source-to-turn navigation (`f2484e00`) | **6 cases:** `test_sessions_topics_summaries_outcomes_and_person`; `test_session_page_structure_precedes_closed_conversation` ×2; `test_session_find_outline_and_long_reply` ×2; `test_session_source_deep_link_reveals_details` | Yes | Target `.session-outcome`; check Summary → transcript → structured outcomes. Keep Find next/previous, HTML escaping, full 3000-character reply, disabled empty-find controls and turn navigation. Check mapped source links highlight their transcript turn and unmatched retained sources reveal Details. Replaced the obsolete closed attachment/outline expectations. |
| Conversation projection requires this page's retained citation windows (`a409b633`) | **4 cases:** `test_round_nine_full_purpose_and_quiet_record_disclosures` ×4 | Yes; synthetic fixture was stale | Supply source-keyed `windows`, `anchors`, message IDs and retained excerpts. Require exactly three Related pages disclosures and one Cited conversations disclosure. Do not lower the four-disclosure requirement. Add six offline cases running the browser's exact fixture edit through the real projection, covering all three record categories in both languages. Retain the earlier Investigated-pill correction. |
| Cached translations must preserve canonical Sources (`b56eec48`) | **2 cases:** `test_chinese_cached_translation_never_exposes_labelled_words` ×2 | Yes; fixture cache was invalid | Keep the original Sources description instead of translating it, and assert `cached()` accepts the fixture before opening Chrome. Preserve all private-text/label checks, page language override and search checks. Update its final mapped-page badge to Translation pending. Validated headings, citations, privacy markers and Sources offline. |
| Source identity started using the mailbox sender formatter (`a409b633`); mailbox parsing lowercased a bare display name | **2 cases:** `test_hidden_excerpt_keeps_identity_claim_and_inline_reveal` ×2 | No: display-name regression | Preserve case for a bare display name such as Mara while continuing to normalize email addresses. Added an offline regression test; observed red (`mara` versus `Mara`) before the fix and green afterward. Keep the browser identity/claim/reveal assertions. |
| Person facts and their citations sit inside the closed Full memory and sources disclosure (`ce93b17b`) | **1 case:** `test_numbered_card_source_opens_as_text_without_rewriting_page` in `test_rem_reader_browser.py` | Yes; interaction was stale | Open the disclosure before clicking the citation. Preserve escaped source text, return focus, phone overflow and unchanged notebook checks. |
| Overdue is distinct from due soon (`108ac316`) | **4 cases:** `test_round7_home_brief_today_limits_search_and_progressive_disclosure` ×4 | Yes | Retain the merged expectation of 1 overdue + 5 due soon, with seven parsed requests, five displayed cards and progressive disclosure. No further change needed. |
| Today and open-thread rows offer a direct primary action and local done/undo (`645ed30e`, test update `6d67d094`) | **1 case:** `test_round7_local_done_copy_undo_reload_and_record_tag` | Yes | Retain the merged single `.btn-act` assertion and absence of Copy prompt. Keep done, undo, reload, record tag and restored rail-count coverage. No further change needed. |
| Queue redesign accidentally replaced compact mapped-gap counts with all section names (`b1927e56`) | **2 cases:** `test_round10_mapped_page_missing_sections_use_a_count` ×2 | No; already fixed in `931de847` | Retain the restored mapped count, named written gaps and English/Chinese assertions. Existing unit coverage verifies both forms. |

Total: **46 cases**. None of the supplied failures is classified as environmental.
Timeouts on removed controls and closed disclosures are behavior/interaction
mismatches, not browser-environment failures. System `git` hit an Xcode license
gate locally; the installed CommandLineTools git worked for the history audit.

## Validation and independent review

Requested command:

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_reader.py tests/unit/test_rem_reader_sessions.py tests/unit/test_rem_sessions.py -n 6
```

Result: **402 passed in 3.54s**. This includes compilation of browser evaluate
strings, seven new offline regression/fixture cases and the existing reader,
reader-session and session tests. It does not establish a Chrome pass.

A separate AI reviewer inspected source, fixtures and diffs from the
product/UI perspective. It found no additional confirmed blocker. This was a
static review, not a rendered desktop/mobile review or a real founder review.

User-run Chrome rechecks, in priority order:

1. People at 1440px, then expanded at 900px and maximum internal horizontal
   scroll: pinned name edge, shaded cut edge and document overflow.
2. Session detail at 1400px and 375px: source/decision navigation highlights
   and reveals the requested turn; current Find matches enter the viewport.
3. Round nine at 390px/1440px and en/zh, for project/org/person records:
   exactly four disclosures, quiet summary styling and phone tap targets.
4. All 46 previously failing parameter cases, followed by the full opt-in run.

Main reader documentation in `docs/cli/rem.md` now records owner exclusion,
session transcript behavior and translation queue/cache behavior. Wiki and
docs-site publication remains a separate release documentation step.
