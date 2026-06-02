# Implementation Plan

## Credential Field Name Fallback

1. [x] Record the scoped runtime follow-up in control docs.
2. [x] Add a failing test for custom credential fields that omit `name`.
3. [x] Update field normalization to derive stable field names.
4. [x] Run focused login handoff tests and syntax/diff checks.
5. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.
6. [x] Restart local co ai so the running test server uses the fix.

## Generalize Existing Credential Handoff Fields

1. [x] Record the scoped task in control docs.
2. [x] Add failing tests for arbitrary fields on `send_credentials_form_to_user`.
3. [x] Add failing tests for `type_saved_login_credential` typing non-username/password saved values.
4. [x] Update the existing login handoff implementation without adding new tool names.
5. [x] Update co ai prompt/tool guidance for OTP/2FA and arbitrary login fields.
6. [x] Run focused tests, syntax checks, and diff hygiene checks.
7. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

## Login Leaves Browser Open

1. [x] Record the narrowed login browser lifecycle task in control docs.
2. [x] Add/update failing tests for successful-login browser-open guidance.
3. [x] Update main login prompt, `close_browser` tool prompt, and browser lifecycle reminder.
4. [x] Run focused prompt/system-reminder tests, syntax checks, and diff hygiene checks.
5. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.
6. [x] Commit and push the prompt-only change.

## co ai Web Server Reuses One Agent Instance

1. [x] Record the new co ai agent-reuse task in control docs.
2. [x] Add a failing test proving `start_server()` passes one concrete agent instance to `host()`, not a per-request factory.
3. [x] Update `start_server()` to create the agent once and pass the instance to `host()`.
4. [x] Run focused co ai tests, syntax checks, and diff hygiene checks.
5. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.
6. [x] Commit, push, and restart local co ai for manual testing.

## PR #143 Auto-Display Screenshot Tool Results

1. [x] Record the new screenshot frontend-display task in control docs.
2. [x] Add the user-requested `login_cleanup.py` removal to the current task scope.
3. [x] Add/update failing tests that expect `image_result_formatter` to call `agent.io.send_image(...)` when IO is available.
4. [x] Add/update failing tests that expect co ai not to export/register `login_cleanup`.
5. [x] Restore `agent.io.send_image(data_url)` while preserving multimodal `image_url` insertion for the LLM.
6. [x] Remove `login_cleanup.py` and its co ai registration/export.
7. [x] Run focused image formatter, browser/login/co-ai, syntax, and diff checks.
8. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.
9. [x] Commit and push the PR update.

## PR #143 Main Merge Conflict

1. [x] Fetch latest `origin/main` and confirm PR #143 is `CONFLICTING`.
2. [x] Merge `origin/main` into the PR branch and identify conflict files.
3. [x] Resolve `connectonion/useful_tools/browser_tools/browser.py` by preserving main updates plus close-before-reopen behavior.
4. [x] Run focused tests, syntax checks, and diff hygiene checks.
5. [x] Update `STATUS.md`, `TASKS.md`, and this plan with final verification.
6. [x] Commit and push the merge-conflict resolution.

## PR #143 Browser Open Closes Previous Instance

1. [x] Verify the new PR comment and current browser cleanup boundary.
2. [x] Add a failing regression test for `open_browser()` replacing an existing browser instance by closing the old context.
3. [x] Update `BrowserAutomation.open_browser()` to close stale live state before launching a new persistent context.
4. [x] Add an `open_browser` system reminder for browser lifecycle cleanup guidance.
5. [x] Run focused browser/login/co-ai tests, syntax checks, and diff hygiene checks.
6. [x] Update `STATUS.md`, `TASKS.md`, and this plan with the result.

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
