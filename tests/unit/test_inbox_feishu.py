"""Unit tests for the Feishu/Lark inbox provider.

LLM-Note: Tests for connectonion.inbox.feishu

What it tests:
- An im.message.receive_v1 event becomes the seven-field Message, mentions readable, our own @ detected
- Non-text and non-user events are named or dropped
- send() and reply go to the right endpoint with a tenant token, retry a rate limit, and surface Feishu's own error
- check() names the missing credential and the pip command, without a live account

Components under test:
- Module: connectonion/inbox/feishu.py
"""

import json
import sys
from types import SimpleNamespace

import pytest

from connectonion.inbox import feishu as feishu_module
from connectonion.inbox.feishu import Feishu


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "s3cret")


def event(*, text='{"text":"@_user_1 look at the deploy"}', mentions=None, chat_type="group",
          sender_type="user", message_type="text", thread_id=None, root_id=None):
    return SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                message_id="om_9f8e", chat_id="oc_a1b2", chat_type=chat_type,
                message_type=message_type, content=text, create_time=1756808267000,
                thread_id=thread_id, root_id=root_id, mentions=mentions,
            ),
            sender=SimpleNamespace(
                sender_type=sender_type,
                sender_id=SimpleNamespace(union_id="on_7c6d", open_id="ou_1"),
            ),
        )
    )


def mention(open_id="ou_bot", key="@_user_1", name="OpsAgent"):
    return SimpleNamespace(key=key, name=name, id=SimpleNamespace(open_id=open_id))


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def test_a_group_mention_becomes_a_message_with_the_name_put_back(creds):
    bot = Feishu()
    bot._bot_open_id = "ou_bot"

    message = bot.to_message(event(mentions=[mention()]))

    assert message.to_dict() == {
        "id": "om_9f8e", "chat": "oc_a1b2", "thread": None, "sender": "on_7c6d",
        "text": "@OpsAgent look at the deploy", "mentioned": True, "at": "2025-09-02T10:17:47Z",
    }


def test_mentioning_someone_else_in_the_group_is_not_mentioning_us(creds):
    bot = Feishu()
    bot._bot_open_id = "ou_bot"

    message = bot.to_message(event(mentions=[mention(open_id="ou_colleague", name="Alice")]))

    assert message.mentioned is False
    assert message.text == "@Alice look at the deploy"


def test_without_knowing_our_open_id_any_mention_counts(creds):
    message = Feishu().to_message(event(mentions=[mention(open_id="ou_whoever")]))
    assert message.mentioned is True


def test_a_direct_message_is_always_addressed_to_us(creds):
    message = Feishu().to_message(event(text='{"text":"hi"}', chat_type="p2p"))
    assert message.mentioned is True
    assert message.text == "hi"


def test_a_thread_is_carried_and_a_plain_reply_uses_its_root(creds):
    assert Feishu().to_message(event(thread_id="omt_1")).thread == "omt_1"
    assert Feishu().to_message(event(root_id="om_root")).thread == "om_root"


def test_a_bot_sender_is_dropped_and_an_image_is_named(creds):
    bot = Feishu()
    assert bot.to_message(event(sender_type="app")) is None
    assert bot.to_message(event(message_type="image", text='{"image_key":"img_1"}')).text == "[image]"


def test_rich_text_keeps_the_words(creds):
    post = json.dumps({"content": [[{"tag": "text", "text": "line one"}, {"tag": "a", "href": "x"}],
                                   [{"tag": "text", "text": "line two"}]]})
    message = Feishu().to_message(event(message_type="post", text=post))
    assert message.text == "line one line two"


