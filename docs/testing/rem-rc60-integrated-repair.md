# rc60 integrated Today repair

Branch: `release/1.9.3rc60`. No commits, live provider calls, or changes to the owner's notebook or `~/.co`.

## Product changes

- `today.py` distinguishes the owner's latest answer (`replied`) from future commitments (`task`). The small rule reads cleaned owner words: first-person English `I'll` / `I will`, elided `Will send` and related work verbs, Chinese `我会` / `我下周` / `我明天` and related time cues. Negatives, third-person `will`, reporting cues, quoted history and signatures are excluded. This is a suggestion to confirm completion, never automatic resolution.
- Owner excerpts drop mail headers/body markers, greetings, quoted history, signatures/mobile footers and URLs. They retain the first two sentences, clipped near 90 characters without splitting Latin words.
- An answered card offers green **Mark done** first and the original mail thread second. English and Chinese explanations show the owner's words and date. Stale prepared mail is hidden for owner-last replies and promises.
- Channel badges remain Outlook/Gmail reply, Lark or session. Only an obligation with no recorded channel becomes Task; a prepared mail draft retains its provider badge.

## Decisions for the ten integrated failures

| Original failing cases | Decision and retained coverage |
| --- | --- |
| `test_rem_search_identity.py::test_morning_cards_do_not_assign_an_ambiguous_counterpart` (three parameters) | Ranking legitimately moved from JS `morningEntries` into Python `today.queue`. Tests now exercise the Python authority and its actual JS projection, retaining all counterpart expectations. |
| `test_a_single_word_title_does_not_disambiguate_morning_cards` | The migrated test exposed a real Python regression: a single-word title incorrectly won over another person's matching first name. Fixed candidate selection. |
| `test_morning_counterpart_must_count_existing_aliases` | The migrated test exposed a real Python regression: aliases no longer blocked ambiguous identity. Fixed alias collision counting. |
| `test_morning_does_not_add_alias_only_resolution` | Test harness migrated to Python ranking; aliases still cannot nominate a counterpart on their own. |
| `test_rem_deadline_state.py::test_reader_keeps_old_deadlines_in_active_counts_and_today` | Ranking legitimately moved. Feed the real Python queue to the JS projection; preserve overdue/nearby deadlines, active counts, translated text, original evidence and done filtering. |
| `test_rem_translate.py::test_daily_rechecks_runner_budget_after_a_translation_repair` | Translations legitimately gained an independent attempt allowance and newest-page ordering. Renamed to `test_daily_rechecks_translation_budget_after_a_repair`; deterministic timestamps, a repair consuming two translation attempts, one additional page, and an uncached third page now prove immediate cap rechecking despite a smaller investigation budget. |
| `test_rem_reader_design.py::test_the_template_names_no_remote_host_and_loads_no_font` | Explicit navigation to the original Gmail/Outlook thread is intended. Permit exactly those hosts; retain checks excluding remote asset loads, remote literal fetches, fonts, imports and links. |
| `test_rem_reader_lazy.py::test_today_renders_a_usable_first_card_without_parsing_detail` | Opening an uncached recorded source replaces guessed mail composition. Check that source link; preserve the real first-card/overdue/headline/fold rendering with no detail fetch or parse. |

No tests were removed. Adjacent English/Chinese reason tests now provide the real `last_word_yours` field and assert the requested promise wording. The existing desktop/phone, English/Chinese, live/snapshot browser fixture also checks answered-card completion actions, clean quotes and provider badges.

## Red to green

- New fictional Today cases: `37 failed, 1 passed in 4.24s` before implementation.
- Migrating ranking tests exposed real alias/single-word regressions: `3 failed, 38 passed in 1.36s` (including a missing title in the migrated deadline fixture, corrected without changing its assertions).
- Nine focused modules after the original repairs: `617 passed in 5.96s`.
- Review regressions for mobile/indented history and stale draft controls: `5 failed, 1 passed, 44 deselected in 1.03s`.
- Review regressions for ordinary first-person future phrasing and negative “never”: `4 failed, 14 passed, 36 deselected in 0.91s`.
- Final classification, quote, identity, deadline and translation checks: `171 passed in 4.42s`.

## Independent experience review

A separate AI reviewer adopted a marketing/UI technology-founder perspective. It inspected the supplied desktop Today screenshots (collapsed and expanded), then reviewed current source and actual JavaScript DOM projection tests for English/Chinese answered and promise cards, provider badges, prepared/no-reply/pending draft states, counterpart/alias ranking and overdue deadlines. It found three issues: future commitments after ordinary introductory text, mobile signature leakage, and stale prepared reply controls on owner-last tasks. All received failing regressions and fixes; the independent recheck found no remaining material issue within scope.

This was an AI role review, not a human founder review. Final desktop/mobile rendered inspection is blocked by Chrome launch failure; baseline screenshot coverage and DOM checks are not an all-page visual pass.

## Validation environment

The exact initial full-unit run ended:

```text
149 failed, 18122 passed, 21 skipped, 2848 warnings, 1 error in 125.93s (0:02:05)
```

Besides the ten integrated failures, this sandbox adds unrelated failures: `/usr/bin/git` refuses to run due to the unaccepted Xcode license, `TERM=dumb` disables color, socket/process operations are denied, and handoff's sandbox guard correctly refuses launch operations. Final unit validation puts the existing `/Library/Developer/CommandLineTools/usr/bin/git` first on PATH and uses `TERM=xterm-256color`. No installation, credentials or sandbox guards were changed.

Final command summaries are recorded below after the runs finish.

Final nine-module scoped command:

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_today.py tests/unit/test_rem_reader.py tests/unit/test_rem_proactive.py tests/unit/test_rem_deadline_state.py tests/unit/test_rem_reader_design.py tests/unit/test_rem_reader_lazy.py tests/unit/test_rem_search_identity.py tests/unit/test_rem_translate.py tests/unit/test_rem_translate_nightly.py -n 8 --dist=worksteal
```

