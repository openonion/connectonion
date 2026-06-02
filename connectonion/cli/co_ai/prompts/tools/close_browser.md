# Tool: Close Browser

Use `close_browser()` only when the user asks to close the server-side browser or when an active browser flow is abandoned and cannot continue.

## Behavior

- Saves the persistent browser context.
- Closes the current server-side browser page/context.
- Releases the Playwright browser process.
- A later `open_browser` call also closes any previous live browser context before launching a fresh one.

## Guidelines

- Do not call this automatically after successful login.
- Leave the browser open after login succeeds so follow-up turns can keep using the logged-in page.
- Call this if the user explicitly asks to close the browser.
- Call this if the browser flow was abandoned or cannot continue and keeping the browser open would be misleading.
- Do not call this while you are still waiting for the user to scan a QR code, enter credentials, complete 2FA, or otherwise continue the active login flow.