def test_reply_posts_to_the_message_with_a_stable_uuid(creds, monkeypatch):
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        if url.endswith("/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "tenant_access_token": "t-abc", "expire": 7200})
        return FakeResponse({"code": 0, "data": {"message_id": "om_reply"}})

    monkeypatch.setattr(feishu_module.requests, "post", fake_post)
    bot = Feishu()

    first = bot.send("oc_a1b2", "done", reply_to="om_9f8e")
    second = bot.send("oc_a1b2", "done", reply_to="om_9f8e")
    again = bot.send("oc_a1b2", "done, and one more thing", reply_to="om_9f8e")

    assert first == second == again == "om_reply"
    url, body, headers = calls[1]
    assert url == "https://open.feishu.cn/open-apis/im/v1/messages/om_9f8e/reply"
    assert json.loads(body["content"]) == {"text": "done"}
    assert headers == {"Authorization": "Bearer t-abc"}
    assert body["uuid"] == calls[2][1]["uuid"], "same message, same text: a retry, one dedupe key"
    assert body["uuid"] != calls[3][1]["uuid"], "same message, new text (--again): a new key"
    assert sum(1 for c in calls if c[0].endswith("/internal")) == 1, "token fetched once"


def test_send_addresses_the_chat_and_lark_uses_its_own_domain_and_keys(monkeypatch):
    monkeypatch.setenv("LARK_APP_ID", "cli_lark")
    monkeypatch.setenv("LARK_APP_SECRET", "lark-secret")
    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json))
        if url.endswith("/internal"):
            assert json == {"app_id": "cli_lark", "app_secret": "lark-secret"}
            return FakeResponse({"code": 0, "tenant_access_token": "t", "expire": 7200})
        return FakeResponse({"code": 0, "data": {"message_id": "om_new"}})

    monkeypatch.setattr(feishu_module.requests, "post", fake_post)

    assert Feishu(domain="lark").send("oc_z", "hello") == "om_new"
    url, body = calls[1]
    assert url == "https://open.larksuite.com/open-apis/im/v1/messages?receive_id_type=chat_id"
    assert body["receive_id"] == "oc_z"


def test_a_rate_limit_is_retried_and_a_feishu_error_is_its_own_words(creds, monkeypatch):
    attempts = []
    monkeypatch.setattr(feishu_module.time, "sleep", lambda s: attempts.append(f"slept {s}"))

    def fake_post(url, json=None, headers=None, timeout=None):
        if url.endswith("/internal"):
            return FakeResponse({"code": 0, "tenant_access_token": "t", "expire": 7200})
        attempts.append("post")
        if attempts.count("post") < 3:
            return FakeResponse({"code": 99991400, "msg": "rate limited"}, status_code=429)
        return FakeResponse({"code": 230002, "msg": "Bot has NOT been added to the chat"})

    monkeypatch.setattr(feishu_module.requests, "post", fake_post)

    with pytest.raises(RuntimeError, match="230002: Bot has NOT been added"):
        Feishu().send("oc_x", "hi")
    assert attempts == ["post", "slept 1.0", "post", "slept 2.0", "post"]


def test_missing_credentials_name_the_variable_and_the_console(monkeypatch):
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.setenv("FEISHU_APP_SECRET", "x")

    problems = Feishu().missing()

    assert len(problems) == 1
    assert problems[0].startswith("FEISHU_APP_ID is not set")
    assert "open.feishu.cn/app" in problems[0]
    assert Feishu().check() == problems, "check stops at configuration"


def test_check_reports_a_missing_sdk_with_the_pip_command(creds, monkeypatch):
    monkeypatch.setitem(sys.modules, "lark_oapi", None)  # import raises ImportError
    monkeypatch.setattr(feishu_module.requests, "post", lambda *a, **k: FakeResponse(
        {"code": 0, "tenant_access_token": "t", "expire": 7200}))
    monkeypatch.setattr(feishu_module.requests, "get", lambda *a, **k: FakeResponse(
        {"code": 0, "data": {"bot": {"open_id": "ou_bot", "app_name": "OpsAgent"}}}))

    problems = Feishu().check()

    assert problems == ["The Feishu SDK is not installed. Run: pip install lark-oapi"]


