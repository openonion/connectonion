# 1.9.3rc8 candidate verification

## Source and scope

Both maintenance fixes merged after separate AI source review and 27 green checks each:

- #2551: `f8e5784e80e79dbf02b9ccfae26e9b44145488c8`; subject-aware contact-date and extracted-packet restoration.
- #2552: `000e4b96481ddb8e700dc4567ca7ea7f11e7a20e`; bounded runner-owned status summary. #1988 remains open for article-length/content-quality work.

The local release preparation began at reviewed branch head `17742b4bb25e99908330a843da39b6ba9a38d8a7`. Its source tree was verified identical to the merged main tree `1ab8fde8ea4f16531c97fe62e8f039cff6ddab6f` before version metadata was prepared. The version PR will carry the release metadata and documentation over the merged main commit. No tag or public release is established by this local record.

## Commands and results

Candidate version/release consistency:

```text
python -m pytest tests/unit/test_the_version_agrees_with_itself.py tests/unit/test_every_release_has_an_entry.py -q
20 passed, 1 skipped in 0.83s
```

The skipped check needs the separate docs-site checkout. Post-publication tag sync remains required; stable stays 1.9.2.

```text
uv lock --check --offline
Using CPython 3.11.16; resolved 118 packages in 4 ms
python scripts/check_release_visuals.py v1.9.3rc8
OK: backend data-maintenance exemption
python -m build --outdir dist
Built wheel and sdist
python -m twine check dist/connectonion-1.9.3rc8.tar.gz dist/connectonion-1.9.3rc8-py3-none-any.whl
Both PASSED
```

Fresh isolated installed-wheel test with declared dependencies, using the complete local wheelhouse, no system-site inheritance and no dependency omission:

```text
PIP_NO_INDEX=1 PIP_FIND_LINKS=/tmp/rem-rc7-wheelhouse python -m pytest tests/e2e/test_the_wheel_works_when_installed.py -m slow -q
13 passed in 16.26s
```

Full offline source suite on CPython 3.11.16:

```text
TERM=xterm-256color OPENONION_API_KEY=test-key python -m pytest tests/ -n 4 --dist loadfile -m "not slow and not real_api and not network" -q
16070 passed, 160 skipped, 7 warnings in 123.81s
```

The actual flags separate `-n 4`; the fixed `test-key` is the same non-secret dummy used by CI, not a production credential. Global test fixtures isolate HOME and prohibit nonlocal connections. Browser, external integration and platform-specific skips are not acceptance. The warnings are retained in the local report; none was disabled to pass.

An initial local run used TERM=dumb and omitted the CI dummy value, producing 11 failures: six explicit terminal-colour checks and five Agent-construction checks. After correcting only that test environment, all 11 failed cases passed in 1.35s; the full run above then passed. No implementation test, timeout, dependency or marker was waived. The initial failed report remains locally available.

The initial 20/13 test records precede this summary; a second isolated installed-wheel run passed 13 tests in 18.76s after it was added. Final documentation refinements pin evidence links to the release tag because docs-site sync does not copy acceptance/design-evidence directories. Final candidate artifacts are rebuilt and the installed-wheel checks repeated before the version PR; that final result belongs in the PR. Code and version metadata remain the tested source. `git diff --check` passes.

## Product evidence boundaries

The real saved-page/source review is the separate dated product audit, not this synthetic suite. All 252 currently matching REM issue bodies were re-fetched; the previous 251-body snapshot is unchanged except for the newly authored #2550, now closed. Not every comment or every real page was semantically reviewed. No private page content is included here.

No real init, new provider/mail collection, model investigation, scheduler run or real Markdown notebook rewrite. A prior attributed local correction record was saved and verified, not treated as an applied page correction. A separate deterministic reproduction confirms the correction-only empty-source early return in #2334.

No new screenshot or browser acceptance. The blocked local-preview route was not retried through another renderer, protocol or browser. The backend exemption acknowledges that future fact/status values can change; reader markup, styles, layout and source-modal focus are unchanged. PR2546 remains outside this candidate. Independent AI review accepted this precise exemption; no real human founder participated.

Remaining release gates: exact version-PR review/CI, immutable annotated tag on its reviewed merge, Trusted Publishing release workflow, public artifact equality, exact-pin install of CLI and scheduled runtime, and docs-site tag sync/canonical URL verification. This candidate does not establish nightly usefulness, current-page truth, instant correction apply, morning recall, mobile or accessibility maturity.
