# rc60 browser triage — 2026-11-08

Branch `release/1.9.3rc60`, starting HEAD `57203e70`. No commits. The owner's
`~/.co` was not written. Chrome ran through Patchright with isolated browser
profiles and fictional notebooks; pytest's autouse HOME isolation remained on.

The supplied baseline had 27 failures, 299 passes and one Chrome-launch setup
error. Fifteen failing cases belong to the supported Today/translation/Open
threads scope. Twelve cases are deferred unchanged because they exercise person
ledgers or Sessions, including one mixed local-completion/person-ledger test.
No product defect was established by the fifteen in-scope failures: they asserted
superseded presentation contracts or mutated fixture data without rebuilding
the shared projection. No test was deleted, skipped, marked xfail, or had an
overflow/page-error assertion weakened. Production code is unchanged.

## Decisions for every original failing case

Paths below are relative to `tests/e2e/cli/`. Parameter lists account for every
individual failing invocation in the supplied log.

| Test and failing parameters | Cases | Decision and location |
| --- | ---: | --- |
| `test_rem_reader_design_browser.py::test_open_request_dates_keep_explicit_deadlines_on_the_notebook_calendar` | 1 | **Deferred, unchanged.** Although its name concerns dates, it navigates to a person's page and reads `.ledger-column.mine .ledger-row .ledger-meta`. The missing ledger is owned by the person-page redesign. Definition at line 1429. |
| `test_rem_reader_design_browser.py::test_phone_open_preview_names_elapsed_age_and_keeps_the_full_thread` | 1 | **Deferred, unchanged.** Reads the person's ledger metadata and full thread; definition at line 1454. No overflow assertion changed. |
| `test_rem_reader_design_browser.py::test_open_context_is_not_counted_as_waiting_on_other_people` | 1 | **Align fixture to shared projection.** The subject is the Open threads destination, not the person-page UI. It inserts synthetic plain context into record data, then now awaits `refreshTodayQueue()` before rendering. The Python Today projection is authoritative after the merged ranking change. Still requires the plain item in its own section and excludes plain items from Waiting on others. Line 1230. |
| `test_rem_reader_design_browser.py::test_sessions_typing_renders_three_hundred_rows_under_fifty_ms` | 1 | **Deferred, unchanged.** Sessions performance belongs to the active redesign. Definition at line 2591. The 50 ms threshold remains intact. |
| `test_rem_reader_design_browser.py::test_person_ledger_discloses_extra_rows_and_deep_hash_targets[375-light]`, `[375-dark]`, `[390-light]`, `[390-dark]`, `[1400-light]`, `[1400-dark]` | 6 | **Deferred, unchanged.** Missing person-ledger columns/count/disclosure/hash targets. Definition at line 2225. |
| `test_rem_reader_design_browser.py::test_chinese_cached_translation_never_exposes_labelled_words[375]`, `[1440]` | 2 | **Align translation assertion.** `Outlook 原文尚未归档。` is a useful missing-mail-archive warning, not an untranslated-page badge. Continue prohibiting `.lang-status` and the actual translation-fallback message; all private-word, private-label, overflow and page-error checks remain. Line 4002. |
| `test_rem_reader_design_browser.py::test_round7_home_brief_today_limits_search_and_progressive_disclosure[light-390]`, `[light-1440]`, `[dark-390]`, `[dark-1440]` | 4 | **Align static action contract.** Undrafted static mail cards open provider sources rather than claiming a live Draft now action. Require five source links and five local Mark done buttons and prohibit Draft now. Ranking, five-card limit, overdue counts, search, disclosure and overflow checks remain. Line 4074. |
| `test_rem_reader_design_browser.py::test_round7_local_done_copy_undo_reload_and_record_tag` | 1 | **Deferred, unchanged (mixed subject).** Its initial primary-button style assertion predates quiet provider-source links, but the same test then asserts the person's `.ledger-row` done-tag/Undo behavior. Preserve the complete test for the person-ledger builder rather than edit a prohibited mixed test. Definition at line 4094. Other Open threads completion tests and approval undo remain in the complete run. |
| `test_rem_reader_design_browser.py::test_round10_calm_record_sections_and_unassigned_person_threads[390]`, `[1440]` | 2 | **Deferred, unchanged.** The failure is on a person's `.between-you` section. Definition at line 4571. |
| `test_rem_reader_browser.py::test_today_draft_coverage_slots_and_honest_snapshot_actions[False-en-390]`, `[False-en-1440]`, `[False-zh-390]`, `[False-zh-1440]`, `[True-en-390]`, `[True-en-1440]`, `[True-zh-390]`, `[True-zh-1440]` | 8 | **Align cleaned quote contract.** `_owner_quote()` deliberately selects one cleaned sentence, or the future commitment sentence. Existing unit tests explicitly expect `Friday works.` for this body. The browser now requires that exact quoted sentence while retaining the completed-answer primary action, recorded source link, date, localized explanation and exclusion of headers/URL/signature/quoted history. Line 546. |

