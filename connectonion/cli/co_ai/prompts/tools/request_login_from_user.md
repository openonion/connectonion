# Tool: Request Login From User

Use `request_login_from_user(mode, message)` when a server-side login flow needs the user to act.

## Modes

- `mode="qr"`: sends the current browser screenshot to the user, then asks them to confirm after scanning the QR code.
- `mode="credentials"`: asks for username and password with a structured credential form.
- `mode="message"`: sends a plain login-related question or instruction and waits for the user's response.

## Guidelines

- Use one of these modes instead of adding separate login handoff tools.
- For username/password pages, use `mode="credentials"` and let the frontend handle credential submission securely.
- For QR-code pages, use `mode="qr"` only after the QR code is visible in the browser.
- For OTP, 2FA, captcha, approval, or other extra login steps, use `mode="message"` with a direct instruction.
- Do not say login succeeded until the browser page shows a logged-in state.
