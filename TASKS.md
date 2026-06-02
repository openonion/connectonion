# Tasks

## Current Task: Lightweight co-ai Deploy Browser Flag

Status: complete

Context:

- co-ai deploy should still upload a normal deploy package for the existing `oo-api` backend.
- Users should not need to create `.co/host.yaml`, `agent.py`, or a handwritten `host(...)` entrypoint for co-ai deploy.
- The CLI should generate those project-scaffold files only inside the temporary tarball, not in the user's working tree.
- Browser deployments need Google Chrome in the container, but non-browser skill deploys should stay lightweight.

Scope:

- Generate a normal-looking co-ai deploy package with `agent.py`, `.co/host.yaml`, selected `.co/skills/*`, and `requirements.txt`.
- Add/keep `--browser` CLI plumbing so only browser deploys generate a Dockerfile that installs Google Chrome and select `browser_channel="chrome"`.
- Keep default `co deploy --skills foo` lightweight for non-browser skills such as image generation.
- Verify with focused tests and a real deploy, then confirm the server container has Chrome only for the browser deployment path.
- After successful verification, remove old remote `co-ai` / `agent-4-linkedin` containers/images so only the latest verified image remains.

Expected result:

- `co deploy --skills foo` creates a lightweight generated co-ai project package without Chrome installation.
- `co deploy --skills linkedin-post --browser` creates a generated co-ai project package with a Chrome-installing Dockerfile.
- The generated files live only in the tarball and do not modify the user's project directory.
- The deployed browser agent runs on the server with Google Chrome available.

Result:

- co-ai deploy packages now generate a normal deploy scaffold inside the tarball: `agent.py`, `.co/host.yaml`, selected `.co/skills/*`, and `requirements.txt`.
- Default `co deploy --skills foo` packages no Dockerfile and no Chrome install; skill requirements are inlined into root `requirements.txt` so the existing `oo-api` generic Dockerfile can install them.
- `co deploy --skills foo --browser` adds a generated Dockerfile that installs Google Chrome with Playwright and makes the generated agent use `browser_channel="chrome"`.
- `--browser` is rejected for explicit `--template project`.
- Production browser deploy succeeded for `agent-4-linkedin` after the directly related `oo-api` Docker build timeout fix.
- Server verification confirmed the latest container has `/usr/bin/google-chrome`, `Google Chrome 148.0.7778.215`, `xvfb-run`, and Playwright can launch channel `chrome`.
- Old `co-ai` and old `agent-4-linkedin` versions were removed; only `agent-4-linkedin-0x92f834c6-15c33c6a` remains on the server for those patterns.

## Current Task: Remove Generic Tool Approval Skip Flag

Status: complete

Context:

- `tool_approval.check_approval()` still honored `session["skip_tool_approval"]` as a generic bypass.
- co-ai no longer sets that flag, but keeping the generic branch makes future accidental bypasses easy.
- ULW can be represented directly by `session["mode"] == "ulw"`; `tool_approval` already has an explicit ULW branch.

Scope:

- Remove the generic `skip_tool_approval` bypass from `tool_approval`.
- Stop ULW from setting or clearing `skip_tool_approval`.
- Update tests so the old flag no longer bypasses approval.
- Keep explicit `mode == "ulw"` approval behavior.

Expected result:

- No generic session flag can bypass tool approvals.
- Only explicit approval modes and configured permissions control approval behavior.

Result:

- Removed the generic `skip_tool_approval` bypass branch from `tool_approval.check_approval()`.
- ULW no longer sets or clears `skip_tool_approval`; it relies on `mode == "ulw"`.
- Updated tool approval, constants, and ULW comments/docs to remove skip-flag semantics.
- Added/updated tests proving a stale `skip_tool_approval=True` still sends `approval_needed`.
- Focused approval/ULW/co-ai/deploy tests, syntax checks, and diff hygiene checks pass.

## Current Task: Remove co-ai Auto-Approve Hook

Status: complete

Context:

- `create_coding_agent(auto_approve=True)` added an `_enable_auto_approve` hook that set `skip_tool_approval=True`.
- That hook bypasses the existing web approval flow for dangerous tools.
- Code inspection confirms dangerous tools exist in `tool_approval.constants.DANGEROUS_TOOLS`: shell/run tools, write/edit tools, background/task control, external communication, and delete/remove tools.
- The separate ULW mode still explicitly uses `skip_tool_approval` as part of its autonomous mode behavior.

Scope:

- Remove the co-ai `_enable_auto_approve` hook.
- Remove the `auto_approve` argument from `create_coding_agent()`.
- Keep generic `skip_tool_approval` behavior for explicit ULW mode.
- Add/update tests proving co-ai no longer exposes or registers the auto-approve hook.

Expected result:

- co-ai never bypasses approval through an agent-factory option.
- Dangerous tools continue to require approval in web mode unless an explicit mode such as ULW is active.

Result:

- Removed `_enable_auto_approve` from `connectonion/cli/co_ai/agent.py`.
- Removed the `auto_approve` parameter from `create_coding_agent()`.
- Updated co-ai tests to assert the factory no longer exposes `auto_approve` and no auto-approve hook is registered.
- Confirmed real approval-gated tools from `DANGEROUS_TOOLS`: shell/run, write/edit, background/task control, external communication, and delete/remove tools.
- Kept explicit ULW `skip_tool_approval` behavior unchanged.
- Focused co-ai/deploy/approval/ULW tests, syntax checks, and diff hygiene checks pass.

