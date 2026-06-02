"""User handoff tools for server-side login flows."""

import json
import re
from typing import Any, Dict, List, Optional

from .ask_user import ask_user

_QR_SCAN_OPTION = "已扫码，继续检查登录状态"
_DEFAULT_CREDENTIAL_FIELDS = [
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
]
_FIELD_KEYS = {"name", "label", "type", "required", "autocomplete", "placeholder"}


def _clear_saved_credentials(agent) -> None:
    for attr in ("_login_credentials", "_login_handoff_active"):
        if hasattr(agent, attr):
            delattr(agent, attr)


def _field_name_from_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""

    parts = re.findall(r"[a-z0-9]+", text)
    if parts:
        return "_".join(parts)

    parts = re.findall(r"\w+", text)
    return "_".join(parts)


def _derive_field_name(field: Dict[str, Any], index: int) -> str:
    for key in ("label", "placeholder", "autocomplete"):
        name = _field_name_from_text(field.get(key))
        if name:
            return name

    input_type = str(field.get("type", "")).strip().lower()
    if input_type and input_type != "text":
        return _field_name_from_text(input_type)

    return f"field_{index + 1}"


def _normalize_credential_fields(fields: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not fields:
        return [field.copy() for field in _DEFAULT_CREDENTIAL_FIELDS]

    normalized = []
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            raise TypeError("Credential fields must be JSON objects.")

        name = str(field.get("name", "")).strip()
        if not name:
            name = _derive_field_name(field, index)

        clean = {key: field[key] for key in _FIELD_KEYS if key in field}
        clean["name"] = name
        clean.setdefault("label", name.replace("_", " ").replace("-", " ").title())
        clean.setdefault("type", "text")
        clean["required"] = bool(clean.get("required", True))
        normalized.append(clean)

    return normalized


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


def send_credentials_form_to_user(
    agent,
    question: str = "",
    fields: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Ask the user for login credentials or verification fields."""
    if not agent.io:
        return "send_credentials_form_to_user requires agent.io."

    credential_fields = _normalize_credential_fields(fields)
    prompt = question or (
        "请输入账号和密码。" if fields is None else "请输入当前登录页面需要的信息。"
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