The original setup error was
`test_rem_reader_design_browser.py::test_every_view_fits_a_phone[light]`, in
`reader` at line 204: Chrome launch exceeded pytest's 60-second timeout before
any page existed. It is an infrastructure error, not evidence of overflow, and
did not recur in either completed full run. Chrome launch and viewport
assertions remain unchanged; the locale is normalized separately below.

## Additional findings from the first complete run

First complete run: `26 failed, 301 passed in 270.55s (0:04:30)`.
Output retained at `/tmp/rc60-full-browser-before-locale.txt`.
All fifteen original supported cases passed, the original Chrome setup error
did not recur, and the unchanged Sessions performance case passed. Eleven
original deferred cases remained, with fifteen additional failures below.

Fourteen additional failures were browser-locale drift: this machine's Chrome
defaults to Australian English (`16 Sept`) while the tests assert American
English literals (`Sep 16`). English `uiLocale()` intentionally uses the browser
locale, so both are valid product output. Pin the shared reader fixture's
`browser.new_page(..., locale="en-US")` at line 206; do not change product date
formatting, timezone logic, or protected test bodies. The independent AI review
confirmed that this matches the existing explicitly localized cross-timezone
test pages. The standalone Project test owns its own browser and is deferred
unchanged under the user's scope rule.

All names in this table are in `test_rem_reader_design_browser.py`:

| Additional failing test | Decision and definition line |
| --- | --- |
| `test_people_phone_cards_keep_contact_metadata_and_sorting[375]`, `[390]` | Locale-only failure; shared fixture normalization, protected body unchanged. Line 488. |
| `test_mapped_project_hero_says_it_waits_instead_of_showing_its_folder` | **Deferred, unchanged.** Standalone Project test's own page uses OS locale; `last on 2 Aug` versus `last on Aug 2`. Line 67. |
| `test_large_people_roster_keeps_mobile_controls_visible` | Locale-only failure; shared fixture normalization, protected body unchanged. Line 529. |
| `test_written_project_purpose_and_source_fit_on_phone` | Locale-only failure; shared fixture normalization, protected body unchanged. Line 1111. |
| `test_a_person_opens_on_the_relationship_ledger_with_facts_disclosed` | Locale-only failure; shared fixture normalization, protected body unchanged. Line 603. |
| `test_home_opens_on_what_to_remember_and_what_is_owed` | Normalize the fixture locale, then await the first destination task band before collecting headings after the hash-link click. Ordering and nonempty-row assertions remain. Definition line 293, navigation wait line 327. |
| `test_citations_name_the_source_and_open_marked_margin_or_sheet` | Locale-only failure; shared fixture normalization, body unchanged. Line 2100. |
| `test_citation_labels_fallback_and_grouped_sources_stay_honest` | Locale-only failure; shared fixture normalization, body unchanged. Line 2161. |
| `test_phone_activity_shows_complete_rows_with_latest_first` | Locale-only failure; shared fixture normalization, protected body unchanged. Line 1494. |
| `test_project_threads_only_label_explicit_direction_and_deduplicate_date` | Locale-only failure; shared fixture normalization, protected body unchanged. Line 3143. |
| `test_mapped_person_distinguishes_map_date_from_missing_note_fact` | Locale-only failure; shared fixture normalization, protected body unchanged. Line 1748. |
| `test_decision_memory_starts_collapsed_and_sources_use_readable_ids[en]` | Locale-only failure; shared fixture normalization, body unchanged. Line 3677. |
| `test_morning_rows_quote_only_original_words_and_format_overdue_dates` | Locale-only failure; shared fixture normalization, body unchanged. Line 2274. |
| `test_round10_list_empty_states_offer_one_working_next_action` | **Deferred, unchanged (mixed subject).** Covers People and Projects lists as well as search/Open threads. Failure is an immediate heading read after a hash-link click, before the destination render. Preserve the protected test for its builders; no assertion weakened. Line 4622. |

## Newly reachable behavior