## Current Task: Remove Claude Runtime Skills From co-ai

Status: complete

Context:

- ConnectOnion runtime skills should come from `.co/skills`, user `~/.co/skills`, and bundled built-ins.
- Claude Code skills may be discoverable/copyable through CLI migration commands, but they should not be loaded automatically by co-ai runtime or hosted deploy behavior.
- Runtime skill discovery currently includes `.claude/skills`, which can unexpectedly expose unrelated Claude workflows.

Scope:

- Remove `.claude/skills` from runtime skill path resolution.
- Remove `.claude/skills` from runtime skill discovery metadata.
- Add a regression test proving slash invocation does not load a Claude-only skill.
- Keep `co skills discover/copy` behavior out of scope.

Expected result:

- co-ai runtime and hosted co-ai only load ConnectOnion skills from `.co/skills`, `~/.co/skills`, and built-ins.
- Claude skills must be explicitly copied into `.co/skills` before runtime/deploy usage.

Result:

- Runtime skill path resolution no longer checks project, cwd, or user `.claude/skills`.
- Runtime skill discovery no longer lists `.claude/skills`.
- Added a regression test proving `/claude-only` is ignored when it exists only under `.claude/skills`.
- Focused skills/deploy tests, syntax checks, and diff hygiene checks pass.

## Current Task: Require co-ai User Approval by Default

Status: complete

Context:

- The hosted co-ai deploy entrypoint currently passes `auto_approve=True`, which sets `skip_tool_approval=True` on each turn.
- That bypasses the existing chat approval flow for dangerous tools.
- The safer default for both local web co-ai and hosted co-ai is to send approval requests to the connected user.

Scope:

- Stop enabling `auto_approve` by default in generated co-ai deploy entrypoints.
- Stop enabling `auto_approve` by default in local `co ai` web server startup.
- Keep the lower-level `skip_tool_approval` mechanism for explicit modes such as ULW.
- Add regression assertions so generated deploy packages and web startup do not silently re-enable auto approval.

Expected result:

- Dangerous hosted/local co-ai tool calls should route through the existing user approval UI when an IO client is connected.
- No blanket auto-approval is enabled by default.

Result:

- Generated co-ai deploy entrypoints no longer pass `auto_approve=True`.
- Local `co ai` web startup no longer passes `auto_approve=True`.
- Existing `skip_tool_approval` behavior remains for explicit modes/plugins such as ULW.
- Added regression assertions for deploy entrypoint generation and local web startup kwargs.
- Focused deploy/co-ai/approval/ULW tests, syntax checks, and diff hygiene checks pass.

## Current Task: Split co-ai Deploy Packaging Helpers

Status: complete

Context:

- `connectonion/cli/commands/deploy_commands.py` grew large after the co-ai deploy work.
- The new co-ai-specific packaging logic is separable from the legacy project deploy upload/polling flow.
- Tests still import helper functions through `deploy_commands`, so the split should preserve that compatibility surface.

Scope:

- Move co-ai deploy packaging, skills discovery, skill resolution, generated entrypoint/Dockerfile, and deploy env loading into a dedicated module.
- Keep `deploy_commands.py` focused on CLI orchestration, project git archive packaging, upload, and deploy status polling.
- Preserve existing `deploy_commands` helper imports through re-exported names.
- Do not change deploy behavior.

Expected result:

- `deploy_commands.py` is materially shorter and easier to review.
- Existing deploy tests continue to pass without behavior changes.

Result:

- Added `connectonion/cli/commands/deploy_co_ai.py` for co-ai deploy packaging, deploy-time skills/env handling, generated entrypoint, generated requirements, and generated Dockerfile logic.
- `deploy_commands.py` now keeps project deploy archive creation, template resolution, upload, and status polling.
- Existing helper names are still importable from `deploy_commands.py`.
- Focused deploy tests, syntax checks, and diff hygiene checks pass.

## Current Task: Explicit All-Skills co-ai Deploy

Status: complete

Context:

- Local `co ai` discovers every project/user/builtin skill and can show many skills, such as 59 skills on the developer machine.
- Hosted `co deploy --skills deploy-smoke` intentionally packages only explicitly selected skills plus bundled built-ins, so it showed fewer skills.
- Users need an explicit opt-in when they really want local project/user skills deployed wholesale.

Scope:

- Add a clear `--all-skills` CLI flag for co-ai deploy.
- Keep default deploy behavior conservative: do not upload all local user skills unless explicitly requested.
- Discover all project `.co/skills/*/SKILL.md` and user `~/.co/skills/*/SKILL.md` directories with project priority on duplicate names.
- Keep `--all-skills` scoped to the co-ai deploy template.

Result:

- `co deploy --name agent-full --all-skills` now auto-selects co-ai deploy and packages all project/user skills.
- `co deploy --template project --all-skills` is rejected before upload.
- Explicit `--skills ...` remains supported and can be combined with discovered all-skills names without duplicating packages.
- Focused deploy CLI/package tests pass.

## Current Task: Deploy Timeout and Package Build Simplification

Status: complete

Context:

