# Jira source feature — development scope

Branch: `feature/jira-source-20261106`. Team baseline: `049a74e81c0f347dddf1d2c1378d970d950e481e`.

## Delivery decision

One eventual upstream PR per complete source feature: CLI/auth/scope and local records → existing source approval/Init → Investigate/Maintain through configured runner → existing Reader and resolvable original citations. Complete and verify this source before submitting. No upstream PR is created by this branch reorganization.

## Current status

Jira CLI and normal approved local-import Init/Investigate/Maintain integration implemented. Real read-only snapshot generated a project and person; repeat consumed zero items. Real edited-source end-to-end acceptance and original-link click-through remain pending. The user desktop screenshot confirms list visibility only.

Historical CLI receipts stay in `jira-cli-remediation.md`. They apply to their recorded commits; do not label old runs as fresh results for this branch. The Jira REM implementation was transferred with original commit provenance from `d689422f0` onto the Jira CLI branch; no sibling CLI remediation commits were merged. See `jira-rem-workflow.md` for model-proof scope and limits.

## Remaining acceptance

- Reuse the customer's existing approval, stage/page Skills, configured runner/model, locks, quotas and recovery. Remote sources stay read-only.
- Verify selected identity/scope, first/repeat/changed content, immutable citations and correct failure progress. Retain authorized fields and the source-specific privacy boundary.
- Prove normal CLI → REM → existing Reader with representative authorized source data; inspect detail/source navigation and desktop/mobile states. Synthetic or old CLI tests are separate evidence.
- Keep generated knowledge in existing semantic categories. Do not add a source-named category, separate scheduler, Reader-open sync hook or mandatory demo bridge.
- Record final source Skill/model trials, focused regressions, CLI audit, known failures and terminal/UI evidence on the exact candidate.

## Branch and upstream boundary

The three feature branches have independent deltas above the common team develop base, which already contains other-source and shared code. They are not yet clean upstream PR diffs. At submission time select/refresh the real upstream base, port only this complete source feature and necessary common dependencies, retain client behavior, and retest. Shared groundwork belongs to a documented common dependency; do not import another source's whole feature branch just to reuse it.

The former four active branch names are retired after atomic remote verification. Original tips and combined integration history are preserved by local `archive/source-reorg-20261106/*` tags. Develop is not merged or moved.

## Post-transfer verification

Jira/REM/Reader-core and CLI-help selection: **1,298 passed / 1 known baseline failure** (`test_first_batch_runs_before_the_clock_is_installed`, reproduced before this reorganization). All 29 Jira integration regressions passed. REM implementation/Skill/test files are byte-identical to the prior combined candidate. No new live/model/browser run was performed during the branch transfer. Historical mixed-tree counts are not this independent branch's result.
