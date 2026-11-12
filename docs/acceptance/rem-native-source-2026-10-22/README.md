# Native Scheduled: source and data compatibility — 2026-10-22

## Result and correction

**The native data structure can be reproduced.** The lack of a public App Server
schedule method does not establish that direct data integration is impossible.
The preceding live legacy-file probe established only that no adoption/execution
was observed within that window. It did not test the scheduler's enable gate.

This follow-up executed the installed desktop application's own storage,
RRULE calculation, due-selector and scheduler-loop functions in isolated data
roots. It did not write the owner's automation directory or database.

## Source provenance

- Public `openai/codex` checkout: `342ed69a174c206c1de52a59491b131e0753cfa5`.
  Searching the public tree found `automation_update` in dynamic-tool discovery
  tests, not a desktop Scheduled persistence/loop implementation. The public
  repository contains the CLI/App Server; those tests show desktop tools can be
  injected dynamically and routed back to the client.
- Installed desktop App version: `26.924.22138`. Implementation inspected from
  its bundled `.vite/build/src-BSSLXJxP.js` and `main-C5425b_s.js`. These are
  shipped compiled JavaScript, not a claim that desktop sources are in the
  public repository. No desktop implementation is redistributed here.
- Storage module SHA-256:
  `50c7cf9c144594cfa6f33298e977f0b144976cc70c579f59fdc7242615c4af98`.

## Creation and loading

Legacy creation (`ml`, exported `kn` in this build) writes a version-1 TOML
under `<CODEX_HOME>/automations/<id>/automation.toml` and upserts the local SQLite
`automations` table. Required definition fields include id/name/prompt/status,
created_at/updated_at in milliseconds, and cron execution settings: RRULE,
model/reasoning effort, local/worktree environment and cwd/project target.
The table also has computed `next_run_at`, `last_run_at`, JSON-encoded `cwds`,
owner account/user/installation identifiers, legacy identity and `auto_archive`.

**Direct SQLite insertion is not always needed.** In legacy mode, the native
loader reads valid files and `ll()` can reconstruct their index rows. This was
proved by deleting only the isolated task's index row, then calling the native
list function: the same file was accepted and the row recreated.

After completed owner migration, `Nc` switches the loader to account-, user-
and installation-scoped rows and filters legacy files out. `saveAndVerify`
first POSTs to `/automations/save` with `executor=local`, `installation_id`,
`legacy_automation_id`, VEVENT-wrapped RRULE, enabled flag and
`local_configuration` (target, compatibility_cwds, execution_environment,
local_environment_config_path, plugin_template_id). It then GETs
`/automation/<id>` and compares the saved definition before caching it.
`syncOwner()` refreshes the canonical list and removes scoped cache rows absent
from that list. Thus copying a local row with owner identifiers is insufficient
for durable migrated-mode registration. No live account identifiers were copied
or invented for the owner's database.

## Source-level compatibility checks

The harness imports the actual bundled storage functions and uses real
`better-sqlite3` in a fresh temporary CODEX_HOME. The Electron app surface and
process-version presence are stubbed only to run these functions outside the
GUI; no existing user data is loaded. Checks passed:

1. Native create writes file and database; native list accepts the definition.
2. Native RRULE code computes the future run; its due selector includes it.
3. Pause excludes the task from due selection; native delete removes both stores.
4. A file alone recreates its index in legacy mode.
5. Completed owner migration hides legacy tasks; a correctly scoped isolated
   row is visible, then canonical-list pruning removes an unregistered row.

The scheduler test evaluates the unmodified `xae()` loop and `As()` next-slot
function extracted from this same build. With its capability flag false, an
already-due native task is not dispatched. Setting capability true dispatches
it and updates native run-time state. Only the final model-turn execution
boundary is replaced by an isolated marker writer. This confirms that correct
persisted data alone does not turn the desktop scheduler on. It does not prove
that this flag was false during the earlier live probe.

See `store-result.json` and `tick-result.json`. The harness source is included;
its temporary bundle paths are prerequisites, not a portable product adapter.
No private desktop code, credential or new service configuration is included.