- `co deploy --name agent-4-linkedin --skills deploy-smoke` failed at `Uploading...` with Cloudflare 524.
- The backend deploy API was doing the full Docker build/run path inside the POST request, so Cloudflare could time out before the CLI reached its existing status polling loop.
- The co-ai generated Dockerfile also copied the entire package before dependency installation, which makes Docker layer caching less useful for repeated deploys.

Scope:

- Keep the CLI/status-polling contract simple: POST returns a deployment id and `deploying`, then CLI polls status.
- Move slow backend build/run work out of the POST response path.
- Remove unnecessary cache busting from deploy builds.
- Keep the co-ai deploy package self-contained and compatible with selected skills.

Expected result:

- Deploy POST should return quickly with `status=deploying` instead of waiting for Docker build.
- Repeated deploys should have a better chance of reusing Docker layers.
- CLI remains the same user flow: upload, then poll until running or failed.

Result:

- Local implementation and focused tests are complete.
- `oo-api` production was deployed with the detached deploy task fix.
- Real `co deploy --name agent-4-linkedin --skills deploy-smoke` no longer 524s at `Uploading...`; it entered `Building...` and completed successfully.

## Current Task: Hosted co-ai Browser Uses Chrome Channel

Status: complete

Context:

- Hosted co-ai browser automation currently installs/uses Playwright Chromium for deploy.
- Login-heavy workflows are more compatible when running against branded Google Chrome's stable channel where available.
- Playwright supports branded browser channels such as `chrome`, but Chrome must be installed in the container and selected at launch.
- Using Chrome improves compatibility but does not make automation invisible; cloud IP, headless mode, automation flags, and new profiles can still trigger login risk systems.

Scope:

- Add a browser channel option to `BrowserAutomation`.
- Pass `browser_channel="chrome"` for deployed co-ai.
- Install Chrome, not default Chromium, in the generated co-ai Dockerfile.
- Keep local co ai behavior unchanged unless a browser channel is explicitly provided.
- Add focused tests for deploy entrypoint/package generation and co-ai agent factory wiring.

Expected result:

- New `co deploy --skills ...` co-ai containers install Google Chrome during image build.
- Hosted co-ai browser tools launch via Playwright's `chrome` channel.
- Local co ai can still use the existing local Chrome path/fallback behavior.

Result:

- Added `browser_channel` support to `BrowserAutomation` and `create_coding_agent()`.
- Hosted co-ai generated entrypoints now pass `browser_headless=True` and `browser_channel="chrome"`.
- Generated co-ai Dockerfiles now install the Playwright Chrome channel with `python -m playwright install --with-deps chrome`.
- `co deploy --skill ...` is accepted as a singular alias for `--skills ...`; repeated/comma-separated skill parsing remains unchanged.
- Selected skill `requirements.txt` files are referenced from the generated root `requirements.txt`, so skill-specific Python dependencies install during image build.
- co-ai deploy env collection now merges project `.env`, allowed API keys from global `~/.co/keys.env`, and allowed API keys from the current process environment without dumping the whole shell environment.
- `auto_approve=True` now sets the session `skip_tool_approval` flag, and the approval plugin respects that flag without switching to ULW mode.
- Focused tests cover the generated deploy package, skill dependency wiring, env-var merge behavior, co-ai factory wiring, CLI skill alias behavior, BrowserAutomation launch options, and approval skip behavior.

## Previous Task: co-ai Deploy Installs Packaged Source

Status: complete

Context:

- The previous browser-runtime fix added a co-ai Dockerfile and Playwright Chromium install step, but it still left `requirements.txt` as `connectonion=={version}`.
- That means Docker build installs dependencies from the published PyPI package, then runtime imports the packaged `/app/connectonion` source through `sys.path`.
- This can drift: newly added co-ai source, package data, or dependency declarations may not match the published package used during build.
- The co-ai deploy package should install the packaged local source itself, including the current `pyproject.toml` dependencies.

Scope:

- Add package metadata needed to install the packaged local ConnectOnion source.
- Change co-ai generated `requirements.txt` to install the local package.
- Keep the co-ai Dockerfile installing dependencies from the generated requirements file, then installing Playwright Chromium.
- Keep project deploy behavior unchanged.
- Update package-builder regression coverage.

Expected result:

- `co deploy --skills ...` builds a co-ai image from the exact local packaged source.
- Hosted co-ai has the current package code, package data, and declared dependencies installed.
- Hosted co-ai browser tools still get Chromium installed at image-build time.

Result:

- co-ai deploy packages now include local package metadata (`pyproject.toml`, plus README/LICENSE when available) alongside the packaged `connectonion/` source.
- Generated co-ai `requirements.txt` installs `.` when local metadata is available, so Docker build installs the packaged source and its declared dependencies.
- The co-ai Dockerfile copies the full package before `pip install -r requirements.txt`, then installs Playwright Chromium during image build.
- If the CLI is running from an installed package without local project metadata, the package builder keeps the previous `connectonion=={version}` fallback.

## Previous Task: co-ai Deploy Browser Runtime

Status: complete

Context:

- The current hosted co-ai session failed the user's browser request before normal page automation and then tried to run `playwright install chromium` through Bash.
- `oo-api` adds a generic Dockerfile only when the package does not include one; that generated Dockerfile only installs Python requirements and does not install Playwright browser binaries or OS dependencies.
- The co-ai deploy package currently includes browser tools, so the package should provide a deploy-specific Dockerfile that installs Chromium during image build.

