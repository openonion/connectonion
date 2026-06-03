"""Tests for server-side login user handoff tools."""

import importlib
from types import SimpleNamespace

import connectonion.useful_tools as useful_tools

login_handoff_mod = importlib.import_module("connectonion.useful_tools.login_handoff")


class FakePage:
    url = "https://example.com/login"


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


def test_request_login_from_user_qr_sends_screenshot_then_ask_user():
    browser = FakeBrowser()
    agent = SimpleNamespace(
        io=FakeIO(answer="I scanned it"),
        browse=browser,
    )

    result = login_handoff_mod.request_login_from_user(agent, "qr")

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
    assert browser.saved is True
    assert "I scanned it" in result
    assert "data:image/png;base64" not in result


def test_request_login_from_user_qr_requires_existing_browser_context():
    agent = SimpleNamespace(io=FakeIO(), tools=SimpleNamespace(_instances={}))

    result = login_handoff_mod.request_login_from_user(agent, "qr")

    assert 'mode="qr"' in result
    assert agent.io.sent == []


def test_request_login_from_user_credentials_sends_structured_ask_user():
    agent = SimpleNamespace(io=FakeIO(answer='{"username":"me@example.com","password":"secret"}'))

    result = login_handoff_mod.request_login_from_user(agent, "credentials")

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
    assert not hasattr(agent, "_login_credentials")
    assert "secret" not in result
    assert "me@example.com" not in result
    assert result == "Login credentials request sent to the user."


def test_request_login_from_user_message_sends_plain_ask_user():
    agent = SimpleNamespace(io=FakeIO(answer="Done"))

    result = login_handoff_mod.request_login_from_user(
        agent,
        "message",
        "Please enter the OTP shown on your phone.",
    )

    assert agent.io.sent == [
        {
            "type": "ask_user",
            "question": "Please enter the OTP shown on your phone.",
            "options": [],
            "multi_select": False,
        }
    ]
    assert result == "Login message sent to the user. User response: Done."


def test_request_login_from_user_requires_io():
    agent = SimpleNamespace(io=None)

    result = login_handoff_mod.request_login_from_user(agent, "credentials")

    assert "request_login_from_user requires agent.io" in result


def test_old_login_tool_names_are_not_exported():
    assert not hasattr(useful_tools, "remote_login")
    assert "remote_login" not in useful_tools.__all__
    assert not hasattr(useful_tools, "request_qr_scan")
    assert not hasattr(useful_tools, "request_login_credentials")
    assert not hasattr(useful_tools, "send_qr_to_user")
    assert not hasattr(useful_tools, "send_credentials_form_to_user")
    assert not hasattr(useful_tools, "type_saved_login_credential")
    assert not hasattr(useful_tools, "close_browser")
    assert "send_qr_to_user" not in useful_tools.__all__
    assert "send_credentials_form_to_user" not in useful_tools.__all__
    assert "type_saved_login_credential" not in useful_tools.__all__
    assert "close_browser" not in useful_tools.__all__
