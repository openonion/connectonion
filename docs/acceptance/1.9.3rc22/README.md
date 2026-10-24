# 1.9.3rc22 acceptance

The candidate combines native initialization/lifecycle PR #2674 and complete
local onboarding PR #2677. It retains the stable 1.9.2 channel.

## Native desktop

Normal installed Codex 26.924.22138, Intel macOS, normal profile/login, managed
App Server 0.164.0. No isolated app or version replacement was used.

- Opening Scheduled in the running app was followed by native execution,
  marker creation, automatic archiving and independently acknowledged pause.
- An early deep-link alone failed in a desktop cold-launch control. Delivering
  Scheduled after adoption passed after another guarded normal desktop restart.
  The managed App Server remained alive. Requested 20:35 Sydney; native index
  due 20:36:33; execution 20:36:34.536; auto-archive 20:37:11.215. The owned task
  was paused and its definition removed.
- The production scheduled REM pass completed at 09:13:37 UTC. The native wrapper
  auto-archived and its command execution items reported exit 0. Its task remained
  ACTIVE after the restart; no launchd job was installed or loaded for it.

The detailed [24 October follow-up](../rem-native-init-2026-10-24.md) retains
negative controls, source observations and compatibility boundaries. These
receipts preceded the release version stamp; a public-package recheck remains
a separate publication step.

## Regression and installation

Scheduling/service/CLI command checks: 262 passed, 3 existing deprecation
warnings. Help contracts: 123 passed separately. The added migration-during-open
test reproduced clock removal before the fix. Independent AI role review
verified the corrected guard, concurrent definition/index changes, ACTIVE
updates and normal PAUSED handover.

Onboarding: 189 focused tests passed; 16 installed-wheel subprocess trials passed
before the version stamp. The final selector/profile guards passed their focused
checks. Full CI found one old subscription test still patching a removed path
constant; it was updated to select the runtime root, and the 25-test recheck
passed. No live auth or account publication was performed by those trials.

Full integrated-suite, candidate wheel and publication results are recorded
below as they complete. Pending work is not represented as a pass.

## Visual review

The independent reviewer is an AI role using technology-founder, marketing and
UI criteria; no human founder participation is claimed. The four complete
onboarding guides, fourteen actual rendered desktop/phone views, Markdown
exports, navigation and copy affordances were reviewed. The recorder exercised
real clipboard reads/writes, a real Markdown download, section jumping and menu
open/close. Guide source/public/HTTP parity passed for all four.

The native guide and journal have separate actual rendered captures. These
show documentation, not the native Codex Scheduled UI. Per-release images and
their exact scopes are listed in `docs/releases/assets/v1.9.3rc22/manifest.yml`.

## Remaining boundaries

Exact requested-minute timing, live account-managed creation/update/pause and
migration, full server/machine restart recovery, sleep/wake, actual native UI
and remote project-history presentation remain unverified. Screenshots are
sample coverage, not an all-page pass. Windows symlink/copy behavior and live
auth are outside the local onboarding trials.
