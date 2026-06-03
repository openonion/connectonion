# Tool: Type Saved Login Credential

Use `type_saved_login_credential(field)` after `send_credentials_form_to_user()` returns and you have focused the correct login input field in the server-side browser.

## Behavior

- Types the saved username or password into the currently focused browser field.
- Does not expose the saved value in tool arguments, trace output, or assistant messages.

## Guidelines

- First click the username/email/phone field, then call `type_saved_login_credential(field="username")`.
- First click the password field, then call `type_saved_login_credential(field="password")`.
- Do not call `keyboard_type` with a user-provided password.
- If the login page reports incorrect credentials, ask the user for corrected credentials with `send_credentials_form_to_user` instead of repeating the old password.
