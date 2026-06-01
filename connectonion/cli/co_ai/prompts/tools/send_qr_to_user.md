# Tool: Send QR To User

Use `send_qr_to_user()` only after you have confirmed that the current server-side browser page is showing a QR code that the user must scan.

## Behavior

- Captures the current browser viewport from the existing agent-side browser context.
- Sends that screenshot to the frontend as the user-facing QR image.
- Immediately sends an `ask_user` prompt asking the user to scan the QR code and confirm.
- Waits for the user's confirmation before returning.
- Does not decide whether login succeeded.

## Guidelines

- Do not use this for ordinary browser screenshots.
- Do not call it before the browser is on the QR-code login screen.
- Do not call `take_screenshot` just to send a QR image to the user; use this tool instead.
- After this tool returns, inspect the browser state in the same turn before saying login succeeded.
- If login is not complete yet, ask the user for the next required action with `ask_user`.
- Do not end the turn by asking the user to send a later chat message after scanning.
