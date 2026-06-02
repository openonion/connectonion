# Tasks

## Current Task: PR #143 Auto-Display Screenshot Tool Results

Status: complete

Context:

- Reviewer/user wants the removed `agent.io.send_image(data_url)` path restored in `image_result_formatter`.
- Desired behavior: all screenshot/image tool results should still be model-visible and also display directly in the frontend when `agent.io` is available.
- Prior localStorage quota protection should remain in the frontend/SDK persistence layer; this task changes real-time WebSocket display, not persistence.
- User also requested deleting `connectonion/cli/co_ai/plugins/login_cleanup.py`; browser cleanup should now be explicit through `close_browser` and lifecycle-safe through `open_browser()` closing stale contexts.

Scope:

- Update image formatter tests so image tool results call `agent.io.send_image(...)` when IO is available.
- Keep the inserted multimodal `image_url` message for agent/LLM visibility.
- Restore real-time frontend image delivery from `image_result_formatter`.
- Remove `login_cleanup` from co ai plugin exports and agent registration.
- Remove obsolete login cleanup tests that exercise the deleted plugin, while keeping direct `close_browser` tool coverage.
- Run focused image formatter tests plus relevant browser/login/co-ai checks.

Expected result:

- Ordinary screenshot/image tool results appear in the frontend immediately.
- The same images remain visible to the LLM through `current_session["messages"]`.
- Full base64 images still should not be persisted to localStorage by the frontend/SDK persistence layer.
- co ai no longer imports or registers a completion-time login cleanup hook.

Result:

- `image_result_formatter` now builds one `data:{mime_type};base64,...` URL per image tool result, inserts it as a multimodal `image_url` message for the LLM, and sends the same data URL through `agent.io.send_image(...)` when IO is available.
- Image formatter unit and e2e coverage now asserts frontend IO delivery for single and multiple image tool results.
- `connectonion/cli/co_ai/plugins/login_cleanup.py` was deleted.
- co ai no longer exports or registers `login_cleanup`; browser cleanup remains available through the explicit `close_browser` tool and stale contexts are closed by `open_browser()`.
- Focused image, login handoff, co ai, browser, syntax, and diff checks pass.

## Current Task: PR #143 Main Merge Conflict

Status: complete

Context:

- GitHub reports PR #143 as `CONFLICTING` against `main`.
- Latest `origin/main` conflicts with the PR branch in `connectonion/useful_tools/browser_tools/browser.py`.
- The resolution must preserve `main` updates while keeping PR #143's browser lifecycle behavior.

Scope:

- Merge latest `origin/main` into the PR #143 branch.
- Resolve the `browser.py` conflict by keeping the current main browser-tool code and the PR behavior that closes any existing browser context before reopening.
- Run focused browser/login/co-ai tests and syntax/diff checks.

Result:

- `origin/main` was merged into the PR branch.
- The `browser.py` conflict was resolved with close-before-reopen behavior preserved.
- Focused browser/login/co-ai tests, syntax checks, and diff hygiene checks pass after the merge.

## Current Task: PR #143 Browser Open Closes Previous Instance

Status: complete

Context:

- PR #143 has a new review comment on `connectonion/cli/co_ai/plugins/login_cleanup.py` asking whether continuing a login conversation leaves the previous browser instance open.
- `login_cleanup` closes the browser only after a login handoff turn marked `_login_handoff_active`.
- The safer lifecycle is for `open_browser()` itself to close any existing live browser context before launching a new persistent browser instance.

Scope:

- Add regression coverage proving `BrowserAutomation.open_browser()` closes an existing browser/page/playwright context before opening a new one.
- Change browser lifecycle code so opening a new browser instance releases any previous instance instead of returning early with `Browser already open`.
- Add system-reminder guidance for `open_browser` so the model still calls `close_browser` when the flow finishes.
- Keep the existing persistent profile path behavior so login cookies survive across browser restarts.

Result:

- `BrowserAutomation.open_browser()` now closes any existing browser/page/playwright state before launching a fresh persistent browser context.
- The browser profile path stays unchanged, so cookies and login state persist across the close/reopen boundary.
- Added an `open_browser` system reminder that tells the agent the previous context is closed on open and to call `close_browser` when the browser/login flow finishes.
- Added regression coverage for closing the old context before reopening and for the new browser lifecycle reminder.

## Current Task: Login Handoff Tool Boundary

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
