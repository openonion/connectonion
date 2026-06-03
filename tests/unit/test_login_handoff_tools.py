"""Tests for server-side login user handoff tools."""

import importlib
from types import SimpleNamespace

import pytest

import connectonion.useful_tools as useful_tools

login_handoff_mod = importlib.import_module("connectonion.useful_tools.login_handoff")


class FakeKeyboard:
    def __init__(self):
        self.typed = []

    def type(self, text):
        self.typed.append(text)


class FakePage:
    url = "https://example.com/login"

    def __init__(self):
        self.keyboard = FakeKeyboard()


class FakeBrowser:
    def __init__(self):
        self.browser = object()
        self.page = FakePage()
        self.screenshot_calls = []
        self.saved = False
        self.closed = False

    def take_screenshot(self, path=None, full_page=False):
        self.screenshot_calls.append((path, full_page))
        return "data:image/png;base64,ZmFrZS1wbmc="

    def _save_context(self):
        self.saved = True

    def close(self):
        self.closed = True
        self.browser = None
        self.page = None
        return "Browser closed"


class FakeIO:
    def __init__(self, answer=""):
        self.sent = []
        self.receives = 0
        self.answer = answer

    def send(self, payload):
        self.sent.append(payload)

    def send_image(self, image_data):
        self.send({"type": "agent_image", "image": image_data})

    def receive(self):
        self.receives += 1
        return {"answer": self.answer}


def test_send_qr_to_user_sends_screenshot_then_ask_user():
    browser = FakeBrowser()
    agent = SimpleNamespace(
        io=FakeIO(answer="I scanned it"),
        browse=browser,
    )

    result = login_handoff_mod.send_qr_to_user(agent)

    assert browser.screenshot_calls == [(None, False)]
    assert agent.io.sent == [
        {
            "type": "agent_image",
            "image": "data:image/png;base64,ZmFrZS1wbmc=",
        },
        {
            "type": "ask_user",
            "question": "Please scan the QR code in the screenshot. After scanning it, choose \"I scanned it. Continue checking login status.\"",
            "options": ["I scanned it. Continue checking login status."],
            "multi_select": False,
        },
    ]
    assert agent.io.receives == 1
    assert agent._login_handoff_active is True
    assert browser.saved is True
    assert "I scanned it" in result
    assert "data:image/png;base64" not in result


def test_send_qr_to_user_requires_existing_browser_context():
    agent = SimpleNamespace(io=FakeIO(), tools=SimpleNamespace(_instances={}))

    result = login_handoff_mod.send_qr_to_user(agent)

    assert "requires agent.browse and agent.io" in result
    assert agent.io.sent == []


def test_send_credentials_form_to_user_sends_structured_ask_user():
    agent = SimpleNamespace(io=FakeIO(answer='{"username":"me@example.com","password":"secret"}'))

    result = login_handoff_mod.send_credentials_form_to_user(agent)

    assert agent.io.sent == [
        {
            "type": "ask_user",
            "text": "Please enter your username and password.",
            "question": "Please enter your username and password.",
            "options": [],
            "multi_select": False,
            "input_type": "credentials",
            "fields": [
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
            ],
        }
    ]
    assert agent.io.receives == 1
    assert agent._login_handoff_active is True
    assert agent._login_credentials == {"username": "me@example.com", "password": "secret"}
    assert "secret" not in result
    assert "me@example.com" not in result
    assert "type_saved_login_credential" in result


