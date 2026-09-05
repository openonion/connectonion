"""WhatsApp O API ingress and Meta delivery boundaries."""

import pytest

from connectonion.listen import ProviderPolicyError
from connectonion.listen.whatsapp import WhatsApp


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


@pytest.fixture
def adapter(monkeypatch):
    values = {
        "OPENONION_API_KEY": "oo-secret",
        "WHATSAPP_ACCESS_TOKEN": "meta-secret",
        "WHATSAPP_PHONE_NUMBER_ID": "100200300",
        "WHATSAPP_BINDING_ID": "binding-id",
        "WHATSAPP_GRAPH_VERSION": "v23.0",
        "WHATSAPP_WABA_ID": "waba-id",
        "WHATSAPP_APP_SECRET": "app-secret",
        "WHATSAPP_VERIFY_TOKEN": "verify-secret",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return WhatsApp()


def test_event_normalizes_to_the_shared_seven_fields(adapter):
    assert adapter.to_message(EVENT).to_dict() == {
        "id": "wamid.HBgLMTE",
        "chat": "61400000000",
        "thread": None,
        "sender": "61400000000",
        "text": "hello from WhatsApp",
        "mentioned": True,
        "at": "2026-09-05T05:00:00Z",
    }


def test_claim_is_written_locally_before_ack(adapter, monkeypatch):
    actions = []

    def api(method, path, **kwargs):
        actions.append(path)
        return {"events": [EVENT]} if path.endswith("/claim") else {"state": "acked"}

    monkeypatch.setattr(adapter, "_o_api", api)
    mailbox = FakeMailbox(actions)

    assert adapter._poll_once(mailbox) == 1
    assert actions == [
        "/api/v1/messaging/inbox/whatsapp/claim",
        "deliver",
        f"/api/v1/messaging/inbox/{EVENT['delivery_id']}/ack",
    ]


def test_failed_local_write_nacks_instead_of_acking(adapter, monkeypatch):
    paths = []

    def api(method, path, **kwargs):
        paths.append((path, kwargs.get("json")))
        return {"events": [EVENT]} if path.endswith("/claim") else {"state": "pending"}

    monkeypatch.setattr(adapter, "_o_api", api)
    adapter._poll_once(FakeMailbox([], failure=OSError("disk full")))

    assert paths[-1][0].endswith("/nack")
    assert paths[-1][1]["error"] == "OSError"
    assert not any(path.endswith("/ack") for path, _ in paths)


def test_send_uses_pinned_graph_version_and_context(adapter, monkeypatch):
    posted = []
    monkeypatch.setattr(
        "connectonion.listen.whatsapp.requests.post",
        lambda url, **kwargs: posted.append((url, kwargs))
        or Response(200, {"messages": [{"id": "wamid.sent"}]}),
    )

    assert adapter.send("61400000000", "hello", reply_to="wamid.original") == "wamid.sent"
    assert posted[0][0] == "https://graph.facebook.com/v23.0/100200300/messages"
    assert posted[0][1]["json"]["context"] == {"message_id": "wamid.original"}
    assert "meta-secret" not in posted[0][0]


def test_closed_service_window_is_an_explicit_redacted_policy_error(adapter):
    response = Response(
        400,
        {"error": {"code": 131047, "message": "meta-secret outside window"}},
    )

    with pytest.raises(ProviderPolicyError, match="pre-approved template") as error:
        adapter._meta_result(response)
    assert "meta-secret" not in str(error.value)
    assert "[redacted]" in str(error.value)


def test_bind_sends_secrets_only_in_authenticated_request_body(adapter, monkeypatch):
    requests = []
    monkeypatch.setattr(
        "connectonion.listen.whatsapp.require_ambient_api_key",
        lambda: "oo-secret",
    )
    monkeypatch.setattr(
        "connectonion.listen.whatsapp.requests.put",
        lambda url, **kwargs: requests.append((url, kwargs))
        or Response(200, {"id": "binding-id"}),
    )

    assert adapter.bind() == {"id": "binding-id"}
    assert requests[0][1]["json"]["app_secret"] == "app-secret"
    assert requests[0][1]["headers"] == {"Authorization": "Bearer oo-secret"}


class FakeMailbox:
    def __init__(self, actions, failure=None):
        self.actions = actions
        self.failure = failure
        self.logs = []

    def deliver(self, message):
        self.actions.append("deliver")
        if self.failure:
            raise self.failure
        return True

    def log(self, line):
        self.logs.append(line)


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload

    def json(self):
        return self.payload
