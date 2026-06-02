# Project Status

Last updated: 2026-06-03

## Baseline

- Repository: `openonion/connectonion`
- Active branch: `codex/co-ai-remote-login-tool`
- Active PR: `#143` (`[codex] Add remote login tool to co ai`)
- Current focus: making credential handoff field normalization tolerate fields that omit `name`.

## Working Tree Notes

- `AGENTS.md` and `test-deploy/` were present before this status baseline.
- New reviewer/user direction: restore `agent.io.send_image(data_url)` in `image_result_formatter` so all screenshot/image tool results display directly in the frontend.
- Boundary: keep the existing multimodal `image_url` message insertion for LLM visibility, and rely on frontend/SDK persistence sanitizers to keep full base64 images out of localStorage.
- New user direction: delete `connectonion/cli/co_ai/plugins/login_cleanup.py`; co ai should rely on explicit `close_browser` plus `open_browser()` stale-context cleanup instead of a completion-time login cleanup plugin.
- Fix: `image_result_formatter` now sends formatted image data URLs through `agent.io.send_image(...)` when IO is available, while retaining the LLM-visible multimodal `image_url` message.
- Fix: `connectonion/cli/co_ai/plugins/login_cleanup.py` was removed and co ai no longer imports, exports, or registers the cleanup plugin.
- New user direction: co ai hosted mode should not create a fresh agent on each continued input; the local web server should hold one Agent instance so browser tool state can persist across turns.
- Fix: `co_ai.main.start_server()` now creates one `Agent` at server startup and passes that instance to `host()`, instead of passing a per-request factory.
- New user direction: after login finishes, co ai should not close the browser; leave it open for follow-up actions.
- Fix: co ai login/browser lifecycle prompts now leave the browser open after successful login and reserve `close_browser` for explicit close requests or abandoned browser flows.
- New user direction: do not add separate form tools; directly update `send_credentials_form_to_user` and prompts so the same handoff can ask for arbitrary login fields such as OTP/2FA verification codes.
- Fix: `send_credentials_form_to_user` now accepts optional `question` and `fields` arguments while preserving its default username/password form.
- Fix: `type_saved_login_credential` now types any saved field name from that form, including `verification_code`, without returning raw values.
- Prompt guidance now tells co ai to use the existing credential handoff for verification code, OTP, 2FA, phone, email, captcha code, and other login fields.
- Runtime finding: local LinkedIn test showed the LLM can pass custom credential field objects without `name`, causing `Credential field requires a name.`
- Current task: derive stable field names from labels/placeholders/autocomplete/type instead of failing on missing `name`.
- Fix: missing credential field names are now derived from `label`, `placeholder`, `autocomplete`, non-text `type`, or a `field_N` fallback.
- Local co ai backend was restarted after the fix; `GET /health` returned healthy.
- GitHub PR #143 reported `mergeable=CONFLICTING` / `mergeStateStatus=DIRTY` after the lifecycle fix.
- Latest `origin/main` conflicted only in `connectonion/useful_tools/browser_tools/browser.py`.
- Conflict resolution keeps `main`'s browser-tool updates and preserves the PR behavior that closes stale browser/page/playwright state before reopening.
- Post-merge verification passed with focused browser/login/co-ai tests, syntax checks, and diff hygiene checks.
- New PR #143 review comment: continuing a login conversation should not leave the previous server-side browser process open when the agent opens a new browser instance.
- Current finding: `login_cleanup` only closes after `_login_handoff_active` completion; direct lifecycle protection belongs in `BrowserAutomation.open_browser()` so cleanup does not rely only on model behavior or a cleanup hook.
- Fix: `BrowserAutomation.open_browser()` now closes any existing browser/page/playwright state before launching a fresh persistent browser context.
- Fix: added an `open_browser` system reminder that explains the previous context is closed on open and reminds the agent to call `close_browser` when the flow finishes.
- Regression coverage added for close-before-reopen behavior and lifecycle reminder matching.
- This iteration should stay scoped to `remote_login`, its directly coupled prompt/tests, and local server restart verification.
- Local runtime issue observed: `remote_login` starts a second Playwright sync context inside the websocket/async runtime and fails with "using Playwright Sync API inside the asyncio loop"; the agent then falls back to browser tools and `wait_for_manual_login`.
- Design correction: do not put browser/process/login lifecycle inside `remote_login`; the browser tool owns browser context and process behavior.
- Remote-agent assumption: the user cannot see the server-side browser window, so QR login must send the QR screenshot through oo-chat as a user action request.
- Current implementation: `remote_login` uses `agent.browse` directly and returns visible page text plus screenshot data for model inspection. It does not create or close browsers, send frontend UI events, or hard-code QR selectors.
- Follow-up issue: `click(description)` cannot target icon-only controls such as the Xiaohongshu QR-login corner because the browser element extractor drops clickable elements that have no text, aria label, or placeholder.
- Boundary decision: fix icon-only targeting in `BrowserAutomation` / `element_finder`, not in `remote_login`.
- Current runtime issue: screenshots are now rendered, but too broadly. The initial `remote_login` screenshot and follow-up `take_screenshot` output should not automatically be user-visible. Only the QR-scan handoff should send the QR screenshot and trigger `ask_user`.
- LinkedIn credential-login e2e initially failed because the model refused a social-site login without using tools. Prompt guidance now explicitly allows user-mediated login when the user asks for it and requires credentials to be requested through `ask_user`.
- Follow-up serialization issue fixed: injected `agent` parameters no longer stream into tool-result args or frontend UI.
- Over-engineering cleanup: old `request_*` helper names and compatibility aliases were removed; QR uses the existing `ask_user` tool instead of a duplicate wrapper; browser lookup uses only `agent.browse`.
- Browser reuse finding: hosted `co ai` creates a fresh Agent per session, and Playwright's sync browser object is thread-bound. Sharing one BrowserAutomation instance across new chat sessions caused `Cannot switch to a different thread`, so cross-session browser-object reuse is not safe in the current architecture.
- Boundary correction: `remote_login` was removed as a tool because it duplicated `open_browser` / `go_to` / `take_screenshot`. co ai now exposes only the two login-specific user handoff tools, and prompt guidance tells the model to use ordinary browser tools for navigation and page inspection.
- Frontend polish: oo-chat's credential ask-user form was restyled to a compact neutral card with simple borders and no amber/yellow treatment.
- Frontend persistence issue found: QR screenshots and other generated image data were being persisted into `localStorage` under `co:agent:{address}:session:{sessionId}`, causing `QuotaExceededError`. The SDK store now strips base64 data URLs from persisted `messages`, `ui`, and `session` while keeping runtime images available in memory.
- Local oo-chat integration note: the local npm package copy under `oo-chat/node_modules/connectonion` was patched to match the SDK source fix because oo-chat was still loading the published `connectonion@0.1.4` store implementation.
- Local oo-chat now depends on `file:../connectonion-ts` and no longer uses `transpilePackages: ['connectonion']`; this keeps local dev on the fixed SDK while avoiding the Turbopack/CommonJS `require is not defined` path.
- Browser cleanup follow-up: `close_browser` is now a login/browser-flow handoff tool. It calls the existing `agent.browse.close()` after login succeeds or the login flow is abandoned, so the persistent profile is saved and the server-side browser process is released.

