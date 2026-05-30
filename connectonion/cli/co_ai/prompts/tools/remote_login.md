# Tool: Remote Login

Use `remote_login(url)` when the user asks you to log in to a website or service.

## Behavior

- Opens the target login page in the agent-side browser.
- Sends screenshots to the user only when the page needs remote visual action, such as scanning a QR code or reviewing a failed login state.
- Asks for account/password together when the page needs credentials.
- The tool checks the browser page itself to decide whether login succeeded; do not ask the user whether it worked.
- Login state is persisted in the dedicated login profile and reused on later calls.

## When to Use

- User says "帮我登录", "login", "sign in", or gives a site URL that requires authentication.
- User needs the agent to prepare a persistent server-side authenticated browser session.

## Guidelines

- Pass the actual login or target site URL as `url`.
- If the user did not provide a URL, ask for the URL first.
- Do not manually ask whether the page uses QR code or password login; the tool decides.
- After the tool returns, summarize the result briefly.
