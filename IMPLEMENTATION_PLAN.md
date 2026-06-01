# Implementation Plan

## Remove Claude Runtime Skills From co-ai

1. [x] Remove `.claude/skills` from runtime `_get_skill_paths()`.
2. [x] Remove `.claude/skills` from runtime `_discover_all_skills()`.
3. [x] Add a regression test that a Claude-only skill is not invoked by slash command.
4. [x] Run focused skills/deploy tests, syntax checks, and diff hygiene checks.
5. [x] Update `TASKS.md`, `STATUS.md`, and this plan with the result.

## Require co-ai User Approval by Default

1. [x] Remove default `auto_approve=True` from generated co-ai deploy entrypoints.
2. [x] Remove default `auto_approve=True` from local `co ai` web server startup.
3. [x] Add regression assertions for generated entrypoints and web startup kwargs.
4. [x] Run focused co-ai/deploy approval tests, syntax checks, and diff hygiene checks.
5. [x] Update `TASKS.md`, `STATUS.md`, and this plan with the result.

## Split co-ai Deploy Packaging Helpers

1. [x] Add a dedicated `deploy_co_ai.py` module for co-ai deploy package construction and deploy-time skill/env helpers.
2. [x] Update `deploy_commands.py` to import/re-export those helpers while retaining project deploy packaging and upload orchestration.
3. [x] Run focused deploy tests, syntax checks, and diff hygiene checks.
4. [x] Update `TASKS.md`, `STATUS.md`, and this plan with the result.

## Explicit All-Skills co-ai Deploy

1. [x] Add failing tests for discovering all project/user deploy skill names with project priority.
2. [x] Add failing package-builder coverage for `all_skills=True`.
3. [x] Add failing CLI coverage for `co deploy --all-skills` auto-selecting co-ai.
4. [x] Add failing CLI coverage rejecting `--template project --all-skills`.
5. [x] Implement `discover_deploy_skill_names()` and wire `all_skills` through package creation.
6. [x] Add the `--all-skills` Typer option and deploy handler validation.
7. [x] Run focused deploy tests, syntax checks, and diff hygiene checks.
8. [x] Update `TASKS.md`, `STATUS.md`, and this plan.

## Deploy Timeout and Package Build Simplification

1. [x] Confirm 524 root cause from current code path: POST `/api/v1/deploy` awaited SSH upload, Docker build/run, Caddy route update, and cleanup.
2. [x] Change oo-api deploy POST to create a deployment row and return `deploying` before slow build work.
3. [x] Detach the slow deploy build from the POST request and preserve status polling via the existing status endpoint.
4. [x] Remove forced Docker `--no-cache` from backend deploy builds.
5. [x] Simplify the generated co-ai Dockerfile so it copies only install/runtime inputs instead of `COPY . .`.
6. [x] Run focused deploy tests and syntax/diff checks.
7. [x] Update `TASKS.md`, `STATUS.md`, and this plan with the local fix result.
8. [x] Deploy oo-api change to production and verify real `co deploy` no longer 524s.

## Hosted co-ai Browser Uses Chrome Channel

1. [x] Confirm the current deploy path installs/uses default Playwright Chromium.
2. [x] Add an explicit browser channel option to `BrowserAutomation`.
3. [x] Wire hosted co-ai deploys to `browser_channel="chrome"`.
4. [x] Install Chrome in generated co-ai Dockerfile.
5. [x] Install selected skill `requirements.txt` dependencies during co-ai image build.
6. [x] Upload allowed API keys from project/global/shell env sources for co-ai deploy.
7. [x] Make `auto_approve=True` actually bypass tool approval without enabling ULW continuation.
8. [x] Add/update focused tests.
9. [x] Run focused tests and syntax checks.
10. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## co-ai Deploy Installs Packaged Source

