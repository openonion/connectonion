"""User handoff tools for server-side login flows."""

import json

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
_CREDENTIAL_FIELDS = {"username", "password"}


def _clear_saved_credentials(agent) -> None:
    if hasattr(agent, "_login_credentials"):
        delattr(agent, "_login_credentials")


def _parse_form_answer(answer) -> dict:
    if isinstance(answer, str):
        if not answer:
            return {}
        answer = json.loads(answer)

    if not isinstance(answer, dict):
        raise TypeError("Credential answer must be a JSON object.")

    return answer


def send_qr_to_user(agent) -> str:
    """Send the current browser screenshot to the user and wait for QR scan."""
    browser = getattr(agent, "browse", None)
    if not browser or not agent.io:
        return "send_qr_to_user requires agent.browse and agent.io."

    screenshot = browser.take_screenshot()
    if screenshot:
        agent.io.send_image(screenshot)

    answer = ask_user(
        agent,
        "Please scan the QR code in the screenshot. After scanning it, choose \"I scanned it. Continue checking login status.\"",
        [_QR_SCAN_OPTION],
    )
    browser._save_context()

    response = answer.strip() or "(no answer)"
    return (
        "QR scan request sent to the user with the current browser screenshot. "
        f"User response: {response}. Continue by checking the browser login "
        "state before claiming success."
    )


def send_credentials_form_to_user(
    agent,
    question: str = "Please enter your username and password.",
) -> str:
    """Ask the user for username/password without exposing values to the LLM."""
    if not agent.io:
        return "send_credentials_form_to_user requires agent.io."

    agent.io.send({
        "type": "ask_user",
        "text": question,
        "question": question,
        "options": [],
        "multi_select": False,
        "input_type": "credentials",
        "fields": [field.copy() for field in _DEFAULT_CREDENTIAL_FIELDS],
    })
    answer = agent.io.receive().get("answer", "")
    credentials = _parse_form_answer(answer)
    username = credentials.get("username")
    password = credentials.get("password")
    if not username or not password:
        return "No credentials were provided."

    agent._login_credentials = {
        "username": str(username),
        "password": str(password),
    }
    return (
        "Credentials saved for this login flow. Focus the username field and "
        "call type_saved_login_credential(field=\"username\"), then focus the "
        "password field and call type_saved_login_credential(field=\"password\"). "
        "Do not use keyboard_type for saved credentials."
    )


def type_saved_login_credential(agent, field: str) -> str:
    """Type a saved login credential into the focused browser field."""
    field = str(field).strip()
    if field not in _CREDENTIAL_FIELDS:
        return 'field must be "username" or "password".'

    credentials = getattr(agent, "_login_credentials", None) or {}
    value = credentials.get(field)
    if not value:
        return f"No saved {field} credential is available."

    browser = getattr(agent, "browse", None)
    page = getattr(browser, "page", None) if browser else None
    if not page:
        return "type_saved_login_credential requires an open agent.browse page."

    page.keyboard.type(value)
    if field == "password":
        _clear_saved_credentials(agent)
    return f"Typed saved {field} into the focused browser field."
