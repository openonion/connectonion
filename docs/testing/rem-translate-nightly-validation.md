# REM nightly translation validation

Branch: `sprint7/translate-nightly`. No commits, deployments, live model calls, or real notebook changes.

## Changes and regression evidence

1. Live interface selection sends one authenticated JSON POST to `/rem/language`; file snapshots send none. Config appends the tag through the existing validation/write path, preserving other settings and waiting for notebook writers. Three initial regressions failed then passed; the lock-contention regression also failed then passed.
2. Language settings are excluded from page-task material hashes. Raw-file and rc59 semantic hashes are migrated only when verified against saved/current config. Four initial submission regressions failed then passed, followed by upgrade regressions. Model and evidence-size changes still reject stale tasks.
3. Both scheduled paths use one backlog: active owner obligations first, then newest page modification times. Current caches are excluded and the daily allowance remains shared. All three ordering/cap regressions failed then passed. The first red native test had a fixture setup failure; enabling its worker produced the intended ordering failure before implementation.
4. Status reports current translations and the next run's budget-limited queue, or `not requested` with a command preserving existing language choices. It reports `schedule off` when disabled. Five initial status regressions failed then passed. Review added next-day budget, explicit-consent, and command-preservation regressions, each observed red then green.

Old ordering assertions were updated for the new requirement. Page timestamps in adjacent fixtures are explicit to prevent filesystem timestamp resolution from changing expected order. Recovery assertions still require accepted translations to survive and uncached work to resume.

## Every pytest invocation

The commands below were run in this checkout. Each output block is the exact last line of its captured output, including intentionally failing red runs and intermediate integration failures.

### 1. rem-step1-red

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive_http.py -k 'interface_'
```

```text
3 failed, 8 deselected in 3.69s
```

### 2. rem-step1-green

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive_http.py -k 'interface_'
```

```text
3 passed, 8 deselected in 1.46s
```

### 3. rem-step2-red

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_next_submit.py -k 'run_control_config_change and language'
```

```text
4 failed, 238 deselected in 3.68s
```

### 4. rem-step2-green

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_next_submit.py -k 'config_change or legacy_config'
```

```text
42 passed, 200 deselected, 174 warnings in 11.29s
```

### 5. rem-step3-red

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_translate_nightly.py
```

```text
3 failed in 1.20s
```

### 6. rem-step3-red2

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_translate_nightly.py
```

```text
3 failed in 1.25s
```

### 7. rem-step3-green

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_translate_nightly.py
```

```text
3 passed in 1.29s
```

### 8. rem-step4-red

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_translate_nightly.py -k status
```

```text
5 failed, 3 deselected in 1.26s
```

### 9. rem-step4-green

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_translate_nightly.py -k status
```

```text
5 passed, 3 deselected in 1.32s
```

### 10. rem-required

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_translate*.py tests/unit/test_rem_proactive_http.py tests/unit/test_rem_next_submit.py tests/unit/test_rem_config*.py -n 6
```

```text
2 failed, 349 passed, 1390 warnings in 113.74s (0:01:53)
```

### 11. rem-adjacent

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_live_reader.py tests/unit/test_rem_daily_round.py tests/unit/test_rem_languages.py -n 6
```

```text
3 failed, 167 passed in 43.72s
```

### 12. rem-rc59-red

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_next_submit.py -k rc59_semantic
```

```text
3 failed, 2 passed, 242 deselected in 19.33s
```

### 13. rem-rc59-green

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_next_submit.py -k rc59_semantic
```

```text
5 passed, 242 deselected, 18 warnings in 13.27s
```

### 14. rem-review-red

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive_http.py tests/unit/test_rem_translate_nightly.py -k 'waits_for or forecasts or menu_suggestion'
```

```text
3 failed, 1 passed, 19 deselected in 6.43s
```

### 15. rem-review-green

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive_http.py tests/unit/test_rem_translate_nightly.py -k 'waits_for or forecasts or menu_suggestion'
```

```text
4 passed, 19 deselected in 4.65s
```

### 16. rem-adjacent-final

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_live_reader.py tests/unit/test_rem_daily_round.py tests/unit/test_rem_languages.py -n 6
```

```text
1 failed, 169 passed in 17.38s
```

### 17. rem-command-red

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_translate_nightly.py -k request_command
```

```text
1 failed, 11 deselected in 1.85s
```

### 18. rem-command-green

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_translate_nightly.py tests/unit/test_rem_daily_round.py -k 'request_command or translates'
```

```text
3 passed, 44 deselected in 2.61s
```

### 19. rem-required-final

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_translate*.py tests/unit/test_rem_proactive_http.py tests/unit/test_rem_next_submit.py tests/unit/test_rem_config*.py -n 6
```

```text
361 passed, 1408 warnings in 58.81s
```

### 20. rem-old-translation-red

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_next_submit.py -k rc59_translation
```

```text
1 failed, 247 deselected in 7.75s
```

### 21. rem-old-translation-green

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_next_submit.py -k 'rc59 or legacy_config'
```

```text
8 passed, 240 deselected, 24 warnings in 11.59s
```

### 22. rem-required-complete

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_translate*.py tests/unit/test_rem_proactive_http.py tests/unit/test_rem_next_submit.py tests/unit/test_rem_config*.py -n 6
```

```text
362 passed, 1408 warnings in 69.30s (0:01:09)
```

### 23. rem-adjacent-complete

```bash
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit/test_rem_proactive.py tests/unit/test_rem_live_reader.py tests/unit/test_rem_daily_round.py tests/unit/test_rem_languages.py -n 6
```

```text
170 passed in 34.36s
```

## CLI and independent review

`co rem status --help` and `co audit --help` were inspected. The initially launched global `co audit co rem status` traversed the entire global command tree and was interrupted (exit 130); it is not counted as a passing audit.

The checkout command `uv run --quiet --python 3.13 --extra dev co rem status --help` passed and includes the queue/request explanation. Its exact last line:

```text
Back:     co rem --help
```

A targeted checkout audit used `connectonion.cli.audit.help_page`, `check`, and `looks` on `co rem status`, with real root/REM/status help pages and pipe/terminal rendering in temporary homes. Exact last line:

```text
co rem status audit: 0 findings; help, flags, example, read-only and terminal parity checked
```

`git diff --check` passed. The reader diff contains exactly one added POST call.

A separate AI reviewer inspected the code, tests and rendered CLI output from fictional temporary notebooks, then rechecked fixes. The review caught and verified fixes for rc59 task migration, busy-writer consent loss, and next-day budget forecasting. This was an AI review, not a human founder review. No desktop/mobile visual browser inspection was performed; the live/file JavaScript behavior was executed in Node.

## Limits and handoff

- The real notebook and `~/.co` were not changed. This branch has not been committed, deployed, or run against a real model.
- A network failure or writer lock exceeding the normal 600-second wait can still fail the single reader POST. The one-call-only reader scope does not add retry or error-display UI.
- Without a saved config snapshot, an old task can be accepted only when its raw/rc59 semantic hash matches current config. There is no unsafe reconstruction of missing task inputs, nor recovery of tasks already discarded.
- The main documentation and CLI help were updated. Separate Wiki/docs-site publication remains for the release owner.

The reviewer's isolated inline reproduction script exited 0 with the exact last line:

```text
review reproduction complete
```
