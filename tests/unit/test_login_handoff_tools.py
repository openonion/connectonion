"""Tests for server-side login user handoff tools."""

import importlib
from types import SimpleNamespace

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
        io=FakeIO(answer="已扫码"),
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
            "question": "请扫描截图中的二维码。完成扫码后，请选择“已扫码，继续检查登录状态”。",
            "options": ["已扫码，继续检查登录状态"],
            "multi_select": False,
        },
    ]
    assert agent.io.receives == 1
    assert agent._login_handoff_active is True
    assert browser.saved is True
    assert "已扫码" in result
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
        question="请输入账号、密码和验证码。",
        fields=[
            {"name": "username", "label": "账号", "type": "text", "required": True},
            {"name": "password", "label": "密码", "type": "password", "required": True},
            {
                "name": "verification_code",
                "label": "验证码",
                "type": "text",
                "required": True,
                "autocomplete": "one-time-code",
            },
        ],
    )

    assert agent.io.sent == [
        {
            "type": "ask_user",
            "text": "请输入账号、密码和验证码。",
            "question": "请输入账号、密码和验证码。",
            "options": [],
            "multi_select": False,
            "input_type": "credentials",
            "fields": [
                {"name": "username", "label": "账号", "type": "text", "required": True},
                {"name": "password", "label": "密码", "type": "password", "required": True},
                {
                    "name": "verification_code",
                    "label": "验证码",
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


def test_send_credentials_form_to_user_derives_missing_field_names_from_labels():
    agent = SimpleNamespace(
        io=FakeIO(answer='{"email_or_phone":"me@example.com","password":"secret"}')
    )

    result = login_handoff_mod.send_credentials_form_to_user(
        agent,
        question="Please enter your LinkedIn credentials.",
        fields=[
            {"label": "Email or phone", "type": "text", "required": True},
            {"label": "Password", "type": "password", "required": True},
        ],
    )

    assert agent.io.sent == [
        {
            "type": "ask_user",
            "text": "Please enter your LinkedIn credentials.",
            "question": "Please enter your LinkedIn credentials.",
            "options": [],
            "multi_select": False,
            "input_type": "credentials",
            "fields": [
                {
                    "name": "email_or_phone",
                    "label": "Email or phone",
                    "type": "text",
                    "required": True,
                },
                {
                    "name": "password",
                    "label": "Password",
                    "type": "password",
                    "required": True,
                },
            ],
        }
    ]
    assert agent._login_credentials == {
        "email_or_phone": "me@example.com",
        "password": "secret",
    }
    assert "email_or_phone" in result
    assert "password" in result
    assert "me@example.com" not in result
    assert "secret" not in result


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
