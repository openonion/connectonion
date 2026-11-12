# Sprint 7: Today draft coverage verification

Branch: `sprint7/draft-coverage`, based on `bb64a3f1` (1.9.3rc59). No commit.

## Changes and regression evidence

- Shared Python queue and group identities: `rem/today.py`, `rem/reader.py`, `rem/drafts.py`, and the reader queue consumers. The 12-thread / budget-three case failed before the change. A further actual-JavaScript regression reproduced distinct mail requests being merged into one card, then passed when the reader consumed Python identities. Canonical DB dates remove excerpt-budget differences.
- Undrafted states: localized queue, missing-original/read-failure, owner-task and waiting-on-others reasons. The task uses the latest archived owner words and date. Primary actions draft only eligible replies, open resolved threads, or open an unresolved recorded source honestly.
- Slots: malformed and incomplete brackets are rejected during check; remaining markers block backend and writer sends. Red send tests proved the provider would otherwise be contacted. Chips retain the original marked content.
- Static cards: one live-reader command action replaces send, write, provider edit, skip and channel-switch buttons. The body stays readable; command wrapping is scoped to the draft card.

All new notebook examples use fictional people. The real notebook was not opened or modified. Supplied screenshots were inspected as read-only evidence. `withoutDateClutter`, `threadWords`, `morningWords`, `setInterfaceLanguage`, and person metrics were not edited.

## Independent AI experience review

An independent AI reviewer used a marketing/UI technology-founder perspective, identified the grouping, stale-promise and unresolved-source-link issues, and rechecked their fixes. Its final source recheck found no blocking issue. This was an AI role review, not a human founder review.

**Rendered desktop/phone review is pending.** Installed Chrome exited with SIGABRT before opening pages; all 320 browser failures/errors were `BrowserType.launch` / `TargetClosedError`. No new screenshots were generated. The alternate browser access host was unavailable, and native Chrome access was rejected by automatic approval review: “Computer Use was not approved to use Google Chrome.”

Recheck the named states once Chrome can launch: Today in English and Chinese at 390 and 1440 pixels; draft-slot wrapping; owner-task reason; queued and missing-original actions; static command reveal/copy; live inline send refusal; full-screen fill/send; draft-now success. These behaviors have deterministic unit coverage; their new browser cases did not reach page assertions.

## Every pytest invocation: exact command and exact last line

Commands below omit only shell output redirection to the linked log. Rows are chronological. Intermediate failures are retained, including the first rank test missing a Node fixture dependency; `reader-rank-red2` is the corrected behavioral failure. `send-red` reran the regression with serializable provider receipts and the send guard temporarily removed, reproducing four missing-refusal failures. Guards were restored before green verification.