def test_check_passes_when_the_bot_answers(creds, monkeypatch):
    monkeypatch.setitem(sys.modules, "lark_oapi", SimpleNamespace())
    monkeypatch.setattr(feishu_module.requests, "post", lambda *a, **k: FakeResponse(
        {"code": 0, "tenant_access_token": "t", "expire": 7200}))
    monkeypatch.setattr(feishu_module.requests, "get", lambda *a, **k: FakeResponse(
        {"code": 0, "data": {"bot": {"open_id": "ou_bot", "app_name": "OpsAgent"}}}))
    bot = Feishu()

    assert bot.check() == []
    assert bot._bot_open_id == "ou_bot", "check learns who we are, so mentions can be matched"


def test_bad_credentials_are_reported_not_raised(creds, monkeypatch):
    monkeypatch.setitem(sys.modules, "lark_oapi", SimpleNamespace())
    monkeypatch.setattr(feishu_module.requests, "post", lambda *a, **k: FakeResponse(
        {"code": 10003, "msg": "invalid app_secret"}))

    (problem,) = Feishu().check()

    assert "invalid app_secret" in problem


def test_an_exhausted_monthly_quota_is_not_retried(creds, monkeypatch):
    """99991403 is the tenant's monthly cap, not a per-minute limit. Retrying
    three times with backoff would only delay the same answer."""
    posts = []
    monkeypatch.setattr(feishu_module.time, "sleep", lambda s: posts.append(f"slept {s}"))

    def fake_post(url, json=None, headers=None, timeout=None):
        if url.endswith("/internal"):
            return FakeResponse({"code": 0, "tenant_access_token": "t", "expire": 7200})
        posts.append("post")
        return FakeResponse({"code": 99991403, "msg": "This month's API call quota has been exceeded"}, status_code=429)

    monkeypatch.setattr(feishu_module.requests, "post", fake_post)

    with pytest.raises(RuntimeError, match="monthly API quota"):
        Feishu().send("oc_x", "hi")
    assert posts == ["post"]


def test_bot_info_reads_the_top_level_shape_feishu_actually_returns(creds, monkeypatch):
    """/bot/v3/info puts `bot` beside code and msg, not under `data`."""
    monkeypatch.setattr(feishu_module.requests, "post", lambda *a, **k: FakeResponse(
        {"code": 0, "tenant_access_token": "t", "expire": 7200}))
    monkeypatch.setattr(feishu_module.requests, "get", lambda *a, **k: FakeResponse(
        {"code": 0, "msg": "ok", "bot": {"open_id": "ou_bot", "app_name": "OpsAgent", "activate_status": 2}}))
    bot = Feishu()

    assert bot.bot_info() == {"open_id": "ou_bot", "name": "OpsAgent"}
    assert bot._bot_open_id == "ou_bot"


def test_a_raw_payload_that_cannot_be_marshalled_is_logged_not_dropped_silently(creds, monkeypatch, tmp_path):
    from types import SimpleNamespace as NS

    from connectonion.inbox.store import Inbox

    class FakeWs:
        def __init__(self, *a, event_handler=None, **k):
            self.handler = event_handler
            self.on_reconnecting = self.on_reconnected = None

        def start(self):
            self.handler(event(text='{"text":"hi"}', chat_type="p2p"))

    class Builder:
        def register_p2_im_message_receive_v1(self, fn):
            self.fn = fn
            return self

        def build(self):
            return self.fn

    class BadJSON:
        @staticmethod
        def marshal(data):
            raise TypeError("not serialisable")

    fake_sdk = NS(ws=NS(Client=FakeWs), LogLevel=NS(WARNING=1), JSON=BadJSON,
                  EventDispatcherHandler=NS(builder=lambda a, b: Builder()))
    monkeypatch.setitem(sys.modules, "lark_oapi", fake_sdk)
    monkeypatch.setattr(feishu_module.requests, "post", lambda *a, **k: FakeResponse(
        {"code": 0, "tenant_access_token": "t", "expire": 7200}))
    monkeypatch.setattr(feishu_module.requests, "get", lambda *a, **k: FakeResponse(
        {"code": 0, "bot": {"open_id": "ou_bot", "app_name": "OpsAgent"}}))
    box = Inbox("feishu", home=tmp_path / "feishu")

    Feishu().run(box, raw=True)

    assert len(box.unread()) == 1, "the message still arrives"
    assert "raw payload of om_9f8e not kept: not serialisable" in box.logfile.read_text()


