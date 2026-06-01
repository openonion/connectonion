# Tool: Send Credentials Form To User

Use `send_credentials_form_to_user()` when a server-side login page needs a username, email, phone number, or password.

## Behavior

- Sends a structured `ask_user` event with account and password fields.
- Waits for the user to submit the fields.
- Returns the submitted credentials for the current login flow.
- Does not decide whether login succeeded.

## Guidelines

- Use this instead of the generic `ask_user` tool for username/password login pages.
- Do not ask the user to type credentials into one free-form text box.
- After this tool returns, use the credentials only to fill the current login page.
- Do not repeat credentials in assistant messages.
- Do not say login succeeded until the browser page shows a logged-in state.
