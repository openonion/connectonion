# Windows task paths: source boundary review

## Baseline and scope

Source-inspected published 1.9.3rc6 and main `32dd0782a3ac22f33f5c5b02dc06ac2b6c42cf08`. The collector already excludes POSIX REM task paths. Issue #2318's original missing exclusion must not be described as wholly unfixed. This follow-up addresses Windows-shaped task paths and the separate slash-only checks used for skill counts and cached samples.

## Failure and correction

Synthetic Codex metadata with `originator: connectonion` and a drive/UNC task cwd allowed a model probe into user input; Claude repair rows did the same. Ten new collector cases failed before the patch. A cached invocation test also counted two internal tasks. No private rollout was inspected, so this is a deterministic source-import reproduction, not a measured current-user contamination report.

Task detection now interprets drive/UNC cwd with Windows path semantics, independent of the reader's operating system. It handles backslashes, mixed separators, the task root and Windows case variations. POSIX paths retain case-sensitive matching. Counting and sampling reuse the same predicate, including cached entries. No cache reset or broad rescan is needed.

## Verification

- 56 focused tests pass: the existing source-import and skill-sampling suites plus drive/UNC, mixed separator, task root, Windows case, similar user-directory and ordinary Windows user-session controls.
- Local command: `python -m pytest tests/unit/test_rem_source.py tests/unit/test_rem_skill_usage.py -q`.
- Local harness overlays the two main-source modules on public 1.9.3b5 package dependencies; it does not claim a complete rc6 installation or full-suite result. CI tests the submitted tree.
- Native Windows first-run, real sessions, model execution, mail, night scheduling and product usefulness: not exercised. Existing user preference leaves real first-run testing manual.
- Screenshots: not applicable to the changed collector/metadata path; no reader/layout changes and no browser/rendering attempted. Prior source-modal browser acceptance remains separately pending in #2546.

## Product impact and limits

Prevents these internal prompts from becoming newly imported context or sampled skill evidence. It does not purge already imported messages, repair claims derived from them or prove first-run completeness. Such existing evidence needs an explicit review, not a silent memory rewrite. Nightly reliability, durable morning recall, mobile and accessibility acceptance remain open under the product audit.

## Independent review

A separate AI source reviewer found no blocking regression. It confirmed drive/UNC semantics, POSIX case preservation, exact segment matching, preserved user sessions and filtering of warm cached events without a cache-version bump. Windows root-relative paths without a drive are not covered; normal absolute producer cwd has a drive or UNC share. No native Windows or rendered-page pass is claimed.
