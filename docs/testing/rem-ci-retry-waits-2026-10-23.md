# Synthetic REM retry waits — CI issue #2134

## Actual bottleneck evidence

Three recent Python 3.12 coverage jobs used two pytest workers:

| PR | Run / job | Pytest elapsed | Passed / skipped | Coverage |
| --- | --- | --- | --- | --- |
| #2621 | 39896113527 / 120226855329 | 662.24 s | 17,090 / 337 | 86.24% |
| #2655 | 39899262566 / 120237146294 | 781.82 s | 17,113 / 337 | 86.26% |
| #2657 | 39902286189 / 120246332074 | 771.35 s | 17,125 / 337 | 86.25% |

These are neighboring PR heads, not controlled same-code before/after benchmark
runs. The workflow already runs Python 3.11–3.13 concurrently, uses pytest-xdist,
and cancels superseded PR runs. The 3.12 job includes coverage; observed timing
alone does not isolate coverage overhead from runner capacity and variance.

The final two logs list three synthetic failure cases taking 14, 14 and 15 seconds:
listing retry backoff requests 2/4/8 seconds; investigation requests 1/2/4/8 seconds.
These tests simulate failure and recovery, not real network timing. Sleeping adds
elapsed time without testing the wall clock. The production retry policies are
unchanged.

## Bounded correction and same-command comparison

Only these tests replace the sleeper with a per-test delay recorder. They assert
exact requested delays, exact final-failure attempt counts, and no final extra
sleep, alongside the existing retained-year, healthy-source and coverage checks.
The Graph fixture uses its existing root-domain query, not Gmail's bare domain.
An initial added assertion incorrectly expected the Gmail query for Graph; that
assertion was corrected. It was a test author error, not a production defect.

On unchanged main fad11f62, the existing three tests passed in 45.76 seconds
(15.03/14.03/14.01-second calls). After the change the identical command passed in
0.68 seconds (3 passed, 237 deselected). No fabricated functional red failure is
claimed: the baseline problem was measured waiting time.

```bash
PYTHONPATH=. TERM=xterm-256color OPENONION_API_KEY=test-key python -m pytest \
  tests/unit/test_rem_investigate.py tests/unit/test_rem_scan.py \
  -k 'test_a_mailbox_that_fails_is_a_gap_in_coverage_and_the_other_mailbox_is_still_read or test_all_history_keeps_completed_years_after_a_later_connection_failure' -q
```

The key is a fixed non-secret test fixture value. No provider or model is called.
Related/full regression, independent exact-head review and remote CI: pending.

## Limits and remaining work

A 43-second reduction in serial simulated waiting does not establish the same
critical-path improvement in parallel CI. Whole-job before/after times and runner
minutes must be measured separately. This does not complete #2134's controlled
sharding experiment, replace native REM acceptance or establish product maturity.
No production code, CI topology, timeout, retry policy, coverage floor, assertion
about retained data, release gate or required test was removed or weakened.
No runtime feature or package version changes; no separate public Design Journal
is needed for this internal test-only maintenance change.