Scope:

- Add a generated Dockerfile to co-ai deploy packages only.
- Install Python requirements first, then run `python -m playwright install --with-deps chromium` at build time.
- Keep project deploy behavior unchanged.
- Add package-builder regression coverage.

Expected result:

- `co deploy --skills ...` builds a co-ai image with Playwright Chromium already installed.
- Hosted co-ai browser tools should not need to call `playwright install chromium` at runtime.

Result:

- co-ai deploy packages now include a generated Dockerfile.
- The generated Dockerfile installs Python requirements and runs `python -m playwright install --with-deps chromium` during image build.
- Project deploy behavior is unchanged; this Dockerfile is only generated for the co-ai deploy package path.
- Added package-builder coverage proving the Dockerfile is included and contains the Chromium install step.

## Previous Task: Restored Running Session Stop State

Status: complete

Context:

- A restored chat session can show a tool card still marked `RUNNING` while the input button remains the disabled send arrow.
- The current chat loading state only follows the live SDK `status`, so a page refresh/reconnect can lose the visible stop affordance even though persisted UI still contains active work.
- In the current hosted co-ai session, the visible running item is a `Bash` tool running `playwright install chromium`; the browser dependency problem is separate, but the frontend should still present a stop control for the active restored item.

Scope:

- Derive oo-chat loading state from both live SDK processing and active restored UI items.
- Make `RemoteAgent.stop()` settle locally running UI items so clicking stop does not leave the page stuck in loading state.
- Add focused SDK regression coverage for stopping restored running items.

Expected result:

- A restored session with `tool_call: running`, `thinking: running`, `intent: analyzing`, `eval: evaluating`, or `compact: compacting` shows the stop button.
- Clicking stop returns the local UI to idle without clearing the transcript.

Result:

- `oo-chat` now derives `isLoading` from both live SDK `isProcessing` and active restored UI items.
- `RemoteAgent.stop()` now settles restored running local UI items as stopped/error/done before returning to idle.
- Added focused SDK regression coverage for stopping restored running items.
- Reloading the current local session now shows the `Stop response` button while the restored UI still contains active work.

## Previous Task: Chat Input Stop Button

Status: complete

Context:

- During hosted agent execution, the input send button remains an inactive arrow instead of switching to a visible stop control.
- Users need a local stop affordance in the send-button position, matching normal chat UX.
- The current backend does not expose safe thread cancellation, so first implementation should stop the client-side active stream by closing the current WebSocket and returning UI state to idle without clearing the transcript.

Scope:

- Add a `stop()` method to the TypeScript remote agent/react hook layer.
- Wire `stop` through `oo-chat`'s `useAgentSDK`, `Chat`, and `ChatInput`.
- Render the send button as a stop button while loading.
- Keep text entry and existing message history intact.

Expected result:

- While an agent response is running, the send button position shows a stop icon.
- Clicking it stops the current client stream and returns the UI to idle without deleting the conversation.

Result:

- Added `RemoteAgent.stop()` in the TypeScript SDK to close the active WebSocket, clear the optimistic thinking placeholder, settle local input state, and return the client UI to idle without clearing the transcript.
- Exposed `stop()` through `useAgentForHuman()` and `oo-chat`'s `useAgentSDK()`.
- Wired `onStop` through the chat page, `Chat`, and `ChatInput`.
- `ChatInput` now switches the send-button position from arrow to stop icon while `isLoading` is true.
- Added a focused SDK regression test for client-side stop behavior.

## Previous Task: Deployed Slash Skills Use Agent co_dir

Status: complete

Context:

- The deployed page now shows `agent-4-linkedin` and `/deploy-smoke`, proving relay profile metadata reaches the frontend.
- Invoking `/deploy-smoke` still let the model run normal coding tools before outputting the marker, which means the backend slash-skill interceptor did not reliably load the deployed `.co/skills/deploy-smoke/SKILL.md`.
- Skill discovery for metadata uses `agent.co_dir`, but the slash invocation loader still searches `Path.cwd()/.co/skills`, which can diverge in hosted deployments.
- The connection also shows intermittent `Authentication timed out`; current evidence points to slow relay/agent handshake and auth retries, but the immediate correctness bug is slash skill routing.

Scope:

- Add a failing test proving `/deploy-smoke` loads from `agent.co_dir` even when process cwd is somewhere else.
- Update the skills plugin so slash invocation and the `skill()` tool load skills from the same `co_dir` source as metadata discovery.
- Keep existing local cwd behavior as a fallback.
- Verify focused skills tests and deploy-related tests.

Expected result:

- Hosted `co ai` slash skills use the packaged `.co/skills` directory and replace `/deploy-smoke` with the skill instructions before the LLM runs.
- The smoke skill no longer triggers exploratory `ls/read_file` behavior just to discover skill files.

Result:

- Added a regression test that reproduces the hosted case: process cwd differs from `agent.co_dir`, and `/deploy-smoke` must still load from `agent.co_dir/skills/deploy-smoke/SKILL.md`.
- Updated the skills plugin path resolver so slash invocation and the `skill()` tool load from `agent.co_dir` first, then cwd, user skills, and built-ins.
- Updated generated co-ai deploy entrypoints to pass `CO_DIR = PACKAGE_ROOT / ".co"` so hosted agents use the package's `.co` directory even if cwd changes.
- Local cwd behavior remains as a fallback for normal local agents.

