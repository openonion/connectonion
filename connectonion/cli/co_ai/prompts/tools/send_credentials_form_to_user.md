# Tool: Send Credentials Form To User

Use `send_credentials_form_to_user()` when a server-side login page needs a username and password.

## Behavior

- Sends a structured `ask_user` event with username and password fields.
- Waits for the user to submit the fields.
- Saves the submitted username and password for the current login flow without returning their raw values.
- Does not decide whether login succeeded.

## Guidelines

- Use this instead of the generic `ask_user` tool for username/password login pages.
- After this tool returns, focus the username field and call `type_saved_login_credential(field="username")`, then focus the password field and call `type_saved_login_credential(field="password")`.
- Do not call `keyboard_type` with a user-provided password.
- Do not repeat credentials in assistant messages.
- Do not say login succeeded until the browser page shows a logged-in state.
- Leave the browser open after login succeeds.