Third complete run after the Today navigation wait:
`13 failed, 314 passed in 270.20s (0:04:30)`.
Output retained at `/tmp/rc60-full-browser-before-sources-wait.txt`.
Today home passed, and the protected mixed-list navigation race did not recur.
Twelve failures were unchanged deferred cases. One additional Skills test,
`test_skill_opens_on_its_finding_and_keeps_usage_in_full_note` (definition line
1616), immediately checked `is_visible()` after clicking the View sources hash
link. Await that exact sources section becoming visible at line 1640, then keep
the original visibility assertion. Source content, focus return, evidence and
document overflow, private-label and page-error checks remain unchanged. The
independent AI reviewer confirmed that this preserves the interaction contract
and still fails if sources never open. Skills is outside the protected
People/Projects/Sessions group.

Second complete run after locale normalization:
`14 failed, 313 passed in 275.03s (0:04:35)`.
Output retained at `/tmp/rc60-full-browser-before-navigation-wait.txt`.
All original supported cases passed. Thirteen failures were the deferred
person/Project/mixed-list cases. The remaining Today home case progressed past
its locale assertion and exposed an immediate `all_inner_texts()` read after
clicking the Open threads hash link. That API does not await elements: it read
`[]` before the `hashchange` render. Await `bands.first.wait_for()` at
`test_rem_reader_design_browser.py:327` before collecting headings; retain exact
heading order and nonempty-row assertions. The independent AI review confirmed
the wait cannot accept stale task bands because none exist on the home page.

After the original quote mismatch was corrected, one focused invocation
`test_today_draft_coverage_slots_and_honest_snapshot_actions[True-zh-1440]`
reached an asynchronous dialog-removal race: `dialog.close()` dispatches the
`close` event that removes the element. Await detachment before retaining the
zero-dialog assertion (`test_rem_reader_browser.py:575`). This synchronizes the
test with the browser lifecycle and does not change product behavior or dismiss
a failed send. The mocked request body still has to match the owner's edit.

## Verification and evidence

Original failing cases reproduced before edits: **16 failed in 49.28s** (the
fifteen supported cases plus the mixed local-done/person-ledger case).
First expanded recheck: **1 failed, 19 passed in 70.03s (0:01:10)**; the failure
was the newly reachable dialog-removal race described above.

Required unit command:

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_reader.py tests/unit/test_rem_today.py tests/unit/test_rem_proactive.py -n 6
```

Exact last line: `549 passed in 14.79s`.
Full output: `/Users/changxing/project/rem-work/rc60-browser-triage-unit.txt`.

Full browser command (all deferred cases included unchanged):

```sh
CO_REM_BROWSER_TEST=1 uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/e2e/cli/test_rem_reader_design_browser.py tests/e2e/cli/test_rem_reader_browser.py tests/e2e/cli/test_rem_open_snapshot_browser.py -n 4
```

Exact last line: `12 failed, 315 passed in 270.60s (0:04:30)`.
Full output: `/Users/changxing/project/rem-work/rc60-browser-triage-final.txt`.

Rendered evidence: `/tmp/rem-draft-coverage/today-{en,zh}-{390,1440}-{live,snapshot}.png`.
Approval evidence: `/tmp/rem-rc60-approval-shots/approval-{ready,held}-{light,dark}-{390,1440}.png`.
The approval test records the edited/selected state before confirmation and the
held result afterward; its existing sheet/document overflow and undo checks
remain. Requests are mocked: these images do not demonstrate real mail delivery
or a real mixed task/completion outcome.

Independent AI experience review: sampled all eight Today screenshots and all
eight approval ready/held screenshots; no significant visual defect found.
Source-channel badges remain explicitly covered by
`test_task_state_never_overrides_channel_or_draft_badge`; the promise explanation
distinguishes pending work. Nonblocking P3 polish: the disabled Confirm button
after approval retains its bright active appearance (`reader.html:4904`). If
polished later, recheck that completed/disabled Confirm looks inactive in both
themes while Close remains available. Lower approval task/handled rows were not
visually covered. This is an AI role review of named samples, not a real human
founder review or all-page pass.


Final disposition: all fifteen original supported failing cases passed. The
remaining twelve failures are eleven original deferred person-ledger/mixed
person-ledger cases plus the standalone Project locale assertion, all unchanged.
The unchanged Sessions performance case, the mixed-list empty-state case and
both phone-fit themes passed. The Chrome-launch setup error did not recur.
Today home and Skills source disclosure passed with the explicit navigation
waits. All approval, snapshot, translation, privacy and overflow assertions
remained active. `git diff --check` passed. No commits or production-code edits.