1. [x] Identify that co-ai deploy still installs published `connectonion==version` instead of the packaged local source.
2. [x] Add local package metadata to the co-ai staging package.
3. [x] Change co-ai generated requirements/Dockerfile to install the local package and its declared dependencies.
4. [x] Update package-builder tests.
5. [x] Run focused deploy tests and syntax checks.
6. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## co-ai Deploy Browser Runtime

1. [x] Confirm the deployed browser failure is caused by package/runtime image construction.
2. [x] Generate a co-ai-specific Dockerfile that installs Playwright Chromium during image build.
3. [x] Add package-builder regression coverage for the generated Dockerfile.
4. [x] Run focused deploy tests and syntax checks.
5. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## Restored Running Session Stop State

1. [x] Inspect the restored-session UI state and loading derivation.
2. [x] Add SDK-side local settling for restored running items when `stop()` is called.
3. [x] Add oo-chat loading derivation from active restored UI items.
4. [x] Add focused regression coverage and run builds/lints.
5. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## Chat Input Stop Button

1. [x] Inspect current chat input and SDK lifecycle to find the narrow stop boundary.
2. [x] Add a non-destructive `stop()` method in the SDK that closes the active WebSocket and returns local state to idle.
3. [x] Wire `stop` through `useAgentForHuman`, `useAgentSDK`, `Chat`, and `ChatInput`.
4. [x] Render stop in the send-button position while loading.
5. [x] Run TypeScript builds/lints and diff hygiene checks.
6. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## Deployed Slash Skills Use Agent co_dir

1. [x] Add a failing plugin regression test for slash invocation loading from `agent.co_dir` when cwd differs.
2. [x] Update skill path resolution so `_load_skill()` accepts `co_dir` / project context and preserves cwd fallback.
3. [x] Route `handle_skill_invocation()` and the `skill()` tool through the agent-aware loader.
4. [x] Make generated co-ai deploy entrypoints pass an absolute package `.co` path.
5. [x] Run focused skills, co-ai, and deploy tests plus diff hygiene checks.
6. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## Frontend Reads Relay Profile for Hosted co-ai

1. [x] Add a failing TypeScript SDK regression test for relay profile metadata when direct `/info` is unreachable.
2. [x] Update SDK endpoint/type handling to read `/api/relay/agents/{address}/profile`, normalize tools/skills, and merge it with direct `/info`.
3. [x] Update `oo-chat`'s `use-agent-info` hook with the same relay-profile fallback and normalization.
4. [x] Align Python relay profile tools with the SDK string-array shape and update focused Python tests.
5. [x] Run targeted SDK, frontend lint, Python tests, and diff hygiene checks.
6. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## Named co-ai Deploys Publish Relay Profile Metadata

1. [x] Add failing tests for `co deploy --name ... --skills ...` propagating the name into upload data and the generated entrypoint.
2. [x] Add failing tests for `create_coding_agent(name=...)` and relay profile construction from hosted agent metadata.
3. [x] Implement name validation, CLI option plumbing, generated entrypoint name injection, and agent factory naming.
4. [x] Publish relay `profile` in host ANNOUNCE and relay heartbeat messages.
5. [x] Run targeted tests, syntax checks, and diff hygiene checks.
6. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## Deploy Env Vars Sent to Backend Secrets Field

1. [x] Add a failing CLI regression test proving `co deploy --skills ...` sends `OPENONION_API_KEY` in the `secrets` form field.
2. [x] Update the deploy upload payload to send both `secrets` and `env_vars` with the same JSON payload.
3. [x] Run targeted deploy tests and syntax/diff hygiene checks.
4. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## co-ai Deploy EntryPoint Imports Packaged Source

1. [x] Add a failing test that generated co-ai entrypoint prepends package root to `sys.path` before importing `connectonion`.
2. [x] Update generated entrypoint content to calculate `/app` from `.co/deploy/co_ai_entrypoint.py` and insert it at `sys.path[0]`.
3. [x] Run deploy/co-ai tests, syntax checks, and diff hygiene checks.
4. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## Direct co-ai Deploy Without Project Scaffold

