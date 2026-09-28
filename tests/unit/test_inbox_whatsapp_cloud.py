"""Unit tests for the WhatsApp Cloud API inbox provider (`co whatsapp-cloud`).

LLM-Note: Tests for connectonion.inbox.whatsapp_cloud

What it tests:
- An O API event becomes the shared Message, and an incomplete one is refused
- A claimed event is ACKed only after it is on disk; a failed write is NACKed, never ACKed
- A redelivered event is ACKed without queueing it twice
- The listener stops (not retries) when O API refuses the account or has no inbox route
- send/reply/react go to the pinned Graph version with the operator's token; Markdown is rendered
- A closed 24-hour window is a ProviderPolicyError, exit 3, with every secret redacted
- bind sends the webhook secrets in the authenticated body only, never argv
- `co whatsapp` is untouched: a different class and a different inbox directory

Every HTTP call goes to a fake; nothing here reaches Meta or O API.

Components under test:
- Module: connectonion/inbox/whatsapp_cloud.py
- Module: connectonion/cli/commands/listen_commands.py (bind, send, reply, edit paths)
"""

import json

import pytest

from connectonion.inbox import Inbox, ListenerStopped, ProviderPolicyError, provider
from connectonion.inbox import whatsapp_cloud as cloud_module
from connectonion.inbox.whatsapp_cloud import WhatsAppCloud

EVENT = {
    "delivery_id": "a28b5479-67dc-4f03-a7a2-c3b7af73b8b2",
    "lease_token": "403ddf37-09b1-4cf7-81fa-bbfa1545effe",
    "id": "wamid.HBgLMTE",
    "chat": "61400000000",
    "thread": None,
    "sender": "61400000000",
    "text": "hello from WhatsApp",
    "mentioned": True,
    "at": "2026-09-05T05:00:00Z",
}