def test_send_credentials_form_to_user_accepts_custom_login_fields():
    agent = SimpleNamespace(
        io=FakeIO(
            answer=(
                '{"username":"me@example.com","password":"secret",'
                '"verification_code":"123456"}'
            )
        )
    )

    result = login_handoff_mod.send_credentials_form_to_user(
        agent,
        question="Please enter your username, password, and verification code.",
        fields=[
            {"name": "username", "label": "Username", "type": "text", "required": True},
            {"name": "password", "label": "Password", "type": "password", "required": True},
            {
                "name": "verification_code",
                "label": "Verification code",
                "type": "text",
                "required": True,
                "autocomplete": "one-time-code",
            },
        ],
    )

    assert agent.io.sent == [
        {
            "type": "ask_user",
            "text": "Please enter your username, password, and verification code.",
            "question": "Please enter your username, password, and verification code.",
            "options": [],
            "multi_select": False,
            "input_type": "credentials",
            "fields": [
                {"name": "username", "label": "Username", "type": "text", "required": True},
                {"name": "password", "label": "Password", "type": "password", "required": True},
                {
                    "name": "verification_code",
                    "label": "Verification code",
                    "type": "text",
                    "required": True,
                    "autocomplete": "one-time-code",
                },
            ],
        }
    ]
    assert agent._login_handoff_active is True
    assert agent._login_credentials == {
        "username": "me@example.com",
        "password": "secret",
        "verification_code": "123456",
    }
    assert "verification_code" in result
    assert "secret" not in result
    assert "123456" not in result


def test_send_credentials_form_to_user_requires_custom_field_names():
    agent = SimpleNamespace(
        io=FakeIO(answer='{"email_or_phone":"me@example.com","password":"secret"}')
    )

    with pytest.raises(ValueError, match="non-empty name"):
        login_handoff_mod.send_credentials_form_to_user(
            agent,
            question="Please enter your LinkedIn credentials.",
            fields=[
                {"label": "Email or phone", "type": "text", "required": True},
                {"name": "password", "label": "Password", "type": "password", "required": True},
            ],
        )

    assert agent.io.sent == []


def test_type_saved_login_credential_types_without_returning_secret():
    browser = FakeBrowser()
    agent = SimpleNamespace(
        browse=browser,
        _login_credentials={"username": "me@example.com", "password": "secret"},
    )

    result = login_handoff_mod.type_saved_login_credential(agent, "password")

    assert browser.page.keyboard.typed == ["secret"]
    assert result == "Typed saved password into the focused browser field."
    assert "secret" not in result


def test_type_saved_login_credential_types_custom_saved_field():
    browser = FakeBrowser()
    agent = SimpleNamespace(
        browse=browser,
        _login_credentials={"verification_code": "123456"},
    )

    result = login_handoff_mod.type_saved_login_credential(agent, "verification_code")

    assert browser.page.keyboard.typed == ["123456"]
    assert result == "Typed saved verification_code into the focused browser field."
    assert "123456" not in result


def test_type_saved_login_credential_requires_saved_value():
    agent = SimpleNamespace(browse=FakeBrowser(), _login_credentials={})

    result = login_handoff_mod.type_saved_login_credential(agent, "password")

    assert result == "No saved password credential is available."


def test_send_credentials_form_to_user_requires_io():
    agent = SimpleNamespace(io=None)

    result = login_handoff_mod.send_credentials_form_to_user(agent)

    assert "requires agent.io" in result


def test_close_browser_closes_existing_browser():
    browser = FakeBrowser()
    agent = SimpleNamespace(
        browse=browser,
        _login_handoff_active=True,
        _login_credentials={"username": "me@example.com", "password": "secret"},
    )

    result = login_handoff_mod.close_browser(agent)

    assert result == "Browser closed"
    assert browser.closed is True
    assert browser.browser is None
    assert browser.page is None
    assert not hasattr(agent, "_login_handoff_active")
    assert not hasattr(agent, "_login_credentials")


def test_close_browser_is_noop_when_browser_already_closed():
    browser = FakeBrowser()
    browser.browser = None
    browser.page = None
    agent = SimpleNamespace(browse=browser)

    result = login_handoff_mod.close_browser(agent)

    assert result == "Browser is already closed."
    assert browser.closed is False


def test_close_browser_requires_agent_browser_context():
    agent = SimpleNamespace()

    result = login_handoff_mod.close_browser(agent)

    assert "requires agent.browse" in result


def test_old_login_tool_names_are_not_exported():
    assert not hasattr(useful_tools, "remote_login")
    assert "remote_login" not in useful_tools.__all__
    assert not hasattr(useful_tools, "request_qr_scan")
    assert not hasattr(useful_tools, "request_login_credentials")