1. [x] Add failing tests that `co deploy --skills ...` selects co-ai and does not require git or `.co/host.yaml`.
2. [x] Add failing tests that co-ai packaging contains generated entrypoint, selected skills, package source, and generated `requirements.txt`.
3. [x] Add failing tests that explicit `--template project --skills ...` is rejected.
4. [x] Implement template auto-detection and separate validation paths for project vs co-ai deploy.
5. [x] Replace co-ai packaging's git archive base with a self-contained temporary package.
6. [x] Update deploy docs and control files.
7. [x] Run targeted tests, syntax checks, and diff hygiene checks.

## Login Handoff Privacy and Cleanup

1. [x] Record the hosted-browser boundary: do not rely on live Playwright objects across turns.
2. [x] Update login prompt guidance so QR and credential handoffs wait and continue in the same turn.
3. [x] Update cleanup guidance so `close_browser` runs after success, failure, or abandonment.
4. [x] Add prompt regression coverage for same-turn login handoff behavior.
5. [x] Store submitted credentials on the current Agent instance instead of returning raw values to the model.
6. [x] Add `type_saved_login_credential` so password typing does not expose the password in `keyboard_type(...)`.
7. [x] Add co ai login cleanup on completion so the server-side browser is closed even if the model forgets.

## co-ai Deploy Template

1. [x] Add failing tests for `co deploy --template co-ai --skills ...` argument handling and upload payload.
2. [x] Add failing tests for co-ai package construction: generated entrypoint, selected skill directories, and no working-tree writes.
3. [x] Add failing tests for missing skills and invalid `--skills` usage.
4. [x] Add failing tests for `create_coding_agent(co_dir=..., browser_headless=True)`.
5. [x] Implement CLI parameters, package builder helpers, skill resolution, and co-ai entrypoint generation.
6. [x] Update co-ai agent factory options for deploy-safe `co_dir` and headless browser behavior.
7. [x] Run targeted tests, syntax checks, and diff hygiene checks.
8. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## PR #143 Remote Login Review

1. [x] Add tests that fail while `remote_login` still performs tool-side judgment or direct user prompting.
2. [x] Refactor `connectonion/useful_tools/remote_login.py` into a thin frontend notification tool.
3. [x] Update the `remote_login` tool prompt so the agent owns user-facing follow-up decisions.
4. [x] Run targeted tests and update `STATUS.md` / `TASKS.md` with the result.

## Runtime Follow-up: co ai + oo-chat

1. [x] Add regression tests for reusing the existing browser automation instance in co ai.
2. [x] Add regression tests for preferring an available QR-login switch.
3. [x] Send a frontend-compatible screenshot event and return visible page context to the agent.
4. [x] Update prompt documentation to avoid terminal-blocking manual-login fallback in web chat.
5. [x] Run targeted tests, restart local co ai / oo-chat, and open the current agent URL.

## Simplify Remote Login Boundary

1. [x] Replace fallback browser creation with a hard dependency on the agent's existing browser context.
2. [x] Remove QR selector/process logic from `remote_login`.
3. [x] Send screenshots only through frontend-rendered image events, not duplicated metadata payloads.
4. [x] Update tests and prompt docs for server-side-browser semantics.
5. [x] Re-run targeted verification.

## BrowserAutomation Icon-Only Click Targets

1. [x] Add tests for extracting clickable icon-only elements.
2. [x] Preserve useful non-text metadata such as id/class/title/alt for element matching.
3. [x] Update matcher formatting so the LLM can select icon controls by metadata or position.
4. [x] Run targeted browser tool tests.

## Frontend Screenshot Delivery

1. [x] Trace `image_result_formatter` output and websocket/image event shape.
2. [x] Compare emitted image events with oo-chat's expected message schema.
3. [x] Patch the local SDK handoff that drops image payloads.
4. [x] Re-run the Xiaohongshu login e2e until the QR screenshot renders in chat.