```text
627 passed in 29.35s
```

Required browser command (repeated after the final browser fixture changes):

```bash
CO_REM_BROWSER_TEST=1 uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/e2e/cli/test_rem_reader_design_browser.py tests/e2e/cli/test_rem_reader_browser.py tests/e2e/cli/test_rem_open_snapshot_browser.py -n 4
```

```text
18 failed, 2 skipped, 302 errors in 64.71s (0:01:04)
```

Chrome fails in `BrowserType.launch` with `TargetClosedError`, exit signal `SIGABRT`, before a page can render. These are launch failures, not passing browser assertions. The owner must rerun this command outside the sandbox to inspect final desktop/mobile behavior.

Required full unit command, with only the toolchain/terminal environment normalized:

```bash
export PATH="/Library/Developer/CommandLineTools/usr/bin:$PATH"
export TERM=xterm-256color
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 8 --dist=worksteal 2>&1 | grep -E "^FAILED|passed|failed"
```

The run was additionally captured with `tee /tmp/rc60-unit-final.log` before the final grep. Exact last line:

```text
105 failed, 18222 passed, 20 skipped, 2858 warnings, 1 error in 200.13s (0:03:20)
```

All ten original integrated failures are absent from the final failure list. The remaining failures also existed in the initial run; they cover sandbox-refused handoff starts, socket/process inspection and teardown, server-key filesystem isolation, and the pre-existing Outlook draft-listing I/O failure. No sandbox guards or unrelated production code were weakened to make the suite appear green. The full suite is **not green** in this environment and this report does not certify a release.

Captured logs: `/tmp/rc60-unit-before.log`, `/tmp/rc60-unit-final.log`, `/tmp/rc60-today-red.log`, `/tmp/rc60-ranking-red.log`, `/tmp/rc60-review-red.log`, `/tmp/rc60-future-red.log`, `/tmp/rc60-all-focused-final.log`, `/tmp/rc60-browser-verified.log`. `git diff --check` passes.
