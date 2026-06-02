# Tool: Type Saved Login Credential

Use `type_saved_login_credential(field)` after `send_credentials_form_to_user()` returns and you have focused the correct login input field in the server-side browser.

## Behavior

- Types the saved value for the requested field into the currently focused browser field.
- Works for username, password, verification code, OTP, 2FA, phone, email, captcha code, or any other field saved by `send_credentials_form_to_user`.
- Does not expose the saved value in tool arguments, trace output, or assistant messages.

## Guidelines

- First click the username/email/phone field, then call `type_saved_login_credential(field="username")`.
- First click the password field, then call `type_saved_login_credential(field="password")`.
- First click a verification code field, then call `type_saved_login_credential(field="verification_code")`.
- Do not call `keyboard_type` with a user-provided password or verification code.
- If the login page reports incorrect credentials or an expired code, ask the user for corrected fields with `send_credentials_form_to_user` instead of repeating the old value.
