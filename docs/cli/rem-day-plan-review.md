# Day plan review — issue #3058

Build: this worktree's uncommitted day-plan change. Documentation preceded the
new failing tests; implementation followed those failures. No commit was made.

The independent reviewer was an AI acting from a marketing/UI technology-founder
perspective, not a human founder. The review inspected code and executed-JavaScript
DOM tests for Today / Your day in English and Chinese: populated events and
proposals, literal/missing addresses, tomorrow, no calendar, unsaved/stale plans,
calendar failures, and grouped Done/Undo. No other page received a visual review.

| Priority | Finding and user impact | Resolution and recheck evidence |
| --- | --- | --- |
| P1 | A clarification could be called a promise; a project could be named as a person. | Reuse Today's future-commitment rule and use neutral wording for project/org rows. `test_day_plan_owner_question_is_not_a_promise_and_project_does_not_wait`, `test_day_plan_project_promise_never_names_project_as_person`. |
| P1 | Old silent dated promises could consume all five proposal slots. | Exclude the same >60-day dated/silent cases before selecting five. `test_day_plan_skips_stale_dated_promises_before_taking_five`. |
| P1 | A failed calendar read could appear freshly read; an existing calendar without a plan could be called unread. | Preserve failure/last-read words; distinguish the first plan save and show untimed proposals. `test_day_plan_retained_calendar_failure_is_said_with_last_read_date`, `test_day_plan_upgrade_fallback_reads_only_saved_calendar`. |
| P1 | A closed task could remain proposed above the rows that had disappeared. | Filter local grouped marks and current Today waiting/reply states without moving saved times. `test_day_plan_reader_hides_closed_grouped_items_and_restores_undo`. |
| P2 | A stale plan could call a past date tomorrow; calendar failure reasons could remain English in Chinese. | Hide the tomorrow section on stale days; translate the failure/never-read words. `test_day_plan_reader_words_links_addresses_tomorrow_and_no_calendar` runs both languages. |
| P2 | The stale-plan reader message offered a terminal command. | Reader message is plain language; `test_no_view_offers_a_command_to_copy` passes. CLI still offers a refresh command. |

The reviewer rechecked the fixes and reported no remaining blocking findings in
the inspected diff. The reviewer did not independently rerun pytest.

Functional evidence: the focused day-plan, reader, calendar, catchup and stage
files recorded 520 passing test calls. A separate complete run of
`test_rem_day_stages.py` and `test_rem_catchup.py` recorded 69 passing calls.
Every run used temporary HOME and TMPDIR. The repository host-leak guard remains
intact: sandbox denial of `ps` prevents a clean session-finish exit. Detailed
per-test outcomes were recorded by a temporary reporting plugin without changing
or suppressing the guard. The final requested unit selection recorded 1,095
passing calls, six failing calls and two setup errors. All eight unsuccessful
cases were sandbox denials of `ps` or loopback socket binding in existing
live-host/live-reader/task tests. There were no remaining assertion failures in
the changed functionality. A final run of the 26 new day-plan and reader cases
also passed before the session-finish guard was blocked.

Rendered desktop/mobile acceptance is **pending**. Two isolated `co browser`
launches failed to start the daemon; the alternate CUA browser transport returned
`native pipe closed before response`. There are no screenshots, viewport overflow
measurements, keyboard/focus checks or visual comparison claims. Reference
comparison is unknown: no visual reference was selected for this functional
addition. Next check: populated, unread, full-day/no-fit and stale Today at phone,
intermediate and desktop widths, in both languages, with keyboard and local Undo.

Open product decisions: all-day events currently occupy the whole working day;
proposals each reserve 30 minutes. Travel buffers, variable task durations and
provider availability/free flags are outside this deterministic first change.
