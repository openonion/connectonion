# Tool: Send Credentials Form To User

Use `send_credentials_form_to_user()` when a server-side login page needs user-provided login fields such as username, email, phone number, password, verification code, OTP, 2FA, or captcha code.

## Behavior

- Sends a structured `ask_user` event with the requested fields.
- Waits for the user to submit the fields.
- Saves the submitted credentials or verification values for the current login flow without returning their raw values.
- Does not decide whether login succeeded.

## Guidelines

- Use this instead of the generic `ask_user` tool for username/password, OTP, 2FA, verification code, phone, email, captcha code, or other login form fields.
- Call with no arguments for the default username/password form.
- When the page asks for different fields, pass `question` and `fields`, for example a text field named `verification_code` with label `Verification code`.
- After this tool returns, focus the relevant input fields and call `type_saved_login_credential(field="verification_code")` or the matching field name to fill the current login page in the same turn.
- Do not call `keyboard_type` with a user-provided password or verification code.
- Do not repeat credentials in assistant messages.
- Do not say login succeeded until the browser page shows a logged-in state.
- Leave the browser open after login succeeds.