def _fake_sdk(monkeypatch, start):
    """A lark_oapi whose ws.Client.start() is `start(handler)`."""
    from types import SimpleNamespace as NS

    class FakeWs:
        started = []

        def __init__(self, *a, event_handler=None, **k):
            self.handler = event_handler
            self.on_reconnecting = self.on_reconnected = None

        def start(self):
            FakeWs.started.append(self)
            start(self.handler)

    class Builder:
        def register_p2_im_message_receive_v1(self, fn):
            self.fn = fn
            return self

        def build(self):
            return self.fn

    fake_sdk = NS(ws=NS(Client=FakeWs), LogLevel=NS(WARNING=1), JSON=json,
                  EventDispatcherHandler=NS(builder=lambda a, b: Builder()))
    monkeypatch.setitem(sys.modules, "lark_oapi", fake_sdk)
    return FakeWs


def test_an_event_the_adapter_cannot_read_is_logged_once_and_the_next_one_still_arrives(creds, monkeypatch, tmp_path):
    # The SDK answers Feishu with HTTP 500 when the handler raises, and Feishu
    # then redelivers the same event for hours. A payload we cannot parse is
    # one log line, not a retry storm; the connection stays up for the next.
    from types import SimpleNamespace as NS

    from connectonion.inbox.store import Inbox

    broken = NS(event=NS(message=NS(chat_id="oc_a1b2"), sender=NS(sender_type="user")))  # no message_id

    def start(handler):
        handler(broken)
        handler(event(text='{"text":"hi"}', chat_type="p2p"))

    _fake_sdk(monkeypatch, start)
    monkeypatch.setattr(feishu_module.requests, "post", lambda *a, **k: FakeResponse(
        {"code": 0, "tenant_access_token": "t", "expire": 7200}))
    monkeypatch.setattr(feishu_module.requests, "get", lambda *a, **k: FakeResponse(
        {"code": 0, "bot": {"open_id": "ou_bot", "app_name": "OpsAgent"}}))
    box = Inbox("feishu", home=tmp_path / "feishu")

    Feishu().run(box)

    assert len(box.unread()) == 1, "the good event still arrives after the bad one"
    assert "event not understood" in box.logfile.read_text()


def test_refused_credentials_stop_before_the_connection_is_opened(creds, monkeypatch, tmp_path):
    # Feishu said no to the app_id/app_secret pair. Dialling the WebSocket with
    # the same pair cannot succeed, and the SDK's retry loop would hide the
    # refusal behind "connect failed" lines forever.
    from connectonion.inbox.store import Inbox

    ws = _fake_sdk(monkeypatch, lambda handler: None)
    monkeypatch.setattr(feishu_module.requests, "post", lambda *a, **k: FakeResponse(
        {"code": 10003, "msg": "invalid param"}))
    box = Inbox("feishu", home=tmp_path / "feishu")

    with pytest.raises(RuntimeError, match="refused the credentials"):
        Feishu().run(box)

    assert ws.started == [], "no connection attempted"
    assert "refused the credentials" in box.logfile.read_text()


class HtmlPage:
    """What Feishu's edge returns when it is having a bad minute."""

    status_code = 502

    def json(self):
        raise ValueError("not JSON")