SECRETS = {
    "OPENONION_API_KEY": "oo-secret-value",
    "WHATSAPP_CLOUD_ACCESS_TOKEN": "meta-secret-value",
    "WHATSAPP_CLOUD_APP_SECRET": "app-secret-value",
    "WHATSAPP_CLOUD_VERIFY_TOKEN": "verify-secret-value-16",
}


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeHTTP:
    """Every request the provider makes, answered by a route table."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for (want_method, suffix), answer in self.routes.items():
            if method == want_method and url.endswith(suffix):
                return answer(kwargs) if callable(answer) else answer
        raise AssertionError(f"unexpected request {method} {url}")

    def paths(self):
        return [url.split("oo.test", 1)[-1] for _method, url, _kwargs in self.calls]


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.setenv("CONNECTONION_BACKEND_URL", "https://oo.test")
    for name, value in {
        **SECRETS,
        "WHATSAPP_CLOUD_PHONE_NUMBER_ID": "100200300",
        "WHATSAPP_CLOUD_BINDING_ID": "binding-1",
        "WHATSAPP_CLOUD_GRAPH_VERSION": "v23.0",
        "WHATSAPP_CLOUD_WABA_ID": "900800700",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("connectonion.credentials.require_ambient_api_key",
                        lambda: SECRETS["OPENONION_API_KEY"])


def http(monkeypatch, routes) -> FakeHTTP:
    fake = FakeHTTP(routes)
    monkeypatch.setattr(cloud_module.requests, "request", fake)
    return fake


CLAIM = ("POST", "/api/v1/messaging/inbox/whatsapp/claim")
ACK = ("POST", f"/api/v1/messaging/inbox/{EVENT['delivery_id']}/ack")
NACK = ("POST", f"/api/v1/messaging/inbox/{EVENT['delivery_id']}/nack")
GRAPH_SEND = ("POST", "/v23.0/100200300/messages")


# ---- the message ------------------------------------------------------------

def test_an_event_becomes_the_shared_message(env):
    message = WhatsAppCloud.to_message(EVENT)
    assert message.to_dict() == {
        "id": "wamid.HBgLMTE", "chat": "61400000000", "thread": None,
        "sender": "61400000000", "sender_name": "", "text": "hello from WhatsApp",
        "kind": "text", "quoted": None, "mentioned": True, "at": "2026-09-05T05:00:00Z",
    }


def test_an_event_without_its_lease_is_refused_by_name(env):
    broken = dict(EVENT, lease_token="")
    with pytest.raises(ValueError, match="lease_token"):
        WhatsAppCloud.to_message(broken)


# ---- delivery: write, then ACK -------------------------------------------------

def test_a_claimed_event_is_written_before_it_is_acked(env, monkeypatch):
    inbox = Inbox("whatsapp-cloud")
    order = []
    real_deliver = inbox.deliver

    def deliver(message, **kwargs):
        order.append("write")
        return real_deliver(message, **kwargs)

    monkeypatch.setattr(inbox, "deliver", deliver)
    fake = http(monkeypatch, {
        CLAIM: lambda kw: order.append("claim") or Response(200, {"events": [EVENT]}),
        ACK: lambda kw: order.append("ack") or Response(200, {"state": "acked"}),
    })

    assert WhatsAppCloud()._poll_once(inbox) == 1

    assert order == ["claim", "write", "ack"]
    assert fake.calls[-1][2]["json"] == {"lease_token": EVENT["lease_token"]}
    assert [m.id for m in inbox.list_messages()] == ["wamid.HBgLMTE"]


def test_a_failed_local_write_is_nacked_and_never_acked(env, monkeypatch):
    inbox = Inbox("whatsapp-cloud")

    def full_disk(message, **kwargs):
        raise OSError("No space left on device")

    monkeypatch.setattr(inbox, "deliver", full_disk)
    fake = http(monkeypatch, {
        CLAIM: Response(200, {"events": [EVENT]}),
        NACK: Response(200, {"state": "pending"}),
    })

    WhatsAppCloud()._poll_once(inbox)

    assert fake.paths()[-1].endswith("/nack")
    assert fake.calls[-1][2]["json"]["error"] == "OSError"
    assert not any(path.endswith("/ack") for path in fake.paths())


def test_a_redelivered_event_is_acked_but_queued_once(env, monkeypatch):
    inbox = Inbox("whatsapp-cloud")
    http(monkeypatch, {CLAIM: Response(200, {"events": [EVENT]}),
                       ACK: Response(200, {"state": "acked"})})
    adapter = WhatsAppCloud()

    adapter._poll_once(inbox)
    adapter._poll_once(inbox)

    assert len(inbox.unread()) == 1
    assert "duplicate wamid.HBgLMTE" in inbox.logfile.read_text()


# ---- the listener ----------------------------------------------------------------

class Stop(Exception):
    pass


def test_no_inbox_route_stops_the_listener_and_names_the_server_change(env, monkeypatch):
    inbox = Inbox("whatsapp-cloud")
    http(monkeypatch, {CLAIM: Response(404, {"detail": "Not Found"})})

    with pytest.raises(ListenerStopped, match="oo-api#227"):
        WhatsAppCloud().run(inbox, sleep=lambda s: pytest.fail("a 404 must not be retried"))

    assert inbox.connection_state()["state"] == "stopped"


def test_a_transient_failure_backs_off_then_reports_connected(env, monkeypatch):
    inbox = Inbox("whatsapp-cloud")
    answers = iter([Response(502, {"detail": "bad gateway"}), Response(200, {"events": []})])
    http(monkeypatch, {CLAIM: lambda kw: next(answers)})
    states, waits = [], []
    real_record = inbox.record_connection
    monkeypatch.setattr(inbox, "record_connection",
                        lambda state, **d: states.append(state) or real_record(state, **d))

    def sleep(seconds):
        waits.append(seconds)
        if len(waits) == 2:
            raise Stop

    with pytest.raises(Stop):
        WhatsAppCloud().run(inbox, sleep=sleep)

    assert states == ["disconnected", "connected"]
    assert waits == [1.0, 2.0]   # the back-off, then the idle wait
    assert inbox.connection_state()["account"] == "100200300"


# ---- outbound -----------------------------------------------------------------------

def test_a_reply_goes_to_the_pinned_version_quoting_the_original(env, monkeypatch):
    fake = http(monkeypatch, {GRAPH_SEND: Response(200, {"messages": [{"id": "wamid.sent"}]})})

    sent = WhatsAppCloud().send("61400000000", "**ready**", reply_to="wamid.original")

    method, url, kwargs = fake.calls[0]
    assert sent == "wamid.sent"
    assert url == "https://graph.facebook.com/v23.0/100200300/messages"
    assert kwargs["json"]["context"] == {"message_id": "wamid.original"}
    assert kwargs["json"]["text"]["body"] == "*ready*"          # WhatsApp bold, not Markdown
    assert kwargs["headers"] == {"Authorization": "Bearer meta-secret-value"}
    assert "meta-secret-value" not in url


def test_a_reaction_is_the_same_endpoint_with_its_own_type(env, monkeypatch):
    fake = http(monkeypatch, {GRAPH_SEND: Response(200, {"messages": [{"id": "wamid.r"}]})})

    WhatsAppCloud().react("61400000000", "wamid.HBgLMTE", "👍")

    body = fake.calls[0][2]["json"]
    assert body["type"] == "reaction"
    assert body["reaction"] == {"message_id": "wamid.HBgLMTE", "emoji": "👍"}


def test_a_closed_window_is_a_policy_error_with_every_secret_redacted(env, monkeypatch):
    echoed = " ".join(SECRETS.values())
    http(monkeypatch, {GRAPH_SEND: Response(400, {"error": {"code": 131047, "message": echoed}})})

    with pytest.raises(ProviderPolicyError, match="pre-approved template") as error:
        WhatsAppCloud().send("61400000000", "hello")

    for secret in SECRETS.values():
        assert secret not in str(error.value)
    assert "[redacted]" in str(error.value)


def test_an_unset_graph_version_is_named_with_the_command_that_fixes_it(env, monkeypatch):
    monkeypatch.setenv("WHATSAPP_CLOUD_GRAPH_VERSION", "latest")
    problems = WhatsAppCloud().missing()
    assert any("co env set WHATSAPP_CLOUD_GRAPH_VERSION v23.0" in p for p in problems)


def test_a_binding_owned_by_someone_else_fails_check(env, monkeypatch):
    http(monkeypatch, {
        ("GET", "/api/v1/messaging/bindings"): Response(200, {"bindings": [{"id": "other"}]}),
        ("GET", "/v23.0/100200300"): Response(200, {"id": "100200300"}),
    })
    problems = WhatsAppCloud().check()
    assert problems and "co whatsapp-cloud bind" in problems[0]


# ---- the CLI -----------------------------------------------------------------------

def test_bind_sends_secrets_in_the_authenticated_body_and_names_the_next_step(env, monkeypatch, capsys):
    from connectonion.cli.commands import listen_commands

    fake = http(monkeypatch, {("PUT", "/api/v1/messaging/bindings/whatsapp"):
                              Response(201, {"id": "binding-9"})})

    listen_commands.handle_bind("whatsapp-cloud")

    _method, url, kwargs = fake.calls[0]
    assert kwargs["json"]["app_secret"] == "app-secret-value"
    assert kwargs["headers"] == {"Authorization": "Bearer oo-secret-value"}
    assert "app-secret-value" not in url
    out = capsys.readouterr()
    assert out.out.splitlines()[0] == "binding-9"
    assert "Next: co env set WHATSAPP_CLOUD_BINDING_ID binding-9" in out.out
    assert "/api/v1/messaging/webhooks/whatsapp/binding-9" in out.err


def test_bind_without_the_app_secret_exits_3_before_any_request(env, monkeypatch, capsys):
    from connectonion.cli.commands import listen_commands

    monkeypatch.delenv("WHATSAPP_CLOUD_APP_SECRET")
    http(monkeypatch, {})

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_bind("whatsapp-cloud")

    assert exit_.value.code == 3
    assert "WHATSAPP_CLOUD_APP_SECRET" in capsys.readouterr().err


def test_a_closed_window_exits_3_and_is_recorded_as_a_failed_send(env, monkeypatch):
    from connectonion.cli.commands import listen_commands

    http(monkeypatch, {GRAPH_SEND: Response(400, {"error": {"code": 131047, "message": "closed"}})})

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_send("whatsapp-cloud", "61400000000", "hello")

    assert exit_.value.code == 3
    record = json.loads(Inbox("whatsapp-cloud").sent.read_text().splitlines()[-1])
    assert "24-hour" in record["error"]


def test_edit_says_the_platform_cannot_rather_than_nobody_wired_it(env, monkeypatch, capsys):
    from connectonion.cli.commands import listen_commands

    with pytest.raises(SystemExit):
        listen_commands.handle_edit("whatsapp-cloud", "wamid.x", "new text")

    err = capsys.readouterr().err
    assert "Cloud API cannot edit" in err
    assert "nobody has wired it up" not in err


def test_co_whatsapp_is_still_the_linked_device_with_its_own_directory(env):
    from connectonion.inbox.whatsapp import WhatsApp

    assert type(provider("whatsapp")) is WhatsApp
    assert type(provider("whatsapp-cloud")) is WhatsAppCloud
    assert Inbox("whatsapp").root != Inbox("whatsapp-cloud").root
