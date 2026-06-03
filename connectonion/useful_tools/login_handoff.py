"""User handoff tools for server-side login flows."""

from .ask_user import ask_user

_QR_SCAN_OPTION = "I scanned it. Continue checking login status."
_DEFAULT_CREDENTIAL_FIELDS = [
    {
        "name": "username",
        "label": "Username",
        "type": "text",
        "required": True,
        "autocomplete": "username",
    },
    {
        "name": "password",
        "label": "Password",
        "type": "password",
        "required": True,
        "autocomplete": "current-password",
    },
]

# Frontend contract:
# - mode="qr" sends the current browser screenshot as an image, then an ask_user event.
# - mode="credentials" sends one ask_user event with input_type="credentials".
# - mode="message" sends one plain ask_user event for login-related user action.
# TODO: The frontend should consume credentials securely from the credentials
# event. The agent tool should only request the login step, not type or persist
# passwords itself.


def request_login_from_user(
    agent,
    mode: str,
    message: str = "",
) -> str:
    """Send one login handoff request to the user."""
    if not agent.io:
        return "request_login_from_user requires agent.io."

    mode = str(mode).strip().lower()
    if mode == "qr":
        browser = getattr(agent, "browse", None)
        if not browser:
            return "request_login_from_user(mode=\"qr\") requires agent.browse."

        screenshot = browser.take_screenshot()
        if screenshot:
            agent.io.send_image(screenshot)

        answer = ask_user(
            agent,
            message or "Please scan the QR code in the screenshot. After scanning it, choose \"I scanned it. Continue checking login status.\"",
            [_QR_SCAN_OPTION],
        )
        browser._save_context()
        response = answer.strip() or "(no answer)"
        return (
            "Login QR request sent to the user with the current browser screenshot. "
            f"User response: {response}. Continue by checking the browser login "
            "state before claiming success."
        )

    if mode == "credentials":
        prompt = message or "Please enter your username and password."
        agent.io.send({
            "type": "ask_user",
            "text": prompt,
            "question": prompt,
            "options": [],
            "multi_select": False,
            "input_type": "credentials",
            "fields": [field.copy() for field in _DEFAULT_CREDENTIAL_FIELDS],
        })
        agent.io.receive()
        return "Login credentials request sent to the user."

    if mode == "message":
        answer = ask_user(
            agent,
            message or "Please complete the requested login step.",
            [],
        )
        response = answer.strip() or "(no answer)"
        return f"Login message sent to the user. User response: {response}."

    return 'mode must be "qr", "credentials", or "message".'