def test_a_gateway_page_on_bot_info_is_not_a_refusal_and_the_connection_is_still_dialled(creds, monkeypatch, tmp_path):
    # Only "Feishu answered and said no to these credentials" stops the
    # listener. A 502 page, a rate limit, or a quota error on the bot-info
    # call is transient: the long connection has its own reconnect.
    from connectonion.inbox.store import Inbox

    ws = _fake_sdk(monkeypatch, lambda handler: None)
    monkeypatch.setattr(feishu_module.requests, "post", lambda *a, **k: FakeResponse(
        {"code": 0, "tenant_access_token": "t", "expire": 7200}))
    monkeypatch.setattr(feishu_module.requests, "get", lambda *a, **k: HtmlPage())
    box = Inbox("feishu", home=tmp_path / "feishu")

    Feishu().run(box)

    assert len(ws.started) == 1, "dialled despite the bad minute"
    assert "bot info failed" in box.logfile.read_text()


def test_an_invalid_token_reply_refreshes_the_token_once_and_retries(creds, monkeypatch):
    # The token is cached by the clock. When the secret is rotated in the
    # console the cached string is dead for up to two hours unless the
    # "invalid access token" reply drops it.
    tokens = []
    sends = []

    def post(url, **kwargs):
        if url.endswith("/tenant_access_token/internal"):
            tokens.append(f"t{len(tokens) + 1}")
            return FakeResponse({"code": 0, "tenant_access_token": tokens[-1], "expire": 7200})
        sends.append(kwargs["headers"]["Authorization"])
        if len(sends) == 1:
            return FakeResponse({"code": 99991663, "msg": "Invalid access token"})
        return FakeResponse({"code": 0, "data": {"message_id": "om_new"}})

    monkeypatch.setattr(feishu_module.requests, "post", post)

    assert Feishu().send("oc_a", "hi") == "om_new"
    assert sends == ["Bearer t1", "Bearer t2"]


def test_ten_or_more_mentions_are_put_back_without_prefix_collisions(creds):
    # Keys are @_user_1, @_user_2, … so @_user_1 is a prefix of @_user_10.
    e = event(text='{"text":"@_user_1 @_user_10 hi"}', mentions=[
        mention(open_id="ou_a", key="@_user_1", name="Alice"),
        mention(open_id="ou_j", key="@_user_10", name="Jon"),
    ])

    assert Feishu().to_message(e).text == "@Alice @Jon hi"


def test_reply_again_with_the_same_text_carries_a_new_uuid(creds, monkeypatch):
    # Feishu holds a reply uuid to one post per hour. A retry of the same
    # text must reuse it; `--again` with the same text must not, or the
    # second reply is silently swallowed while the CLI reports success.
    bodies = []

    def post(url, **kwargs):
        if url.endswith("/tenant_access_token/internal"):
            return FakeResponse({"code": 0, "tenant_access_token": "t", "expire": 7200})
        bodies.append(kwargs["json"])
        return FakeResponse({"code": 0, "data": {"message_id": "om_x"}})

    monkeypatch.setattr(feishu_module.requests, "post", post)
    bot = Feishu()
    bot.send("oc_a", "done", reply_to="om_9f8e")
    bot.send("oc_a", "done", reply_to="om_9f8e")
    bot.send("oc_a", "done", reply_to="om_9f8e", fresh=True)

    assert bodies[0]["uuid"] == bodies[1]["uuid"], "a retry is the same post"
    assert bodies[2]["uuid"] != bodies[0]["uuid"], "--again is a new post"


def test_listen_needs_the_sdk_and_says_how_to_get_it(creds, monkeypatch):
    # send/reply are REST and work without the SDK; only listen needs it, so
    # the requirement is asked for by listen, not by every verb.
    monkeypatch.setitem(sys.modules, "lark_oapi", None)

    assert Feishu().missing() == []
    assert Feishu().listen_requirements() == [feishu_module.SDK_MISSING]
