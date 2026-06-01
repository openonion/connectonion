# Tool: Close Browser

Use `close_browser()` after a server-side browser flow is finished.

## Behavior

- Saves the persistent browser context.
- Closes the current server-side browser page/context.
- Releases the Playwright browser process so later sessions do not keep using the old open browser.

## Guidelines

- Call this after confirming a login succeeded.
- Call this if you decide the login flow cannot continue and you are about to report that to the user.
- Do not call this while you are still waiting for the user to scan a QR code, enter credentials, complete 2FA, or otherwise continue the active login flow.