## QR Screenshot Ask-User Handoff

1. [x] Add failing tests proving image formatting does not send every screenshot to the frontend.
2. [x] Add failing tests for a QR scan handoff that sends the current screenshot and waits on `ask_user`.
3. [x] Implement the explicit QR handoff tool and register it in co ai.
4. [x] Update prompt docs so QR login calls the handoff tool instead of `take_screenshot`/`wait_for_text`.
5. [x] Run targeted tests and local e2e verification.

## Credential Login Follow-Up

1. [x] Reproduce LinkedIn credential-login refusal in local oo-chat.
2. [x] Add prompt regression coverage for user-mediated credential login.
3. [x] Update prompt guidance so explicit login requests use `remote_login` and credential pages ask through `ask_user`.
4. [x] Prevent injected `agent` arguments from streaming into tool-result args.
5. [x] Restart local co ai and verify LinkedIn reaches account/password `ask_user`.

## Credential Ask-User Form

1. [x] Add failing tests for a structured credential `ask_user` event.
2. [x] Add failing tests that co ai registers the credential handoff tool and prompt guidance prefers it.
3. [x] Implement and export the credential handoff tool.
4. [x] Update co ai prompt docs to use the handoff for username/password pages.
5. [x] Restart local co ai and verify LinkedIn renders account/password fields.

## Remote-Login Handoff Tool Rename

1. [x] Add failing tests for new `send_*_to_user` tool names.
2. [x] Rename exports and co ai registration to the new names.
3. [x] Rename prompt docs and update remote-login guidance.
4. [x] Remove old request-prefixed exports instead of keeping compatibility aliases.
5. [x] Run targeted tests.

## Remote-Login Minimal Boundary Cleanup

1. [x] Remove helper discovery and use only `agent.browse` for the browser context.
2. [x] Remove duplicate ask-user wrapper logic and reuse the existing `ask_user` tool for QR confirmation.
3. [x] Remove custom `remote_login` frontend metadata events; only explicit user handoff tools send UI events.
4. [x] Remove optional handoff parameters that are not needed by the current login flow.
5. [x] Run syntax checks, broader focused tests, and diff hygiene checks.

## Hosted co ai Browser Reuse Finding

1. [x] Test whether two hosted Agent instances can share one BrowserAutomation object.
2. [x] Reject process-level singleton because sync Playwright is thread-bound and fails across agent threads.
3. [ ] Decide whether the next minimal fix is session cleanup, a browser lock, or a dedicated browser worker.

## Login Handoff Tool Boundary

1. [x] Remove `remote_login` from co ai tool registration and useful tool exports.
2. [x] Move QR and credential user handoffs into a direct `login_handoff.py` module.
3. [x] Update co ai prompts so normal browser tools open and inspect login pages.
4. [x] Update focused tests for the two send tools and absence of `remote_login`.
5. [x] Restyle the oo-chat credential form as a compact neutral card.

## Frontend Session Persistence

1. [x] Identify that `QuotaExceededError` comes from persisting base64 image data into `co:agent:*:session:*` localStorage keys.
2. [x] Strip base64 data URLs from persisted SDK `messages`, `ui`, and `session` while preserving runtime image display.
3. [x] Sync the fix into the local oo-chat package copy used by the dev server.
4. [x] Run a smoke test proving a large base64 image no longer expands the persisted localStorage payload.

## Browser Cleanup Tool

1. [x] Add a direct `close_browser` tool that uses the existing `agent.browse.close()` lifecycle.
2. [x] Register `close_browser` in co ai.
3. [x] Update login prompt guidance so the agent closes the server-side browser after success or abandonment, but not while waiting on user login steps.
4. [x] Add focused tests for close success, no-op closed state, registration, and prompt guidance.
