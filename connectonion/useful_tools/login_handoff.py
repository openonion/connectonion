"""User handoff tools for server-side login flows."""

import json
from typing import Any, Dict, List, Optional

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


def _clear_saved_credentials(agent) -> None:
    for attr in ("_login_credentials", "_login_handoff_active"):
        if hasattr(agent, attr):
            delattr(agent, attr)


def _credential_fields(fields: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not fields:
        return [field.copy() for field in _DEFAULT_CREDENTIAL_FIELDS]

    for field in fields:
        if not isinstance(field, dict):
            raise TypeError("Credential fields must be JSON objects.")
        name = str(field.get("name", "")).strip()
        if not name:
            raise ValueError("Credential fields must include a non-empty name.")

    return [field.copy() for field in fields]


def _parse_form_answer(answer) -> Dict[str, Any]:
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

    agent._login_handoff_active = True
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
    question: str = "",
    fields: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Ask the user for login credentials or verification fields."""
    if not agent.io:
        return "send_credentials_form_to_user requires agent.io."

    credential_fields = _credential_fields(fields)
    prompt = question or (
        "Please enter your username and password."
        if fields is None
        else "Please enter the information required by the current login page."
    )
    agent.io.send({
        "type": "ask_user",
        "text": prompt,
        "question": prompt,
        "options": [],
        "multi_select": False,
        "input_type": "credentials",
        "fields": credential_fields,
    })
    answer = agent.io.receive().get("answer", "")
    credentials = _parse_form_answer(answer)

    saved = {}
    for field in credential_fields:
        name = field["name"]
        value = credentials.get(name)
        if value in (None, ""):
            if field.get("required", True):
                return "No credentials were provided."
            continue
        saved[name] = str(value)

    if not saved:
        return "No credentials were provided."

    agent._login_handoff_active = True
    agent._login_credentials = saved
    field_names = ", ".join(saved)
    return (
        f"Credentials saved for this login flow for fields: {field_names}. "
        "Focus each matching browser field and call "
        "type_saved_login_credential(field=\"field_name\"). Do not use "
        "keyboard_type for saved credentials or verification codes."
    )


def type_saved_login_credential(agent, field: str) -> str:
    """Type a saved login credential into the focused browser field."""
    field = str(field).strip()
    if not field:
        return "field is required."

    credentials = getattr(agent, "_login_credentials", None) or {}
    value = credentials.get(field)
    if not value:
        return f"No saved {field} credential is available."

    browser = getattr(agent, "browse", None)
    page = getattr(browser, "page", None) if browser else None
    if not page:
        return "type_saved_login_credential requires an open agent.browse page."

    page.keyboard.type(value)
    return f"Typed saved {field} into the focused browser field."


def close_browser(agent) -> str:
    """Close the agent-side browser after a login/browser flow is finished."""
    browser = getattr(agent, "browse", None)
    if not browser:
        _clear_saved_credentials(agent)
        return "close_browser requires agent.browse."

    if not getattr(browser, "browser", None) and not getattr(browser, "page", None):
        _clear_saved_credentials(agent)
        return "Browser is already closed."

    close = getattr(browser, "close", None)
    if not callable(close):
        _clear_saved_credentials(agent)
        return "agent.browse does not support close()."

    result = close()
    _clear_saved_credentials(agent)
    return result