## Previous Task: Frontend Reads Relay Profile for Hosted co-ai

Status: complete

Context:

- Hosted co-ai now publishes relay profile metadata, and named deploys can set the deployed agent identity.
- The chat landing page still renders address-only because `oo-chat` and the TypeScript SDK only read relay endpoints, then try direct agent `/info` for name/tools/skills.
- For hosted relay traffic, direct `/info` may be unreachable or stale from the browser, while `/api/relay/agents/{address}/profile` is the stable metadata path.

Scope:

- Teach the TypeScript SDK and `oo-chat` agent-info hook to read relay profile metadata.
- Normalize profile `tools` so both current object-shaped payloads and string arrays render correctly.
- Keep direct `/info` as a best-effort enrichment path, without making UI metadata depend on it.
- Align hosted Python profile tools with the SDK's `string[]` shape while retaining frontend tolerance for older deployed profiles.

Expected result:

- A deployed co-ai page can show the deploy name, selected skills, tools, model, and version from relay profile even if direct `/info` cannot be reached.
- Existing direct `/info` metadata still wins when it is available and address-verified.
- The dashboard/chat address-only fallback is reserved for agents that truly have no relay profile.

Result:

- `connectonion-ts.fetchAgentInfo()` now reads `/api/relay/agents/{address}/profile`, normalizes skills/tools, and returns profile metadata when direct `/info` cannot be reached.
- `oo-chat`'s `useAgentInfo()` now uses the same relay-profile fallback, so the landing page/sidebar/settings can render name, skills, tools, model, and version from relay metadata.
- Direct `/info` remains a best-effort enrichment path and no longer gates metadata or online status.
- Hosted Python relay profiles now publish `tools` as a string array, matching SDK/frontend expectations; the frontend still accepts older `{name: ...}` tool objects.

## Previous Task: Named co-ai Deploys Publish Relay Profile Metadata

Status: complete

Context:

- Hosted co-ai deploy now starts and connects through the relay, but the frontend only shows the address because the host ANNOUNCE does not publish profile metadata.
- The deployed co-ai agent name is still hardcoded as `oo`, and the deploy project name defaults to `co-ai`, so repeated co-ai deploys refresh the same dashboard/app identity.
- The desired UX is `co deploy --name agent-4-linkedin --skills ...`: deploy co-ai with selected skills, use the name for backend project identity, Agent metadata, and relay profile display.

Scope:

- Add a lightweight deploy name option that works with co-ai deploys and is safe for agent URLs.
- Pass the selected deploy name into the generated co-ai entrypoint and `create_coding_agent()`.
- Publish relay profile metadata from `host()` using the already extracted agent metadata so frontend/directory/profile endpoints can show name, skills, tools, model, and version.
- Keep existing `co deploy --skills ...` behavior compatible, defaulting to `co-ai` when no name is provided.

Expected result:

- `co deploy --name agent-4-linkedin --skills deploy-smoke` uploads with `project_name=agent-4-linkedin`.
- The generated hosted co-ai Agent has `agent.name == "agent-4-linkedin"`.
- Relay ANNOUNCE includes profile metadata, so the frontend can render a name and available skills/tools instead of address-only UI.

Result:

- Added `co deploy --name/-n` and validate it for URL-safe lowercase letters, numbers, and hyphens.
- Direct co-ai deploy still defaults to `co-ai`, but `--name agent-4-linkedin` now sets the upload `project_name`, generated entrypoint agent name, and hosted Agent name.
- `create_coding_agent(name=...)` now accepts custom names while local `co ai` keeps the default `oo`.
- `host()` now publishes a signed relay profile built from agent metadata: alias/name, bio, version, model, tools, and skills.
- Relay heartbeat re-announces preserve the profile payload instead of dropping it on refresh.

## Previous Task: Deploy Env Vars Sent to Backend Secrets Field

Status: complete

Context:

- Real co-ai deploy now imports packaged source from `/app/connectonion`, so the previous site-packages import bug is fixed.
- The remote container now fails at startup with `ValueError: OPENONION_API_KEY not found in environment`.
- The CLI sends environment variables as multipart field `env_vars`, but the production `oo-api` deploy route accepts `secrets` and the deploy service only parses `secrets` into `docker run -e ...`.

Scope:

- Update the CLI deploy upload payload so env vars are sent in the backend-compatible `secrets` field.
- Keep sending `env_vars` as a compatibility field for any backend version that already expects it.
- Add regression coverage for co-ai deploy passing `OPENONION_API_KEY` through the upload payload.

Expected result:

- `co deploy --skills ...` uploads `OPENONION_API_KEY` in the field the current deploy backend injects into the Docker container.
- Existing project deploy payload behavior remains compatible.

Result:

- CLI deploy now serializes env vars once and sends the JSON under both `env_vars` and `secrets`.
- This keeps compatibility with the SDK-side `env_vars` naming while matching the production `oo-api` backend that reads `secrets` for Docker env injection.
- Added regression coverage proving `co deploy --skills ...` includes `OPENONION_API_KEY` in `secrets`.