## Verification

- `/opt/homebrew/bin/python3 -m pytest tests/unit/test_browser_automation.py tests/unit/test_browser_tools.py tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_agent_main.py tests/unit/test_co_ai_prompts_assembler.py tests/unit/test_co_ai_system_reminder_plugin.py -q`
- `/opt/homebrew/bin/python3 -m py_compile connectonion/useful_tools/browser_tools/browser.py connectonion/useful_tools/login_handoff.py connectonion/cli/co_ai/plugins/login_cleanup.py connectonion/cli/co_ai/plugins/system_reminder.py`
- `git diff --check`
- `/opt/homebrew/bin/python3 -m pytest tests/unit/test_browser_automation.py tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_agent_main.py tests/unit/test_co_ai_prompts_assembler.py tests/unit/test_co_ai_system_reminder_plugin.py -q`
- `/opt/homebrew/bin/python3 -m py_compile connectonion/useful_tools/browser_tools/browser.py connectonion/useful_tools/login_handoff.py connectonion/cli/co_ai/plugins/login_cleanup.py connectonion/cli/co_ai/plugins/system_reminder.py`
- `git diff --check`
- `/opt/homebrew/bin/python3 -m pytest tests/unit/test_image_result_formatter.py tests/e2e/test_image_formatter_plugin.py tests/unit/test_co_ai_agent_main.py tests/unit/test_login_handoff_tools.py -q`
- `/opt/homebrew/bin/python3 -m pytest tests/unit/test_image_result_formatter.py tests/e2e/test_image_formatter_plugin.py tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_agent_main.py tests/unit/test_co_ai_prompts_assembler.py tests/unit/test_co_ai_system_reminder_plugin.py tests/unit/test_browser_automation.py tests/unit/test_browser_tools.py -q`
- `/opt/homebrew/bin/python3 -m py_compile connectonion/useful_plugins/image_result_formatter.py connectonion/cli/co_ai/agent.py connectonion/cli/co_ai/plugins/__init__.py connectonion/useful_tools/login_handoff.py connectonion/useful_tools/browser_tools/browser.py connectonion/cli/co_ai/plugins/system_reminder.py`
- `git diff --check`
- `/opt/homebrew/bin/python3 -m pytest tests/unit/test_co_ai_agent_main.py tests/unit/test_login_handoff_tools.py tests/unit/test_browser_automation.py tests/unit/test_browser_tools.py -q`
- `/opt/homebrew/bin/python3 -m py_compile connectonion/cli/co_ai/main.py connectonion/cli/co_ai/agent.py connectonion/useful_tools/browser_tools/browser.py connectonion/useful_tools/login_handoff.py`
- `git diff --check`
- `/opt/homebrew/bin/python3 -m pytest tests/unit/test_co_ai_prompts_assembler.py tests/unit/test_co_ai_system_reminder_plugin.py tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_agent_main.py -q`
- `/opt/homebrew/bin/python3 -m py_compile connectonion/cli/co_ai/plugins/system_reminder.py connectonion/cli/co_ai/prompts/assembler.py connectonion/useful_tools/login_handoff.py connectonion/cli/co_ai/agent.py`
- `git diff --check`
- `/opt/homebrew/bin/python3 -m pytest tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_prompts_assembler.py -q`
- `/opt/homebrew/bin/python3 -m pytest tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_agent_main.py tests/unit/test_co_ai_prompts_assembler.py -q`
- `/opt/homebrew/bin/python3 -m py_compile connectonion/useful_tools/login_handoff.py connectonion/cli/co_ai/agent.py connectonion/cli/co_ai/prompts/assembler.py`
- `git diff --check`
- Local restart check: `curl -sS http://localhost:8000/health`
- `/opt/homebrew/bin/python3 -m pytest tests/unit/test_login_handoff_tools.py::test_send_credentials_form_to_user_derives_missing_field_names_from_labels -q`
- `/opt/homebrew/bin/python3 -m pytest tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_agent_main.py tests/unit/test_co_ai_prompts_assembler.py -q`
- `/opt/homebrew/bin/python3 -m py_compile connectonion/useful_tools/login_handoff.py connectonion/cli/co_ai/agent.py connectonion/cli/co_ai/prompts/assembler.py`
- `git diff --check`
- `python3 -m pytest tests/unit/test_remote_login_tool.py tests/unit/test_co_ai_agent_main.py`
- `python3 -m py_compile connectonion/useful_tools/remote_login.py connectonion/cli/co_ai/agent.py`
- `git diff --check`
- `python3 -m pytest tests/unit/test_ask_user.py tests/unit/test_tool_executor.py tests/unit/test_remote_login_tool.py tests/unit/test_image_result_formatter.py tests/unit/test_co_ai_agent_main.py tests/unit/test_co_ai_prompts_assembler.py`
- Local restart verified with `co ai` on port 8000 and `oo-chat` on port 3000 at `http://localhost:3000/0xa0d98aa8f348e5ffa7c0f44204eb65dc17ccead6624d6f51e284cd34c9d9a89a`.
- Local LinkedIn login e2e verified after restart: `remote_login(https://www.linkedin.com/login)` ran, then the credential handoff rendered separate `账号` and `密码` fields in oo-chat, with the password field using `type="password"`.
- `python3 -m pytest tests/unit/test_remote_login_tool.py tests/unit/test_co_ai_agent_main.py::test_create_coding_agent tests/unit/test_co_ai_prompts_assembler.py::test_remote_login_prompt_allows_user_mediated_credential_login tests/unit/test_ask_user.py::TestAskUserTool::test_ask_user_sends_event_and_receives_answer tests/unit/test_co_ai_tools_misc.py::test_ask_user_round_trip`
- `python3 -m pytest tests/unit/test_remote_login_tool.py tests/unit/test_co_ai_agent_main.py tests/unit/test_co_ai_prompts_assembler.py tests/unit/test_ask_user.py tests/unit/test_tool_executor.py tests/unit/test_image_result_formatter.py`
- `python3 -m py_compile connectonion/useful_tools/remote_login.py connectonion/useful_tools/__init__.py connectonion/cli/co_ai/agent.py connectonion/core/tool_executor.py`
- `git diff --check`
- `python3 -m pytest tests/unit/test_remote_login_tool.py tests/unit/test_co_ai_agent_main.py tests/unit/test_co_ai_prompts_assembler.py tests/unit/test_ask_user.py tests/unit/test_tool_executor.py tests/unit/test_image_result_formatter.py tests/unit/test_co_ai_tools_misc.py`
- `python3 -m py_compile connectonion/useful_tools/remote_login.py connectonion/useful_tools/__init__.py connectonion/useful_tools/ask_user.py connectonion/cli/co_ai/tools/ask_user.py connectonion/cli/co_ai/agent.py connectonion/core/tool_executor.py`
- `git diff --check`
- `python3 -m pytest tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_agent_main.py::test_create_coding_agent tests/unit/test_co_ai_prompts_assembler.py::test_login_handoff_prompt_allows_user_mediated_credential_login`
- `python3 -m pytest tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_agent_main.py tests/unit/test_co_ai_prompts_assembler.py tests/unit/test_ask_user.py tests/unit/test_tool_executor.py tests/unit/test_image_result_formatter.py tests/unit/test_co_ai_tools_misc.py`
- `python3 -m py_compile connectonion/useful_tools/login_handoff.py connectonion/useful_tools/__init__.py connectonion/cli/co_ai/agent.py`
- Local LinkedIn smoke after restart: co ai used `open_browser`, `go_to`, and `send_credentials_form_to_user`; oo-chat rendered separate `账号` and `密码` fields.
- oo-chat component check: `npx eslint components/chat/chat-ask-user.tsx`
- SDK persistence smoke: simulated a 200k-character base64 image through oo-chat's loaded `connectonion/dist/react/store.js`; persisted localStorage payload stayed small and contained no `data:image/png;base64`.
- oo-chat checks: `npx eslint components/chat/chat-ask-user.tsx next.config.ts`; `npm run build`
- `python3 -m pytest tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_agent_main.py::test_create_coding_agent tests/unit/test_co_ai_prompts_assembler.py::test_login_handoff_prompt_allows_user_mediated_credential_login`
- `python3 -m pytest tests/unit/test_login_handoff_tools.py tests/unit/test_co_ai_agent_main.py tests/unit/test_co_ai_prompts_assembler.py tests/unit/test_ask_user.py tests/unit/test_tool_executor.py tests/unit/test_image_result_formatter.py tests/unit/test_co_ai_tools_misc.py`
- `python3 -m py_compile connectonion/useful_tools/login_handoff.py connectonion/useful_tools/__init__.py connectonion/cli/co_ai/agent.py`
