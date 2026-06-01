"""User handoff tools for server-side login flows."""

import json

from .ask_user import ask_user

_QR_SCAN_OPTION = "已扫码，继续检查登录状态"
_CREDENTIAL_FIELDS = {"username", "password"}


def _clear_saved_credentials(agent) -> None:
    for attr in ("_login_credentials", "_login_handoff_active"):
        if hasattr(agent, attr):
            delattr(agent, attr)


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
        "请扫描截图中的二维码。完成扫码后，请选择“已扫码，继续检查登录状态”。",
        [_QR_SCAN_OPTION],
    )
    browser._save_context()

    response = answer.strip() or "(no answer)"
    return (
        "QR scan request sent to the user with the current browser screenshot. "
        f"User response: {response}. Continue by checking the browser login "
        "state before claiming success."
    )


def send_credentials_form_to_user(agent) -> str:
    """Ask the user for login credentials with username/password fields."""
    if not agent.io:
        return "send_credentials_form_to_user requires agent.io."

    agent.io.send({
        "type": "ask_user",
        "text": "请输入账号和密码。",
        "question": "请输入账号和密码。",
        "options": [],
        "multi_select": False,
        "input_type": "credentials",
        "fields": [
            {
                "name": "username",
                "label": "账号",
                "type": "text",
                "required": True,
                "autocomplete": "username",
            },
            {
                "name": "password",
                "label": "密码",
                "type": "password",
                "required": True,
                "autocomplete": "current-password",
            },
        ],
    })
    answer = agent.io.receive().get("answer", "")
    if not answer:
        return "No credentials were provided."

    credentials = json.loads(answer)
    if not isinstance(credentials, dict):
        raise TypeError("Credential answer must be a JSON object.")

    username = credentials.get("username")
    password = credentials.get("password")
    if not username or not password:
        return "No credentials were provided."

    agent._login_handoff_active = True
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