## Previous Task: co-ai Deploy EntryPoint Imports Packaged Source

Status: complete

Context:

- Real `co deploy --skills deploy-smoke` reached the deploy server and built a container, but startup failed.
- Traceback showed `/app/.co/deploy/co_ai_entrypoint.py` imported `connectonion.cli.co_ai.agent` from `/usr/local/lib/python3.11/site-packages/connectonion`, not the packaged `/app/connectonion` source.
- The installed PyPI version did not yet include `create_coding_agent(co_dir=...)`, causing `TypeError: unexpected keyword argument 'co_dir'`.

Scope:

- Update the generated co-ai entrypoint so it prepends the deployment package root (`/app`) to `sys.path` before importing `connectonion`.
- Add regression coverage proving the generated entrypoint prefers packaged source over site-packages.
- Keep the direct co-ai deploy UX and project deploy behavior unchanged.

Expected result:

- Deployed co-ai containers import the generated package source from `/app/connectonion`.
- The `create_coding_agent(co_dir=..., browser_headless=True)` entrypoint works before these changes are published to PyPI.

Result:

- Generated co-ai entrypoints now calculate `PACKAGE_ROOT = Path(__file__).resolve().parents[2]` and insert it at the front of `sys.path` before importing `connectonion`.
- This makes `/app/connectonion` take precedence over `/usr/local/lib/python*/site-packages/connectonion` inside the deployed container.
- Added regression coverage to ensure the `sys.path` insertion happens before `from connectonion import host`.

## Previous Task: Direct co-ai Deploy Without Project Scaffold

Status: complete

Context:

- The first co-ai deploy implementation still inherited project deploy assumptions: git repo, `.co/host.yaml`, and a committed project file.
- The intended UX is to deploy hosted `co ai` directly by attaching selected skills, without preparing or committing a separate agent entrypoint.

Scope:

- Make `co deploy --skills <name>` select co-ai deployment automatically.
- Let co-ai deployment run from any directory without git, `.co/host.yaml`, or `agent.py`.
- Build a self-contained temporary co-ai package with generated entrypoint, selected skills, package source, and a minimal `requirements.txt`.
- Keep explicit `--template project` behavior as the backwards-compatible project deploy path.
- Update tests and docs to match the direct co-ai deploy UX.

Expected result:

- `co deploy --skills alpha,beta` deploys co-ai directly.
- `co deploy --template co-ai --skills alpha` also works without project files.
- Existing `co deploy` inside a normal ConnectOnion project continues to deploy the project.
- Explicit `co deploy --template project --skills alpha` is rejected because project deploys do not consume skills.

Result:

- `co deploy --skills ...` now auto-selects co-ai deploy and does not require git, `.co/host.yaml`, or `agent.py`.
- `co deploy --template co-ai --skills ...` uses the same direct co-ai path.
- `co deploy` in a git/ConnectOnion project still follows the project deploy path.
- Explicit `--template project --skills ...` is rejected.
- Co-ai deploy packages are self-contained: current ConnectOnion package source, generated `requirements.txt`, generated `.co/deploy/co_ai_entrypoint.py`, and selected skills are written only into the temporary tarball staging directory.

## Previous Task: Login Handoff Privacy and Cleanup

Status: complete

Context:

- Hosted `co ai` creates fresh Agent/tool instances for new requests, so the frontend chat session should not rely on a live Playwright browser object surviving across turns.
- The lightweight architecture is to complete QR or credential handoff inside the current tool loop, then close the server-side browser when the login flow ends.
- Local LinkedIn testing showed the model used `keyboard_type(text="...")` for the submitted password, exposing it in trace/UI.
- The model also ended after a failed login without explicitly calling `close_browser`.

Scope:

- Keep `send_qr_to_user` and `send_credentials_form_to_user` as blocking user handoff tools.
- Update prompt guidance so the model does not end the turn by asking the user to message later after scanning or entering credentials.
- Require `close_browser` after login success, failure, or abandonment.
- Do not return raw credentials from the credential handoff.
- Add a narrow tool that types saved credentials into the focused browser field without exposing their values in tool arguments.
- Add a co ai completion cleanup safety net for login handoff turns.
- Avoid session-scoped browser registries, browser workers, or core runtime changes.

Result:

- Login prompt guidance now says to keep handoffs inside the same turn and continue checking browser state after the handoff returns.
- QR and credential tool docs now explicitly prohibit ending the turn with "tell me later" style instructions.
- Cleanup guidance now covers success, failure, and abandonment.
- `send_credentials_form_to_user` stores credentials on the current Agent instance and returns only instructions, not credential values.
- `type_saved_login_credential(field="username"|"password")` types the saved value into the focused browser field without putting the secret in trace args.
- co ai registers a login cleanup `on_complete` plugin that closes the browser after a login handoff turn when needed.
- Added regression coverage for same-turn login lifecycle, hidden credential typing, and automatic login cleanup.

## Previous Task: co-ai Deploy Template

Status: complete

Context:

- `co deploy` currently deploys a complete project agent by reading `.co/host.yaml`, validating that its entrypoint calls `host(...)`, packaging `git archive HEAD`, and uploading that tarball.
- The desired flow is to deploy a hosted `co ai` coding agent from CLI arguments, then add selected skills with `--skills`, without requiring users to maintain a full deployable agent entrypoint in the project.

