"""User handoff tools for server-side login flows."""

from typing import Literal

from pydantic import BaseModel, Field

from .ask_user import ask_user

_QR_SCAN_OPTION = "I scanned it. Continue checking login status."


class LoginCredentialField(BaseModel):
    name: str
    label: str
    type: Literal["text", "password"]
    required: bool = True
    autocomplete: str


class LoginUserRequest(BaseModel):
    type: Literal["ask_user"] = "ask_user"
    text: str | None = None
    question: str
    options: list[str] = Field(default_factory=list)
    multi_select: bool = False
    input_type: Literal["credentials"] | None = None
    fields: list[LoginCredentialField] | None = None


_CREDENTIAL_FIELDS = [
    LoginCredentialField(
        name="username",
        label="Username",
        type="text",
        autocomplete="username",
    ),
    LoginCredentialField(
        name="password",
        label="Password",
        type="password",
        autocomplete="current-password",
    ),
]

# Frontend contract:
# - mode="qr" sends the current browser screenshot as an image, then an ask_user event.
# - mode="credentials" sends one ask_user event with input_type="credentials".
# - mode="message" sends one plain ask_user event for login-related user action.
# TODO: The frontend should consume credentials securely from the credentials
# event. The agent tool should only request the login step, not type or persist
# passwords itself.


def request_user_login(
    agent,
    mode: str,
    message: str = "",
) -> str:
    """Send one login handoff request to the user."""
    if not agent.io:
        return "request_user_login requires agent.io."

    mode = str(mode).strip().lower()
    if mode == "qr":
        browser = getattr(agent, "browse", None)
        if not browser:
            return "request_user_login(mode=\"qr\") requires agent.browse."

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
        payload = LoginUserRequest(
            text=prompt,
            question=prompt,
            input_type="credentials",
            fields=_CREDENTIAL_FIELDS,
        )
        agent.io.send(payload.model_dump(exclude_none=True))
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
