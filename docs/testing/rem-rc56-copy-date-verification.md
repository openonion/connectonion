# REM rc56 copy/date/plain-words verification

Branch: `release/1.9.3rc56`. Changes are uncommitted. `reader_page`, the design `reader` fixture, the completed-delivery timeout test, and the round10 first-build lazy-load test are unchanged.

The “assert False on layout” digest entries in people cards, large roster, and project purpose were text/provenance/date comparisons in the full log; their actual layout checks were retained.

Additional product safeguards in `reader.html:4532`: retain meaningful parenthesized document dates such as “agreement dated (2026-10-03)”, preserve quoted deadlines, and strip a due date only if the same date is displayed in metadata. Four added unit regressions cover failure payload safety, updated-original/translated deadlines, historical roles, and meaningful document/deadline dates. An existing translation-notice unit assertion now requires visible failure information.

## Per-test decisions

All test names below are in `tests/e2e/cli/test_rem_reader_design_browser.py`; parameterized variants share the same decision.

| Test | Decision | Evidence / reason |
| --- | --- | --- |
| `test_private_mapped_project_explains_why_it_waits_on_desktop_and_phone` (:31) | Test aligned | The investigation command is in `.reader-settings .cmd`, with no `.missing .cmd`; desktop/phone layout checks remain. |
| `test_home_opens_on_what_to_remember_and_what_is_owed` (:280) | Test aligned | `.today-thread .waiting-age b`: “12 days · due Oct 3”; same-year date and age are in metadata. |
| `test_people_phone_cards_keep_contact_metadata_and_sorting` (:476) | Test aligned | `.c-last .mono[title="Last contact in map"]`: “Sep 16”; map provenance remains in the title. All layout checks retained. |
| `test_large_people_roster_keeps_mobile_controls_visible` (:517) | Test aligned | Same “Sep 16” date/title check; retains controls, sorting and overflow assertions. |
| `test_a_person_opens_on_the_relationship_ledger_with_facts_disclosed` (:591) | Test aligned | Fact citation: “Aug 22”; accessible label “Source: Outlook, Aug 22, original not in this snapshot”. |
| `test_adjacent_citation_chips_show_only_the_supporting_sentence` (:639) | Test aligned | Evidence claim retains the entire quoted promise; the decorative trailing “(2026-10-14)” is omitted. Checks sentence isolation. |
| `test_investigation_command_targets_the_notebook_being_viewed` (:994) | Test aligned | Checks rooted command in `.reader-settings .cmd code`; retains exact notebook root and target assertion. |
| `test_written_project_purpose_and_source_fit_on_phone` (:1098) | Test aligned | Purpose citation accessible label starts “Source: Session, Aug 2”; all first-screen/overflow assertions retained. |
| `test_open_request_dates_keep_explicit_deadlines_on_the_notebook_calendar` (:1415) | Product bug fixed + test aligned | reader.html:3273 uses current original text; :4532 strips only matching metadata deadlines. Keeps explicit deadline and original ISO checks; metadata reads “due Today”, then “overdue · Yesterday” across Sydney midnight. Fictional cited request timestamp now agrees with its Oct 1 request date. |
| `test_phone_open_preview_names_elapsed_age_and_keeps_the_full_thread` (:1440) | Product bug fixed + test aligned | reader.html:3273 stops reading a stale original. The fictional cited request timestamp agrees with Sep 29 so the 5-day check remains meaningful under the latest-source age rule; full ask remains checked. |
| `test_dates_and_contact_age_use_notebook_calendar_on_another_browser_timezone` (:1458) | Test aligned | Contact “Yesterday”; same-year “Aug 1”/“Jul 31”. Cross-year “Dec 31, 2026” and notebook-timezone day boundary checks remain. |
| `test_phone_activity_shows_complete_rows_with_latest_first` (:1480) | Test aligned | `.activity-day`: “Sep 4”, “Sep 3”, “Sep 2”, “Sep 1”; all complete-prose and layout assertions retained. |
| `test_reviewed_role_and_unknown_company_override_older_index` (:1498) | Product bug fixed | reader.html:3739 parses updated English instead of the saved original; preserves “Programme manager (historical current unknown)” and explicit Unknown company. Test retained. |
| `test_mapped_person_distinguishes_map_date_from_missing_note_fact` (:1733) | Product bug fixed + test aligned | reader.html:6037 keeps map provenance in a title; visible `.contact-line` is “Last contact Sep 16”, and `.c-last .mono` retains its provenance title. |
| `test_unknown_open_status_is_not_a_current_exchange` (:1773) | Product bug fixed | reader.html:3273 reads current text so historical/unknown work is not resurrected from an older original. Test retained. |
| `test_completed_delivery_is_conversation_instead_of_a_commitment` (:1807) | Unchanged; deferred timeout | The supplied first failure is a lazy-load mutation overwritten before the page loads, followed by Locator.get_attribute timeout. This is the other engineer’s scope. Classification assertions and fixture are unchanged; DOM check after detail availability confirms Conversation/Commitment semantics. |
| `test_failed_init_is_visible_and_keyboard_reachable` (:1907) | Product bug fixed | reader.html:4522 consumes safe failure hints; reader.py:292/:299 carries generic recovery messages into Today without private runner output. Existing refusal/timeout, keyboard and privacy assertions retained. |
| `test_citations_name_the_source_and_open_marked_margin_or_sheet` (:2085) | Test aligned | `.person-insight .cite` is the quiet superscript “5”; title/accessible label still names “Mara, Outlook, Oct 14” and the subject. Source opening/highlighting/layout checks retained. |
| `test_citation_labels_fallback_and_grouped_sources_stay_honest` (:2146) | Test aligned | Same-year source labels omit 2026. Group superscript “4” retains `data-sources="4 5 6"` and accessible “3 sources for this line”; all three originals remain openable. Missing source label remains “source 99”. |
| `test_person_ledger_discloses_extra_rows_and_deep_hash_targets` (:2210) | Product bug fixed + test aligned | reader.html:3273 respects four current obligations instead of one stale obligation. :4532 moves matching due date into metadata. Fictional request-source times agree with the intended 7/85-day ages; preserves four-row disclosure, gone quiet, direction and deep-link assertions. |
| `test_morning_rows_quote_only_original_words_and_format_overdue_dates` (:2259) | Test aligned | `morningWords.words` keeps “A draft; send questions afterward.” and the complete quoted ask; `.context` contains “[5]”. Dates remain in prose without supplied metadata; “overdue · Sep 10” omits same-year 2026. |
| `test_project_focus_and_deep_note_do_not_repeat_purpose_or_threads` (:2298) | Product bug fixed | reader.html:3273 reads five current obligations, preserving three in focus and two in the deep note. Test retained. |
| `test_sessions_filters_notebook_calendar_and_groups` (:2518) | Test aligned | `.session-meta` contains “Today 09:12” rather than “Oct”; retains exact local time, filters and grouping assertions. |
| `test_summary_omits_empty_relationship_history_and_unknown_facts` (:2863) | Product bug fixed + test aligned | reader.html:4395 normalizes the stripped “Nothing.” to “Nothing open.”; the observation stamp is intentionally omitted. Privacy/history/unknown-fact checks retained. |
| `test_project_threads_only_label_explicit_direction_and_deduplicate_date` (:3124) | Product bug fixed + test aligned | reader.html:3273 restores current plain/mine/theirs rows; :4532 removes the matching date prefix already represented in meta. Keeps [“Open”, “You owe”, “They owe”]; tooltip is “since Sep 13”. |
| `test_partial_project_status_explains_the_uninvestigated_sections` (:3272) | Test aligned | Both status pills say “More to learn”; explanatory tooltip still describes the uninvestigated sections. |
| `test_audited_lists_keep_chrome_concise_and_prose_as_written` (:3593) | Test aligned | Chinese count is “N 项中，N 项有内容”; usage ends “最近 昨天” / “last Yesterday”. Original prose, directions and layout assertions retained. |
| `test_decision_memory_starts_collapsed_and_sources_use_readable_ids` (:3658) | Test aligned | Source ID reads “Claude Code session · Sep 3” / “Claude Code 会话 · 9月3日”; full source ID remains in title. |
| `test_chinese_waiting_summary_splits_and_trims_detail` (:3742) | Test aligned | The whole ask and later clause remain in `morningWords.words`; `.context` contains “[4]”. English also retains “; discuss tomorrow”. |
| `test_cached_facts_translate_subtitles_and_connected_context` (:3757) | Test aligned | `.waiting-ask .words` contains “你需要签署试点协议；后续安排明天讨论” and citation 4; the removed `.context` element is no longer required. Translation/subtitle/connected-context checks retained. |
| `test_round10_calm_record_sections_and_unassigned_person_threads` (:4545) | Product bug fixed + test aligned | reader.html:4395 gives all empty records the same plain “Nothing open.”; no observation-stamp prose. Unassigned thread and visual consistency assertions retained. |
| `test_round11_reader_languages_and_written_page_translation_fallback` (:4681) | Product bug fixed + test aligned | reader.html:4783 and reader.py:294 restore “1 个页面未能翻译。” when translation fails. Quiet notice continues “打开页面时会翻译成中文。”; removed queue spans/command controls are not asserted. |
| `test_reader_copy_uses_one_local_date_format_and_omits_owner_and_redundant_badges` (:4810) | Test aligned | All six local date/citation/time paths use “Yesterday”; owner and redundant-badge assertions retained. |