Scope:

- Keep `co deploy` default behavior backwards-compatible.
- Add `co deploy --template co-ai --skills ...` as a separate deploy path.
- Generate a temporary co-ai host entrypoint only inside the deployment package.
- Package selected skills from project `.co/skills`, user `~/.co/skills`, or built-in co-ai skills.
- Add focused tests for CLI argument behavior, package contents, missing skills, and co-ai agent factory options.

Expected result:

- `co deploy` continues to deploy the project configured by `.co/host.yaml`.
- `co deploy --template co-ai --skills alpha,beta` uploads a tarball with the generated co-ai entrypoint and selected `.co/skills/*` directories.
- The user working tree is not modified by co-ai deploy packaging.
- Missing skills stop deployment before upload with a clear suggestion to run `co skills discover && co skills copy <name>`.
- Deployed co-ai agents can use project `.co` state and headless browser automation.

Result:

- Added `--template`, `--skills`, `--model`, and `--max-iterations` options to `co deploy`.
- Kept the default `project` deploy path compatible with existing `.co/host.yaml` and `host(...)` validation.
- Added co-ai deploy packaging that starts from `git archive HEAD`, overlays `.co/deploy/co_ai_entrypoint.py`, and copies selected skill directories into `.co/skills/`.
- Added skill resolution priority: project `.co/skills`, user `~/.co/skills`, then built-in co-ai skills.
- Updated `create_coding_agent()` with deploy-safe `co_dir` and `browser_headless` options.
- Updated deploy documentation for the new co-ai template path.

## Previous Task: Login Handoff Tool Boundary

Status: complete

Context:

- `remote_login` duplicated normal browser automation (`open_browser`, `go_to`, `take_screenshot`) and gave the model an extra path.
- The only login-specific behavior needed by co ai is sending QR screenshots or credential forms to the user.

Scope:

- Remove `remote_login` from useful tool exports, co ai registration, and prompt guidance.
- Keep `send_qr_to_user` and `send_credentials_form_to_user` as the only login handoff tools.
- Move the remaining implementation into a direct `login_handoff.py` module.
- Update tests so prompt guidance uses browser tools for navigation and the send tools for user interaction.
- Restyle oo-chat's credential ask-user form to a neutral compact UI.

Expected result:

- co ai does not expose `remote_login`.
- Login prompts tell the model to open and inspect pages with browser automation.
- QR login sends the screenshot only through `send_qr_to_user`, then waits for scan confirmation.
- Credential login sends one structured account/password form to the user.
- The credential form uses a minimal neutral card instead of a colored/amber treatment.

Result:

- `remote_login` was removed.
- `send_qr_to_user` captures the current browser screenshot, sends it with `agent.io.send_image`, then calls the existing `ask_user` tool.
- `send_credentials_form_to_user` emits a single structured credential `ask_user` event with both `text` and `question` for the current oo-chat SDK path.
- Old `request_qr_scan` and `request_login_credentials` names are no longer exported or registered.
- LinkedIn smoke test after restart reached `send_credentials_form_to_user` without `remote_login` and rendered separate account/password fields.
- oo-chat credential form was simplified to neutral borders, white background, compact fields, and a neutral submit button.
- The frontend image persistence failure was traced to SDK localStorage persistence, not to QR handoff logic. The SDK persistence path now removes base64 image data before saving session state.
- Added `close_browser` as an explicit cleanup tool for the agent to call after a login/browser flow succeeds or cannot continue. The tool delegates to the existing browser context close path instead of introducing a second browser lifecycle.

## Previous Task: Remote-Login Minimal Boundary Cleanup

Status: complete

Context:

- The QR and credential handoff tools are user-facing send operations, not login process owners.
- The implementation should rely on the existing co ai browser context (`agent.browse`) and the existing `ask_user` tool instead of wrapper discovery, duplicate prompt helpers, or compatibility aliases.

Result:

- Duplicate wrappers, old request-prefixed names, and frontend metadata events were removed.
- Cross-session BrowserAutomation reuse was tested and rejected: the sync Playwright object is thread-bound, so sharing it across fresh hosted Agent threads raises `Cannot switch to a different thread`.

## Previous Task: Credential Ask-User Handoff

Status: complete

Context:

- LinkedIn credential-login e2e now reaches `remote_login` and then calls the generic `ask_user` tool.
- The generic tool-card UI renders a single "Something else..." input, which is not the intended account/password form.
- oo-chat already supports a standalone `ask_user` credential form when events include `input_type="credentials"` and `fields`.

Scope:

- Add a login credential handoff tool that emits a structured `ask_user` event with username/password fields.
- Register it in co ai and update prompts so credential login pages use it instead of generic `ask_user`.
- Add focused tests for event shape and prompt guidance.
- Re-run LinkedIn e2e until the frontend shows separate account/password fields.

Expected result:

- Credential login pages trigger an `ask_user` event with account and password fields.
- The frontend renders a two-field credential form rather than a generic single custom-answer box.
- QR login behavior remains unchanged.

Result:

- Added the credential handoff, registered it in co ai, and documented it for credential login pages.
- Credential ask-user events now include `input_type="credentials"` and username/password `fields`.
- English login requests such as "help me login" are explicitly covered by the co ai remote-login prompt.
- Local LinkedIn e2e now reaches the credential handoff and oo-chat renders separate `账号` and `密码` fields instead of the generic single-answer input.

