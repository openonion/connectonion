# Native REM next/submit review

This is an independent AI role review from the perspective of a technology
founder with marketing and UI experience. No human founder participated.

Inspected actual CLI states: next/submit help, pending task, literal citation and
markup-like evidence, paths containing spaces, JSON, round done, refused output,
and successful resubmission. No web pages changed; desktop/mobile page review
does not apply. Model answers and source services were faked in temporary
notebooks. No live notebook or real model was used.

| Priority | Problem and user impact | Evidence | Improvement and recheck |
| --- | --- | --- | --- |
| P1 | Rich markup could corrupt evidence or crash pending-task output. | A literal `[/unknown]` raised `MarkupError`. | Print task text verbatim. Actual pending/JSON output now preserves `[1]`, JSON brackets and markup-like text. |
| P1 | Abandoned work could bypass the cap, and task records were invisible to logs. | Task IDs did not match the existing `run_` log convention. | Reserve compatible run records when tasks are issued. Tests check abandoned-call accounting and unknown usage. |
| P1 | Whole-notebook output, relative translation paths and merge deletions were lost. | Actual stage interfaces use different output forms. | Explicit task outputs, a checked page map for whole-notebook work, and deletion promotion. Real maintenance, translation and same-person regressions pass. |
| P1 | Refused first-page work could change state before the next pending page. | Caller loops can swallow a refusal before unwinding. | Inspect stage results as well as run records before promotion. A two-page regression verifies byte-for-byte unchanged canonical state. |
| P1 | Replayed answers could consume replacement evidence. | A search changed a body while retaining its source ID, count and file path. | Hash supplied material and referenced evidence bodies. The real search-follow-up regression refuses the stale answer without advancing progress. |
| P1 | Snapshot capture clocks made stable repository evidence look changed. | Real project packet preparation stamps every read. | Normalize capture metadata while retaining source dates, revisions and text. Independent real project preparation now reaches the normal validator. |
| P1 | Hitting a cap before a required audit discarded an unchecked answer and claimed success. | A writer-plus-audit fake round with cap 1 reproduced the loss. | Refuse with an explicit pause reason and keep the original editable task. The regression resumes after the daily reset and finishes the audit. |
| P1 | Private-copy locks did not protect canonical source collection. | Preparation originally ran outside the canonical lock. | Hold the canonical lock during CLI computation and release it before task return. Private stages share that ownership. |
| P2 | Follow-up tasks omitted original instructions/evidence; snapshots accumulated. | Resumed child calls carry only the next-turn text. | Include original context and earlier replies; remove disposable copies on completion or supersession. Regression tests cover both. |
| P2 | The pending footer pointed to next, suggesting abandonment. | Actual rendered task had a misleading next action. | Pending output now points to its submit command; done output points to status. |

Remaining limits: no live Scheduled trial, no real model quality comparison,
and no large-notebook performance trial. Replaying an operation can repeat
read-only collection; changed inputs require a fresh plan. Private notebook
copies add disk and I/O cost until the phase completes or is superseded.

Validation used `uv run --python 3.13 --extra dev`:

- `python -m pytest -q -n auto tests/unit -k rem`: 4,732 passed, 2 failed.
  The failures are the macOS wake-process detection test and forced browser
  process cleanup test. Both reproduce separately; this sandbox denies `ps`
  and cannot provide the expected LaunchServices/process-inspection behavior.
- CLI audit, general CLI help, and REM help contract: 153 passed.
- Native round suite: 23 passed, independently rechecked.
