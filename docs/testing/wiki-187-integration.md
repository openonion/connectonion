# Wiki 1.8.7 consolidated acceptance — 2026-09-19

Review in #1454; source/lifecycle requirements #1443/#1523; undecided experience
in #1580. Reader #1587 is merged into the implementation branch. The branch also
includes current main (1.8.6); the Outlook merge preserves its `newest_first`
parameter, ascending returned rows and Wiki recipient fields.

## Single-project end to end

Synthetic Atlas is a local Python word counter, with README, implementation,
three-word input and recorded output. One synthetic Codex user message requests
a possible hosted website later. No private mailbox, historical notebook or
customer material is supplied.

The successful run passed through real `build_map` → source `gather` →
`co ai --harness codex --model gpt-5.6-luna` → new candidate → validator →
notebook replacement and investigation stamp. The model inspected the fixture
files and reran the sample command. Manual review confirmed:

- The opening is a short purpose, user-flow ASCII and runnable local entry.
- The sample result is `3`, with input/output and actual artifact paths.
- A request to consider hosting remains an open thread, not a claimed deployment.
- All canonical project headings occur once and references identify the supplied
  session, inspected local files, command result and runner coverage.
- Missing owner, test coverage, hosting details and edge-case behavior remain gaps.

[Actual resulting page](artifacts/wiki187/atlas-investigated.md),
[returned result and usage](artifacts/wiki187/atlas-result.json), and
[synthetic source files](artifacts/wiki187/atlas-source/README.md) are retained.
The `/tmp/wiki187-e2e` paths in the page are the actual acceptance environment,
not portable product links or a hosted service.

The first launch was blocked by the execution sandbox before model startup.
Two subsequent model candidates were rejected by validator bugs: local-file
references were not recognized, then the runner's `investigation:coverage` ID
was excluded. Both were fixed and regression-tested. The third model run
completed and promoted its page. The rejected drafts did not replace the page.
This is not a claim that every first attempt succeeds.

The successful invocation reported 752,276 input tokens, including 688,128
cached input tokens, and 7,342 output tokens. These are cumulative model context
counts, not unique source volume; only 456 source characters were initially
gathered before project-file retrieval. The overhead remains high, and neither
dollar cost nor total usage of the two rejected candidates was retained by the
older invocation path. Do not extrapolate a cheap batch or global success rate.
The updated runner retains execution and candidate-review sidecars for future runs.

Reproduce mapping without inference:

```bash
PYTHONPATH="$PWD" python scripts/validation/wiki_project_acceptance.py
```

Explicitly opt into one real provider run in a fresh directory (requires the
configured Codex CLI and subscription; use the intended checkout on PYTHONPATH
and the matching `co` on PATH):

```bash
PYTHONPATH="$PWD" python scripts/validation/wiki_project_acceptance.py --run-model
```

## Regression and reader

Focused Wiki/COAI/default-Skill/mail-window checks after merging current main:
**357 passed, 8 opt-in browser skips**. Command:

```bash
PYTHONPATH="$PWD" python -m pytest tests/unit/test_co_ai_harness.py tests/unit/test_codex_tool.py tests/unit/test_default_skills_are_for_customers.py tests/unit/test_wiki* tests/unit/test_mail_window.py tests/e2e/cli/test_wiki* -q
```

Reader: **14 passed** in real headless Chrome at 375×812, 768×1024 and 1440×1000.
Chrome initially could not start in the execution sandbox; the permitted retry
passed. [Desktop](artifacts/wiki187/reader-desktop.png) and
[mobile](artifacts/wiki187/reader-mobile.png) screenshots use synthetic content.

```bash
CO_WIKI_BROWSER_TEST=1 PYTHONPATH="$PWD" python -m pytest tests/unit/test_wiki_reader.py tests/e2e/cli/test_wiki_reader_browser.py -q
```

CLI help was checked for Wiki init, Gmail search, Outlook search, OpenOnion email
addresses/inbox/sent, and browser tab open. A wheel builds with the available
Hatchling (`python -m build --wheel --no-isolation`); isolated dependency fetching
was blocked by network access. `git diff --check` passes.

## Full-suite limits

The first full run, before the main-base merge, on Python 3.14.7 under the
execution sandbox: **9,645 passed, 577 failed, 27 skipped, 21 errors**. No Wiki
failure appeared in its failure summary. Failures include blocked sockets and
browser processes, dependency-install errors and event-loop/order-sensitive
failures. On unmodified main-PR head `6651e7a1`, the representative transport,
WebSocket ping, tool-executor and Wiki-runner group produced 61 passes and the
same 3 socket permission failures. That reproduces those three, not all 577;
some asynchronous tests passed in isolation. The full suite is not green.

The post-main-merge full-run result is recorded below when it finishes.
