"""User handoff tools for server-side login flows."""

from .ask_user import ask_user

_QR_SCAN_OPTION = "已扫码，继续检查登录状态"


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
    return answer


def close_browser(agent) -> str:
    """Close the agent-side browser after a login/browser flow is finished."""
    browser = getattr(agent, "browse", None)
    if not browser:
        return "close_browser requires agent.browse."

    if not getattr(browser, "browser", None) and not getattr(browser, "page", None):
        return "Browser is already closed."

    close = getattr(browser, "close", None)
    if not callable(close):
        return "agent.browse does not support close()."

    return close()