| Log | Command | Exact last line |
| --- | --- | --- |
| [red](/tmp/rem-draft-red.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_reader.py -k 'nights_three or noncanonical or marked_parts or undrafted_today_reason or snapshot_replaces or writer_refuses'` | `15 failed, 364 deselected in 11.67s` |
| [green1](/tmp/rem-draft-green1.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_reader.py -k 'nights_three or noncanonical or marked_parts or undrafted_today_reason or snapshot_replaces or writer_refuses'` | `3 failed, 12 passed, 364 deselected in 11.49s` |
| [green2](/tmp/rem-draft-green2.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_reader.py -k 'nights_three or noncanonical or marked_parts or undrafted_today_reason or snapshot_replaces or writer_refuses'` | `1 failed, 14 passed, 364 deselected in 10.98s` |
| [unit1](/tmp/rem-draft-unit1.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_proactive_http.py tests/unit/test_rem_reader.py tests/unit/test_rem_daily*.py tests/unit/test_rem_next_submit.py -n 6` | `6 failed, 658 passed, 1366 warnings in 10.79s` |
| [unit2](/tmp/rem-draft-unit2.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_proactive_http.py tests/unit/test_rem_reader.py tests/unit/test_rem_daily*.py tests/unit/test_rem_next_submit.py -n 6` | `664 passed, 1366 warnings in 10.89s` |
| [focused](/tmp/rem-draft-focused.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_reader.py -k 'today_reply_state or nights_three or noncanonical or marked_parts or undrafted_today_reason or snapshot_replaces or writer_refuses or queue_card_prepared or today_includes'` | `19 passed, 362 deselected in 0.78s` |
| [promise-red](/tmp/rem-draft-promise-red.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py -k 'today_reply_state'` | `2 failed, 110 deselected in 1.24s` |
| [reader-rank-red](/tmp/rem-draft-reader-rank-red.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_reader.py -k 'preserves_python_ranks'` | `1 failed, 269 deselected in 1.19s` |
| [rank-promise-green](/tmp/rem-draft-rank-promise-green.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_reader.py -k 'preserves_python_ranks or today_reply_state or nights_three'` | `1 failed, 3 passed, 378 deselected in 0.52s` |
| [reader-rank-red2](/tmp/rem-draft-reader-rank-red2.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_reader.py -k 'preserves_python_ranks'` | `1 failed, 269 deselected in 0.43s` |
| [rank-promise-green2](/tmp/rem-draft-rank-promise-green2.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_reader.py -k 'preserves_python_ranks or today_reply_state or nights_three'` | `4 passed, 378 deselected in 0.46s` |
| [morning-red](/tmp/rem-draft-morning-red.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py -k 'morning_selects'` | `1 failed, 112 deselected in 0.32s` |
| [send-red](/tmp/rem-draft-send-red.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py -k 'refuses_marked_parts'` | `4 failed, 109 deselected in 0.51s` |
| [followup-green](/tmp/rem-draft-followup-green.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_reader.py -k 'morning_selects or preserves_python_ranks or today_reply_state or marked_parts'` | `8 passed, 376 deselected in 0.61s` |
| [unit3](/tmp/rem-draft-unit3.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_proactive_http.py tests/unit/test_rem_reader.py tests/unit/test_rem_daily*.py tests/unit/test_rem_next_submit.py -n 6` | `669 passed, 1366 warnings in 10.95s` |
| [browser](/tmp/rem-draft-browser.log) | `CO_REM_BROWSER_TEST=1 uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/e2e/cli/test_rem_reader_design_browser.py tests/e2e/cli/test_rem_reader_browser.py tests/e2e/cli/test_rem_open_snapshot_browser.py -n 4` | `18 failed, 2 skipped, 302 errors in 28.87s` |
| [budget-red](/tmp/rem-draft-budget-red.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py -k 'excerpt_budget'` | `1 failed, 113 deselected in 0.34s` |
| [date-red](/tmp/rem-draft-date-red.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py -k 'invalid_notebook_dates'` | `4 failed, 114 deselected in 1.32s` |
| [unit-final](/tmp/rem-draft-unit-final.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_proactive_http.py tests/unit/test_rem_reader.py tests/unit/test_rem_daily*.py tests/unit/test_rem_next_submit.py -n 6` | `674 passed, 1366 warnings in 13.07s` |
| [edge-red](/tmp/rem-draft-edge-red.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py -k 'noncanonical or marked_parts or not_advertised'` | `5 failed, 11 passed, 109 deselected in 0.68s` |
| [unit-final2](/tmp/rem-draft-unit-final2.log) | `uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_proactive_http.py tests/unit/test_rem_reader.py tests/unit/test_rem_daily*.py tests/unit/test_rem_next_submit.py -n 6` | `681 passed, 1366 warnings in 11.20s` |
| [browser-final](/tmp/rem-draft-browser-final.log) | `CO_REM_BROWSER_TEST=1 uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/e2e/cli/test_rem_reader_design_browser.py tests/e2e/cli/test_rem_reader_browser.py tests/e2e/cli/test_rem_open_snapshot_browser.py -n 4` | `18 failed, 2 skipped, 302 errors in 29.58s` |

The final unit result is green. Browser execution is blocked, not passed. No tests were disabled, and no real messages were sent.