## Previous Task: QR Screenshot Ask-User Handoff

Status: complete

Context:

- The icon-only click issue is fixed in local e2e: `click(QR code icon...)` now selects the `img` at the top right of the login box.
- Frontend image delivery now works in local oo-chat, but the current backend behavior sends every screenshot-like tool result to chat.
- For remote login, ordinary screenshots should be used by the model to inspect the page. The user-visible screenshot should happen only when the agent has a QR code for the user to scan.

Scope:

- Change image result formatting so screenshots are model-visible by default but not automatically frontend-visible.
- Add a tightly scoped QR scan handoff tool that captures the current browser screenshot, sends it to oo-chat, and asks the user to confirm after scanning.
- Update co ai tools and prompt guidance so QR login uses the handoff tool instead of `take_screenshot` + final text or `wait_for_text`.

Expected result:

- `remote_login` and `take_screenshot` can still provide screenshots to the model for visual reasoning.
- oo-chat does not receive every screenshot automatically.
- When a QR code is visible, the agent calls the QR handoff tool; oo-chat receives the QR screenshot and an `ask_user` prompt asking the user to scan and confirm.
- The agent waits for the user's confirmation before checking whether login completed.

Result:

- Ordinary screenshot tool results are model-visible but no longer automatically sent to oo-chat.
- The QR handoff sends the current browser screenshot to oo-chat and immediately waits on an `ask_user` confirmation.
- co ai registers the QR handoff and keeps its browser headed for local server-side-browser simulation.
- Prompt guidance now tells the agent to use the QR handoff for QR logins and credential handoff for account/password logins.
- LinkedIn credential-login e2e reaches `remote_login` and then prompts the user for account/password instead of refusing.
- Injected `agent` arguments no longer leak into streamed tool-result args.

## Previous Task: Frontend Screenshot Delivery for Remote Login

Status: complete

Context:

- The icon-only click issue was fixed in local e2e: `click(QR code icon...)` now selects the `img` at the top right of the login box.
- The next failure was that the resulting QR screenshot was not visible in oo-chat, even though `take_screenshot` and `image_result_formatter` reported success.

Result:

- Local oo-chat's bundled connectonion runtime was patched so `agent_image` events render inline.
- The backend-to-frontend image event path was verified in local e2e.

## Previous Task: BrowserAutomation Icon-Only Click Targets

Status: complete

Context:

- Local co ai + oo-chat e2e for `帮我登录 https://creator.xiaohongshu.com/login` reached the server-side browser page.
- The agent attempted `click(QR code login icon...)`, but `element_finder` returned only text/input/button candidates such as `短信登录` and `登 录`.
- The Xiaohongshu QR-login switch appears to be a visual icon without useful text or aria metadata, so the current extractor filters it out before matching.

Scope:

- Keep `remote_login` as a thin browser-state/screenshot tool.
- Improve BrowserAutomation's element extraction/matching so clickable icon-only controls can appear as candidates.
- Add focused regression coverage for icon-only clickable elements.

Expected result:

- `click(description)` can select a clickable icon target when the target is represented by position or non-text attributes.
- The agent should stop retrying impossible semantic clicks when a page exposes only SMS/login candidates.

Result:

- `extract_elements.js` keeps small clickable icon-only controls instead of filtering them out.
- `element_finder` preserves non-text metadata (`title`, `alt`, `id`, `class`, selected `data-*`) and size in matcher context.
- The element matcher prompt now explicitly handles icon-only controls such as QR switches.

## Previous Task: PR #143 Remote Login Runtime Follow-up

Status: complete

Context:

- `connectonion/useful_tools/remote_login.py`: reviewer says the tool should not make the login judgment. It should notify the frontend and let the agent, guided by prompt text, decide what request to send to the user.
- Local `co ai` + `oo-chat` testing showed `remote_login` fails in the websocket/async runtime when it starts its own Playwright sync context, causing the agent to fall back to normal browser tools and terminal-blocking manual login.
- Design correction: `remote_login` should not own browser/process/login lifecycle. It should use the browser context already registered on the agent, send a screenshot to the frontend, and return page context for the agent prompt.

Scope:

- Remove tool-side QR/password/success judgment from `remote_login`.
- Keep the remote login tool focused on using the existing browser context to open the login page, sending browser state to the frontend, and returning instructions to the agent.
- Require the existing co ai browser automation instance instead of creating a fallback browser.
- Leave QR switching and other browser operations to the browser tool/prompt layer rather than hard-coding page process logic in `remote_login`.
- Remove terminal-blocking manual login from co ai's web-agent tool schema.
- Update directly coupled tests and prompt documentation.

Result:

- `remote_login` now requires and uses the agent's existing browser context.
- It no longer imports or instantiates `BrowserAutomation`, opens/closes browsers, owns profiles, or hard-codes QR/login process logic.
- It calls the existing browser context to navigate, capture a screenshot, send `agent_image` to the frontend, and return visible page text.
- The custom `remote_login` metadata payload no longer duplicates the screenshot data URL.
- `wait_for_manual_login` remains removed from the co ai tool schema because it blocks on local stdin in websocket chat.