## Validation and limits

- Scoped unit regression run, four workers: **79 passed in 1.57s**. The focused first pass was 27 passed.
- Final scoped Chrome run with `-k` and `-n 4`: **1 failed, 53 errors in 6.84s**, all caused by Chrome launch failure before browser assertions.
- Full reader run, once, four workers: **10 failed, 302 errors in 27.58s** (312 cases). The two snapshot cases were then run once separately: **2 skipped in 0.97s**. Total 314 reader/snapshot cases accounted for: **0 passed, 10 failed, 302 errors, 2 skipped**. These are environment outcomes, not validated product regressions: Chrome aborts with SIGABRT; Patchright then reports kill EPERM. Snapshot fallback Chromium is not installed.
- Supplementary jsdom execution uses the actual rendered notebook and exact browser test mutation scripts. It confirms complete morning asks, explicit Today/Yesterday deadlines, all three direction labels, historical role/Unknown-company precedence, five project threads split 3+2, quiet ledger rows, and unknown-work filtering. This is DOM/behavior evidence, not a rendered desktop/mobile layout pass.
- Independent AI review checked source selection, preserved asks/deadlines, failure privacy and recheck criteria. No significant remaining introduced issue was found. Actual 390px/1440px rendering, source interaction and keyboard checks still require a Chrome-capable runner.
- Existing latest-cited-source age precedence is unchanged. Fictional timestamps were made consistent with the dates used by age-specific tests.
- `git diff --check` passed. No commit was made.

Exact browser summary lines:

```text
10 failed, 302 errors in 27.58s
2 skipped in 0.97s
```

Logs: `/tmp/rem-copy-unit-broad.txt`, `/tmp/rem-copy-browser-final.txt`, `/tmp/rem-rc56-full-browser-final.txt`, `/tmp/rem-rc56-snapshot-browser-final.txt`; supplementary DOM output: `/tmp/rem-copy-dom-results.txt`.