## What remains

This is **source-level compatibility**, not a live desktop end-to-end pass.
Native UI visibility, the running owner's scheduler capability, actual model
turn dispatch, sleep/wake and migrated-mode backend registration remain to be
checked. A product adapter can follow the legacy file format without creating
another clock, but it must distinguish legacy from migrated mode and must not
announce “running” or remove the existing REM trigger on a file-write alone.

## Independent review

A separate AI reviewer, in a technology-founder/marketing/UI role, reviewed the
report and both result records. It found no blocker in these bounded claims.
Its recheck criterion is live desktop capability and task visibility, actual
model-turn execution, and migrated-mode backend registration/persistence before
calling the integration running. It did not inspect native UI or certify an
end-to-end pass. This is an AI role review, not a claim of human participation.

## Follow-up: Python support and the renderer capability gate

Python 3.10 reached upstream end of life on October 1, 2026
(https://peps.python.org/pep-0619/). The recommended compatibility policy is to
raise the minimum to 3.11 in a clearly documented release, update installers,
package classifiers and the CI matrix together, and publish Pillow >=13.0.0 as
a dependency floor as well as updating the lockfile. Existing Python 3.10
installations are not forcibly changed; their old releases remain available,
but must not be described as receiving current security support. Pinning an
unpatched Pillow or maintaining a private backport is not recommended.

Pillow is used by browser image tools as well as arriving through python-pptx
and the WhatsApp extra. Making only python-pptx optional therefore does not
remove the compatibility problem. No compatibility metadata has been changed
by this investigation.

Additional read-only local observations:

- `codex features list` reports `in_app_local_automation` enabled.
- `lsof -p 93137` confirms the running desktop main process has
  `~/.codex/sqlite/codex-dev.db` open. This rules out checking the wrong database
  for that process; it does not prove the scheduler is enabled.
- The installed renderer sends `automations.local.isCapable` to
  `localAutomationsScheduler.setCapability`. That capability combines the
  `in_app_local_automation` feature with a native local-access policy.
- The native policy checks allowed local access, a local host, and, when its
  rollout is enabled, `chatgpt.workspace.feature.codex-local-automation.access`.
- `verify-capability.cjs` executes that exact policy expression with injected
  state, covering six combinations. These are isolated policy tests, not
  observations of the running renderer. The prerequisite extracted shared
  renderer bundle is `/tmp/rem-native-renderer/app-shared-36eae88777f2.js`;
  the source bundle is not included in this repository.

The policy tests pass, but the live renderer's capability, migration owner
state and automatic execution remain unverified. Do not change enterprise
policy or patch the desktop to force capability. The next live check is to
open the desktop Scheduled/Automations page, create an isolated task through
its native path, and observe both its scheduled run and output marker. The
previous no-run probe is still a failed end-to-end check. Keep the existing
REM launchd job until the native trigger passes.

Current official scheduling documentation also requires the machine and
app to remain running for local project tasks:
https://learn.chatgpt.com/docs/automations?surface=app . Native scheduling
therefore changes the availability contract compared with launchd; this
must be stated in the migration experience, not silently hidden.

Compatibility implementation touchpoints found: `pyproject.toml` requires-python,
Python classifier and Ruff target; `uv.lock`; Python matrices and audit runtime
in `.github/workflows/tests.yml`; and `install.sh`, whose current `uv tool
install` does not select a Python version. The installer should deliberately
select a supported interpreter instead of retrying an incompatible pinned RC
as if the package had not appeared on PyPI yet. Validate both upgrade from a
3.10 installation and a fresh install without changing system Python.

Independent AI role review (technology founder, marketing and UI): the
compatibility recommendation and distinction between isolated and live tests
are sound. P1: synchronize interpreter/dependency floors across install, CI,
metadata and docs, and verify fresh installation plus upgrade. P1: obtain live
native registration, automatic execution and marker evidence before migration.
P2: retain the isolated-policy coverage label. Review inspected the evidence
summary, not the live renderer or native UI; it did not reproduce the runs.

## Second live smoke test

The owner's request to test automatic scheduling was followed by a fresh
150-second live test. A unique ACTIVE legacy definition used
`FREQ=MINUTELY;INTERVAL=1` and a temporary local workspace. Its prompt permitted
only a Python script writing an execution marker. The running desktop's
read-only SQLite connection was queried every ten seconds for that exact id.
All 16 observations had no automation row, no run and no marker. The test
failed; see `live-retest-result.json`. Test definition and workspace were
removed; existing tasks were not modified and no database writes were made.
This verifies failure of this registration path, not that every native
scheduling path is broken. No native rendered UI was inspected.

Independent AI trial review (founder/marketing/UI role, evidence summary only)
classifies this as a high-priority release blocker: users must not be promised
native scheduling before exact-id registration, scheduled execution and marker
creation are observed. Reviewer assessed observations through 90 seconds and
requested the final check; the completed 150-second result remains negative.
No definitive cause or native UI pass was claimed.

## Native creation entrypoint and transport authorization

The installed desktop exposes the bundled `codex-app-tools` MCP plugin
(version 0.1.5 is present locally). Its unmodified `server.mjs` forwards
`tools/list` and `tools/call` through `CODEX_APP_TOOLS_PIPE_PATH`. The
`automation_update` tool reaches the desktop automations service; it is a
better candidate than reproducing private SQLite mutations. Source inspection
confirms that service creation uses native storage in legacy mode, or
canonical save-and-verify followed by local caching in owned mode.

The running desktop's startup log identifies its tool pipe. A read-only
`tools/list` request to that exact pipe was closed without a response; the
matching desktop log at 2026-10-22T07:07:44.086Z reports
`dynamic_app_tools_peer_rejected reason=untrusted-process-ancestry`.
`native-entrypoint-result.json` records the result. No mutation request was
sent and no peer authorization was bypassed. This establishes why this
external process cannot call the native tool transport; it does not establish
why the earlier file-only smoke test was not adopted.

Available routes and decisions:

- Desktop-native `automation_update`: preferred registration path. Requires a
  desktop-authorized caller and still needs real scheduled execution testing.
- Legacy TOML: native source compatibility is established, but two live probes
  failed. Do not make this the default installer without adoption verification.
- Direct owned SQLite insertion: rejected as an integration strategy because
  canonical synchronization can remove rows that were never registered.
- Public CLI/App Server: the inspected protocol has no scheduling CRUD method;
  reuse it for execution, not as an assumed native scheduler API.
- Maintaining a copied/forked scheduler: technically separate work, but adds a
  scheduler to maintain and does not validate the running desktop's Scheduled.
- Existing launchd trigger plus archived REM execution: retain for continuity
  until native registration and execution pass; do not label it native.

An isolated acceptance workspace and a ready-to-use desktop-native task prompt
are prepared at `~/.co/rem-trials/native-schedule-acceptance`. The probe script
was syntax-checked but deliberately not executed by hand, so a future marker
can provide useful scheduled-run evidence. Creating that task in a normal
desktop chat is the next supported live test. Current tools have no native UI
control or authorized desktop tool transport, so this last step remains open.

Independent AI role review (founder, marketing and UI; supplied evidence only)
found the claims bounded correctly. P1: scheduled handoff remains unverified;
recheck exact-id registration, scheduled execution and marker before changing
REM defaults. P2: syntax checks are not execution evidence, and native desktop
flow remains uninspected. No product UI or release pass is claimed.

### Official MCP launcher recheck

The unchanged bundled codex-app-tools 0.1.5 launcher was then tested over its
normal stdio MCP protocol, with its documented tools-pipe environment variable.
MCP initialization succeeded, but tools/list returned `Codex app tools pipe
closed`; the matching desktop log at 2026-10-22T09:18:59.223Z again reports
`untrusted-process-ancestry`. This confirms that switching from a direct pipe
probe to the official client did not authorize this execution environment.
No automation mutation was attempted, no App permissions were changed, and no
native scheduling success is claimed. See `official-mcp-result.json`.
