"""Security and lifecycle tests for the hosted ACP WebSocket boundary."""

from __future__ import annotations

import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from acp import PROTOCOL_VERSION
from acp.schema import ResumeSessionResponse

import connectonion.network.asgi as asgi_module
from connectonion import address
from connectonion.cli.co_ai.acp_server import ConnectOnionACPAgent
from connectonion.network.host.acp_gateway import (
    ACP_AUTHORIZE_PATH,
    ACP_PATH,
    ACP_QUEUE_MESSAGES,
    ACP_SUBPROTOCOL,
    MAX_ACP_MESSAGE_BYTES,
    ACPAdmissionRateLimiter,
    ACPPrincipal,
    ACPTicketRegistry,
    AuthenticatedACPApp,
)
from connectonion.network.host.auth import sign_http_request
from connectonion.network.host.session import ActiveSessionRegistry

ORIGIN = "https://chat.openonion.ai"


class _Trust:
    def __init__(self, *, allow=True, level="contact", payment_verified=False):
        self.allow = allow
        self.level = level
        self.payment_verified = payment_verified
        self.requests = []
        self.payment_requests = []

    def should_allow(self, address, request):
        self.requests.append((address, request))
        return SimpleNamespace(allow=self.allow, reason="test policy")

    def is_admin(self, _address):
        return self.level == "admin"

    def get_level(self, _address):
        return self.level

    def verify_payment(self, caller, amount):
        self.payment_requests.append((caller, amount, threading.get_ident()))
        return self.payment_verified


class _Replay:
    def __init__(self):
        self.seen = set()

    def __call__(self, data):
        signature = data["signature"]
        existed = signature in self.seen
        self.seen.add(signature)
        return existed


class _Agent(ConnectOnionACPAgent):
    def __init__(self):
        super().__init__(
            model="test/model",
            max_iterations=1,
            yolo=False,
            yolo_turns=1,
        )
        self.cancelled = False
        self.closed = False

    def cancel_all(self):
        self.cancelled = True
        super().cancel_all()

    async def close_all(self):
        self.closed = True
        await super().close_all()

    async def resume_session(self, session_id, cwd, **_kwargs):
        self.resumed = (session_id, cwd)
        return ResumeSessionResponse()


def _headers(values):
    return [(str(key).lower().encode("latin-1"), str(value).encode("latin-1")) for key, value in values.items()]


def _app(*, trust=None, tickets=None):
    caller = address.generate()
    recipient = address.generate()
    agents = []

    def create_agent(principal):
        agent = _Agent()
        agents.append((principal, agent))
        return agent

    app = AuthenticatedACPApp(
        create_agent,
        trust_agent=trust or _Trust(),
        recipient_address=recipient["address"],
        replay_check=_Replay(),
        allowed_origins=[ORIGIN],
        tickets=tickets,
    )
    return app, caller, recipient, agents


async def _http(app, *, method, path, headers=None, body=b""):
    sent = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": method,
            "path": path,
            "scheme": "http",
            "client": ("127.0.0.1", 49152),
            "query_string": b"",
            "headers": _headers({"host": "127.0.0.1:8000", **(headers or {})}),
        },
        receive,
        send,
    )
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    response_headers = dict(next(message["headers"] for message in sent if message["type"] == "http.response.start"))
    raw = next(message["body"] for message in sent if message["type"] == "http.response.body")
    return status, response_headers, json.loads(raw) if raw else None


async def _authorize(app, caller, recipient, *, origin=ORIGIN, body=b"{}"):
    signed = sign_http_request(
        caller,
        "POST",
        ACP_AUTHORIZE_PATH,
        recipient_address=recipient["address"],
        body=body,
    )
    return await _http(
        app,
        method="POST",
        path=ACP_AUTHORIZE_PATH,
        headers={**signed, "origin": origin, "content-type": "application/json"},
        body=body,
    )


async def _websocket(
    app,
    *,
    headers=None,
    protocols=(),
    frames=(),
    expected_sends=1,
    path=ACP_PATH,
    scheme="ws",
    client=("127.0.0.1", 49152),
):
    sent = []
    frames = list(frames)
    outgoing = asyncio.Condition()
    outgoing_count = 0
    index = 0

    async def receive():
        nonlocal index
        if index == 0:
            index += 1
            return {"type": "websocket.connect"}
        frame_index = index - 1
        if frame_index < len(frames):
            index += 1
            if isinstance(frames[frame_index], bytes):
                return {"type": "websocket.receive", "bytes": frames[frame_index]}
            return {"type": "websocket.receive", "text": json.dumps(frames[frame_index])}
        async with outgoing:
            await asyncio.wait_for(
                outgoing.wait_for(lambda: outgoing_count >= expected_sends),
                timeout=2,
            )
        return {"type": "websocket.disconnect", "code": 1000}

    async def send(message):
        nonlocal outgoing_count
        sent.append(message)
        if message["type"] in ("websocket.send", "websocket.close"):
            async with outgoing:
                outgoing_count += 1
                outgoing.notify_all()

    await asyncio.wait_for(
        app(
            {
                "type": "websocket",
                "path": path,
                "scheme": scheme,
                "client": client,
                "query_string": b"",
                "headers": _headers({"host": "127.0.0.1:8000", **(headers or {})}),
                "subprotocols": list(protocols),
            },
            receive,
            send,
        ),
        timeout=3,
    )
    return sent


def _initialize():
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION},
    }


def test_ticket_registry_hashes_binds_and_consumes_once():
    clock = [100.0]
    registry = ACPTicketRegistry(ttl_seconds=10, clock=lambda: clock[0])
    principal = ACPPrincipal(
        address="0xcaller",
        level="contact",
        recipient="0xrecipient",
        origin=ORIGIN,
        auth_method="signed_headers",
        authenticated_at=clock[0],
    )

    ticket = registry.issue(principal)

    assert ticket.encode() not in registry._records
    assert registry.consume(ticket, origin="https://evil.example") is None
    assert registry.consume(ticket, origin=ORIGIN) is None

    expiring = registry.issue(principal)
    clock[0] = 110.0
    assert registry.consume(expiring, origin=ORIGIN) is None


def test_transport_queues_are_bounded_for_backpressure():
    from connectonion.network.host.acp_gateway import _ACPTransport

    transport = _ACPTransport()

    assert transport._to_agent.maxsize == ACP_QUEUE_MESSAGES == 8
    assert transport._to_client.maxsize == ACP_QUEUE_MESSAGES


@pytest.mark.asyncio
async def test_outbound_rejects_unserializable_and_oversized_messages():
    from connectonion.network.host.acp_gateway import _ACPTransport

    async def run(message):
        transport = _ACPTransport()
        sent = []

        async def send(frame):
            sent.append(frame)

        await transport.send(message)
        await AuthenticatedACPApp._pump_outbound(transport, send)
        return sent

    unserializable = await run({"value": object()})
    non_standard_number = await run({"value": float("nan")})
    oversized = await run({"value": "x" * MAX_ACP_MESSAGE_BYTES})

    assert unserializable == [
        {
            "type": "websocket.close",
            "code": 1011,
            "reason": "ACP response could not be serialized",
        }
    ]
    assert non_standard_number == [
        {
            "type": "websocket.close",
            "code": 1011,
            "reason": "ACP response could not be serialized",
        }
    ]
    assert oversized == [
        {
            "type": "websocket.close",
            "code": 1009,
            "reason": "ACP response is too large",
        }
    ]


def test_ticket_registry_bounds_one_principals_pending_tickets():
    registry = ACPTicketRegistry(max_pending=3, max_pending_per_principal=1)
    principal = ACPPrincipal(
        address="0xcaller",
        level="contact",
        recipient="0xrecipient",
        origin=ORIGIN,
        auth_method="signed_headers",
        authenticated_at=100.0,
    )

    registry.issue(principal)

    with pytest.raises(RuntimeError, match="too many pending"):
        registry.issue(principal)


def test_admission_rate_limiter_is_principal_scoped_bounded_and_expires():
    clock = [100.0]
    limiter = ACPAdmissionRateLimiter(
        limit=1,
        window_seconds=10,
        max_principals=1,
        clock=lambda: clock[0],
    )
    principal = ACPPrincipal(
        address="0xcaller",
        level="contact",
        recipient="0xrecipient",
        origin=ORIGIN,
        auth_method="signed_headers",
        authenticated_at=100.0,
    )
    other = ACPPrincipal(
        address="0xother",
        level="contact",
        recipient="0xrecipient",
        origin=ORIGIN,
        auth_method="signed_headers",
        authenticated_at=100.0,
    )

    assert limiter.allow(principal) is True
    assert limiter.allow(principal) is False
    assert limiter.allow(other) is False
    clock[0] = 110.0
    assert limiter.allow(other) is True


@pytest.mark.asyncio
async def test_rejected_connection_does_not_release_an_existing_principal_slot():
    caller = address.generate()
    recipient = address.generate()
    app = AuthenticatedACPApp(
        lambda _principal: _Agent(),
        trust_agent=_Trust(),
        recipient_address=recipient["address"],
        replay_check=_Replay(),
        allowed_origins=[ORIGIN],
        max_connections_per_principal=1,
    )
    key = (recipient["address"], caller["address"], None, "signed_headers")
    app._active_principals[key] = 1
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )

    sent = await _websocket(app, headers=signed)

    assert sent == [
        {
            "type": "websocket.close",
            "code": 4429,
            "reason": "ACP principal connection limit reached",
        }
    ]
    assert app._active_principals[key] == 1


@pytest.mark.asyncio
async def test_browser_preflight_accepts_standard_headers_and_private_network():
    app, _, _, _ = _app()

    status, headers, response = await _http(
        app,
        method="OPTIONS",
        path=ACP_AUTHORIZE_PATH,
        headers={
            "origin": ORIGIN,
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type, x-co-from",
            "access-control-request-private-network": "true",
        },
    )

    assert status == 204
    assert response is None
    assert headers[b"access-control-allow-origin"] == ORIGIN.encode()
    assert headers[b"access-control-allow-private-network"] == b"true"


@pytest.mark.asyncio
async def test_browser_preflight_rejects_unadvertised_headers():
    app, _, _, _ = _app()

    status, _, response = await _http(
        app,
        method="OPTIONS",
        path=ACP_AUTHORIZE_PATH,
        headers={
            "origin": ORIGIN,
            "access-control-request-method": "POST",
            "access-control-request-headers": "x-co-from, x-secret-bypass",
        },
    )

    assert status == 400
    assert response == {"error": "CORS preflight requested unsupported headers"}


@pytest.mark.asyncio
async def test_authorize_requires_json_content_type_before_admission():
    app, caller, recipient, agents = _app()
    body = b"{}"
    signed = sign_http_request(
        caller,
        "POST",
        ACP_AUTHORIZE_PATH,
        recipient_address=recipient["address"],
        body=body,
    )

    status, _, response = await _http(
        app,
        method="POST",
        path=ACP_AUTHORIZE_PATH,
        headers={**signed, "origin": ORIGIN, "content-type": "text/plain"},
        body=body,
    )

    assert status == 415
    assert response == {"error": "Content-Type must be application/json"}
    assert agents == []


@pytest.mark.asyncio
async def test_authorize_rejects_json_prefixed_non_json_media_type():
    app, caller, recipient, agents = _app()
    body = b"{}"
    signed = sign_http_request(
        caller,
        "POST",
        ACP_AUTHORIZE_PATH,
        recipient_address=recipient["address"],
        body=body,
    )

    status, _, response = await _http(
        app,
        method="POST",
        path=ACP_AUTHORIZE_PATH,
        headers={
            **signed,
            "origin": ORIGIN,
            "content-type": "application/json-evil",
        },
        body=body,
    )

    assert status == 415
    assert response == {"error": "Content-Type must be application/json"}
    assert agents == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "error"),
    [
        (b'{"payment":NaN}', "Invalid JSON"),
        (b'{"payment":true}', "Invalid payment"),
        (b'{"payment":-1}', "Invalid payment"),
        (b'{"payment":' + (b"9" * 4000) + b"}", "Invalid payment"),
        (b'{"invite_code":{}}', "Invalid invite_code"),
    ],
)
async def test_authorize_validates_onboarding_fields_before_trust(body, error):
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "POST",
        ACP_AUTHORIZE_PATH,
        recipient_address=recipient["address"],
        body=body,
    )

    status, _, response = await _http(
        app,
        method="POST",
        path=ACP_AUTHORIZE_PATH,
        headers={
            **signed,
            "origin": ORIGIN,
            "content-type": "application/json",
        },
        body=body,
    )

    assert status == 400
    assert response == {"error": error}
    assert agents == []


@pytest.mark.asyncio
async def test_duplicate_signed_header_is_rejected_before_admission():
    app, caller, recipient, agents = _app()
    body = b"{}"
    signed = sign_http_request(
        caller,
        "POST",
        ACP_AUTHORIZE_PATH,
        recipient_address=recipient["address"],
        body=body,
    )
    raw_headers = _headers(
        {
            **signed,
            "origin": ORIGIN,
            "content-type": "application/json",
        }
    )
    raw_headers.append((b"x-co-from", b"0xduplicate"))
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": "POST",
            "path": ACP_AUTHORIZE_PATH,
            "scheme": "http",
            "client": ("127.0.0.1", 49152),
            "query_string": b"",
            "headers": raw_headers,
        },
        receive,
        send,
    )

    start = next(item for item in sent if item["type"] == "http.response.start")
    response = json.loads(next(item["body"] for item in sent if item["type"] == "http.response.body"))
    assert start["status"] == 400
    assert response == {"error": "Ambiguous security headers"}
    assert agents == []


@pytest.mark.asyncio
async def test_verified_principal_admission_is_rate_limited():
    limiter = ACPAdmissionRateLimiter(limit=1)
    caller = address.generate()
    recipient = address.generate()
    agents = []

    app = AuthenticatedACPApp(
        lambda principal: agents.append(principal) or _Agent(),
        trust_agent=_Trust(),
        recipient_address=recipient["address"],
        replay_check=_Replay(),
        allowed_origins=[ORIGIN],
        rate_limiter=limiter,
    )

    first = await _authorize(app, caller, recipient)
    second = await _authorize(app, caller, recipient)

    assert first[0] == 201
    assert second[0] == 429
    assert second[2] == {"error": "too many ACP admission attempts"}
    assert agents == []


@pytest.mark.asyncio
async def test_native_payment_onboarding_verifies_transfer_off_the_event_loop():
    trust = _Trust(allow=False, payment_verified=True)
    app, caller, recipient, agents = _app(trust=trust)
    event_loop_thread = threading.get_ident()

    status, headers, response = await _authorize(
        app,
        caller,
        recipient,
        body=b'{"payment":10}',
    )

    assert status == 201
    assert headers[b"cache-control"] == b"no-store"
    assert response["protocols"][0] == "acp"
    assert len(trust.payment_requests) == 1
    payment_caller, payment_amount, worker_thread = trust.payment_requests[0]
    assert (payment_caller, payment_amount) == (caller["address"], 10)
    assert worker_thread != event_loop_thread
    assert agents == []


@pytest.mark.asyncio
async def test_claimed_native_payment_without_verified_transfer_stays_forbidden():
    tickets = ACPTicketRegistry()
    trust = _Trust(allow=False, payment_verified=False)
    app, caller, recipient, agents = _app(trust=trust, tickets=tickets)

    status, headers, response = await _authorize(
        app,
        caller,
        recipient,
        body=b'{"payment":999}',
    )

    assert status == 403
    assert headers[b"cache-control"] == b"no-store"
    assert response == {"error": "forbidden: test policy"}
    assert trust.payment_requests[0][:2] == (caller["address"], 999)
    assert tickets._records == {}
    assert agents == []


@pytest.mark.asyncio
async def test_native_payment_provider_failure_is_generic_and_issues_no_ticket():
    tickets = ACPTicketRegistry()
    trust = _Trust(allow=False)
    trust.verify_payment = Mock(side_effect=RuntimeError("private provider detail"))
    app, caller, recipient, agents = _app(trust=trust, tickets=tickets)

    status, _, response = await _authorize(
        app,
        caller,
        recipient,
        body=b'{"payment":10}',
    )

    assert status == 503
    assert response == {"error": "misconfigured: payment verification unavailable"}
    assert "private provider detail" not in response["error"]
    assert tickets._records == {}
    assert agents == []


@pytest.mark.asyncio
async def test_rejected_signed_attempts_are_limited_before_payment_verification():
    limiter = ACPAdmissionRateLimiter(limit=1)
    trust = _Trust(allow=False, payment_verified=False)
    caller = address.generate()
    recipient = address.generate()
    app = AuthenticatedACPApp(
        lambda _principal: _Agent(),
        trust_agent=trust,
        recipient_address=recipient["address"],
        replay_check=_Replay(),
        allowed_origins=[ORIGIN],
        rate_limiter=limiter,
    )

    first = await _authorize(app, caller, recipient, body=b'{"payment":10}')
    second = await _authorize(app, caller, recipient, body=b'{"payment":10}')

    assert first[0] == 403
    assert second[0] == 429
    assert second[2] == {"error": "too many ACP admission attempts"}
    assert len(trust.payment_requests) == 1


@pytest.mark.asyncio
async def test_browser_ticket_requires_signed_trusted_exact_origin_then_runs_acp():
    trust = _Trust(level="contact")
    app, caller, recipient, agents = _app(trust=trust)

    status, headers, response = await _authorize(app, caller, recipient)

    assert status == 201
    assert headers[b"access-control-allow-origin"] == ORIGIN.encode()
    assert headers[b"cache-control"] == b"no-store"
    assert agents == []
    assert trust.requests == [
        (
            caller["address"],
            {
                "prompt": "Open an ACP WebSocket connection",
                "invite_code": None,
                "payment": 0,
            },
        )
    ]

    sent = await _websocket(
        app,
        protocols=response["protocols"],
        headers={"origin": ORIGIN},
        frames=[_initialize()],
    )

    assert sent[0]["type"] == "websocket.accept"
    assert sent[0]["subprotocol"] == "acp"
    connection_id = dict(sent[0]["headers"])[b"acp-connection-id"].decode()
    assert len(connection_id) == 36
    initialized = next(json.loads(item["text"]) for item in sent if item["type"] == "websocket.send")
    assert initialized["id"] == 1
    assert initialized["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert len(agents) == 1
    principal, agent = agents[0]
    assert principal.address == caller["address"]
    assert principal.recipient == recipient["address"]
    assert principal.origin == ORIGIN
    assert principal.auth_method == "browser_ticket"
    assert agent.connection_principal == principal
    assert agent.cancelled is True
    assert agent.closed is True

    replayed = await _websocket(
        app,
        protocols=response["protocols"],
        headers={"origin": ORIGIN},
    )
    assert replayed == [
        {
            "type": "websocket.close",
            "code": 4401,
            "reason": "ACP admission refused",
        }
    ]
    assert len(agents) == 1


@pytest.mark.asyncio
async def test_untrusted_or_wrong_origin_never_creates_an_agent():
    app, caller, recipient, agents = _app(trust=_Trust(allow=False))

    status, _, response = await _authorize(app, caller, recipient)
    assert status == 403
    assert response["error"] == "forbidden: test policy"

    status, headers, response = await _authorize(
        app,
        caller,
        recipient,
        origin="https://evil.example",
    )
    assert status == 403
    assert b"access-control-allow-origin" not in headers
    assert response == {"error": "Origin not allowed"}
    assert agents == []


@pytest.mark.asyncio
async def test_insecure_non_loopback_authorize_fails_before_admission():
    app, caller, recipient, agents = _app()
    body = b"{}"
    signed = sign_http_request(
        caller,
        "POST",
        ACP_AUTHORIZE_PATH,
        recipient_address=recipient["address"],
        body=body,
    )
    sent = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": "POST",
            "path": ACP_AUTHORIZE_PATH,
            "scheme": "http",
            "client": ("203.0.113.10", 49152),
            "query_string": b"",
            "headers": _headers(
                {
                    **signed,
                    "origin": ORIGIN,
                    "content-type": "application/json",
                }
            ),
        },
        receive,
        send,
    )

    start = next(item for item in sent if item["type"] == "http.response.start")
    response = json.loads(next(item["body"] for item in sent if item["type"] == "http.response.body"))
    assert start["status"] == 403
    assert response == {"error": "Secure transport is required for non-loopback ACP"}
    assert agents == []


@pytest.mark.asyncio
async def test_programmatic_client_can_sign_upgrade_without_browser_ticket():
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )

    sent = await _websocket(app, headers=signed, frames=[_initialize()])

    assert sent[0]["type"] == "websocket.accept"
    assert b"acp-connection-id" in dict(sent[0]["headers"])
    assert any(item["type"] == "websocket.send" for item in sent)
    assert agents[0][0].auth_method == "signed_headers"


@pytest.mark.asyncio
async def test_binary_frame_is_ignored_while_waiting_for_initialize():
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )

    sent = await _websocket(
        app,
        headers=signed,
        frames=[b"ignored transport data", _initialize()],
    )

    assert sent[0]["type"] == "websocket.accept"
    assert any(item["type"] == "websocket.send" for item in sent)
    assert len(agents) == 1


@pytest.mark.asyncio
async def test_multiple_ticket_protocols_are_rejected_without_agent_creation():
    app, caller, recipient, agents = _app()
    first = (await _authorize(app, caller, recipient))[2]
    second = (await _authorize(app, caller, recipient))[2]

    sent = await _websocket(
        app,
        protocols=[
            ACP_SUBPROTOCOL,
            first["protocols"][1],
            second["protocols"][1],
        ],
        headers={"origin": ORIGIN},
    )

    assert sent == [
        {
            "type": "websocket.close",
            "code": 4401,
            "reason": "ACP admission refused",
        }
    ]
    assert agents == []


@pytest.mark.asyncio
async def test_browser_ticket_requires_acp_subprotocol():
    app, caller, recipient, agents = _app()
    authorized = (await _authorize(app, caller, recipient))[2]

    sent = await _websocket(
        app,
        protocols=[authorized["protocols"][1]],
        headers={"origin": ORIGIN},
    )

    assert sent == [
        {
            "type": "websocket.close",
            "code": 4401,
            "reason": "ACP admission refused",
        }
    ]
    assert agents == []


@pytest.mark.asyncio
async def test_remote_transport_keeps_resume_route_enabled():
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )
    resume = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "session/resume",
        "params": {"sessionId": "saved-session", "cwd": "/tmp"},
    }

    sent = await _websocket(
        app,
        headers=signed,
        frames=[_initialize(), resume],
        expected_sends=2,
    )

    responses = [
        json.loads(item["text"])
        for item in sent
        if item["type"] == "websocket.send"
    ]
    assert [response["id"] for response in responses] == [1, 2]
    assert responses[1]["result"] == {}
    assert agents[0][1].resumed == ("saved-session", "/tmp")


@pytest.mark.asyncio
async def test_first_frame_must_initialize_before_agent_creation():
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )

    sent = await _websocket(
        app,
        headers=signed,
        frames=[{"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {}}],
    )

    assert sent[-1]["type"] == "websocket.close"
    assert sent[-1]["code"] == 4400
    assert agents == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first",
    [
        {"jsonrpc": "1.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": True, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": []},
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "not-an-integer"},
        },
        {**_initialize(), "result": {"foreign": True}},
        {
            **_initialize(),
            "error": {"code": -32000, "message": "foreign"},
        },
    ],
)
async def test_malformed_initialize_never_creates_an_agent(first):
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )

    sent = await _websocket(app, headers=signed, frames=[first])

    assert sent[-1]["type"] == "websocket.close"
    assert sent[-1]["code"] == 4400
    assert agents == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mixed",
    [
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/resume",
            "params": {"sessionId": "saved-session", "cwd": "/tmp"},
            "result": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/resume",
            "params": {"sessionId": "saved-session", "cwd": "/tmp"},
            "error": {"code": -32000, "message": "foreign"},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/resume",
            "result": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {},
            "params": {},
        },
    ],
)
async def test_mixed_post_initialize_envelope_has_no_side_effect(mixed):
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )

    sent = await _websocket(
        app,
        headers=signed,
        frames=[_initialize(), mixed],
        expected_sends=2,
    )

    responses = [json.loads(item["text"]) for item in sent if item["type"] == "websocket.send"]
    initialized = next(item for item in responses if item["id"] == 1)
    rejected = next(item for item in responses if item["id"] == mixed["id"])
    assert initialized["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert rejected["error"]["code"] == -32600
    assert not hasattr(agents[0][1], "resumed")


@pytest.mark.asyncio
async def test_meta_cannot_shadow_websocket_request_parameters():
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )
    shadowed = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "session/resume",
        "params": {
            "sessionId": "visible-session",
            "cwd": "/",
            "_meta": {
                "session_id": "hidden-session",
                "cwd": "/hidden",
            },
        },
    }

    sent = await _websocket(
        app,
        headers=signed,
        frames=[_initialize(), shadowed],
        expected_sends=2,
    )

    responses = [
        json.loads(item["text"])
        for item in sent
        if item["type"] == "websocket.send"
    ]
    rejected = next(item for item in responses if item["id"] == shadowed["id"])
    assert rejected["error"] == {
        "code": -32602,
        "message": "Invalid params",
        "data": {"details": "ACP _meta cannot override request parameters"},
    }
    assert not hasattr(agents[0][1], "resumed")


@pytest.mark.asyncio
async def test_shadowed_initialize_never_creates_an_agent():
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )
    first = _initialize()
    first["params"]["_meta"] = {"protocol_version": 0}

    sent = await _websocket(app, headers=signed, frames=[first])

    assert sent[-1]["type"] == "websocket.close"
    assert sent[-1]["code"] == 4400
    assert agents == []


@pytest.mark.asyncio
async def test_non_standard_json_constant_is_rejected_before_agent_creation():
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )
    first = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": float("nan")},
    }

    sent = await _websocket(app, headers=signed, frames=[first])

    assert sent[-1]["type"] == "websocket.close"
    assert sent[-1]["code"] == 1007
    assert agents == []


@pytest.mark.asyncio
async def test_wrong_websocket_path_never_runs_admission_or_agent_factory():
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )

    sent = await _websocket(app, path=ACP_AUTHORIZE_PATH, headers=signed)

    assert sent == [
        {
            "type": "websocket.close",
            "code": 4404,
            "reason": "ACP WebSocket path not found",
        }
    ]
    assert agents == []


@pytest.mark.asyncio
async def test_insecure_non_loopback_websocket_never_runs_admission():
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )

    sent = await _websocket(
        app,
        headers=signed,
        client=("203.0.113.10", 49152),
    )

    assert sent == [
        {
            "type": "websocket.close",
            "code": 4403,
            "reason": "Secure transport is required",
        }
    ]
    assert agents == []


@pytest.mark.asyncio
async def test_plaintext_loopback_proxy_with_public_authority_fails_closed():
    app, caller, recipient, agents = _app()
    signed = sign_http_request(
        caller,
        "GET",
        ACP_PATH,
        recipient_address=recipient["address"],
    )

    sent = await _websocket(
        app,
        headers={**signed, "host": "agent.example.com"},
        client=("127.0.0.1", 49152),
        scheme="ws",
    )

    assert sent == [
        {
            "type": "websocket.close",
            "code": 4403,
            "reason": "Secure transport is required",
        }
    ]
    assert agents == []


@pytest.mark.asyncio
async def test_unsigned_websocket_is_closed_before_agent_creation():
    app, _, _, agents = _app()

    sent = await _websocket(app)

    assert sent == [
        {
            "type": "websocket.close",
            "code": 4401,
            "reason": "ACP admission refused",
        }
    ]
    assert agents == []


@pytest.mark.asyncio
async def test_top_level_asgi_routes_only_exact_acp_endpoints(monkeypatch):
    calls = []

    class _ACPApp:
        async def __call__(self, scope, _receive, _send):
            calls.append(("acp", scope["type"], scope["path"]))

        async def close(self):
            calls.append(("acp-close",))

    async def legacy_websocket(scope, _receive, _send, **_kwargs):
        calls.append(("legacy", scope["type"], scope["path"]))

    monkeypatch.setattr(asgi_module, "handle_websocket", legacy_websocket)
    app = asgi_module.create_app(
        route_handlers={},
        storage=Mock(),
        registry=ActiveSessionRegistry(),
        acp=_ACPApp(),
    )

    async def receive():
        return {"type": "websocket.connect"}

    async def send(_message):
        pass

    await app({"type": "websocket", "path": ACP_PATH}, receive, send)
    await app({"type": "websocket", "path": ACP_AUTHORIZE_PATH}, receive, send)
    await app({"type": "websocket", "path": "/ws"}, receive, send)
    await app(
        {
            "type": "http",
            "method": "POST",
            "path": ACP_AUTHORIZE_PATH,
        },
        receive,
        send,
    )

    assert calls == [
        ("acp", "websocket", ACP_PATH),
        ("legacy", "websocket", ACP_AUTHORIZE_PATH),
        ("legacy", "websocket", "/ws"),
        ("acp", "http", ACP_AUTHORIZE_PATH),
    ]


@pytest.mark.asyncio
async def test_lifespan_shutdown_runs_host_cleanup_if_acp_cleanup_fails(caplog):
    events = []

    class _FailingACPApp:
        async def close(self):
            events.append("acp")
            raise RuntimeError("cleanup failure")

    async def host_shutdown():
        events.append("host")

    app = asgi_module.create_app(
        route_handlers={},
        storage=Mock(),
        registry=ActiveSessionRegistry(),
        acp=_FailingACPApp(),
        on_shutdown=host_shutdown,
    )
    received = False
    sent = []

    async def receive():
        nonlocal received
        if received:
            raise AssertionError("lifespan receive called twice")
        received = True
        return {"type": "lifespan.shutdown"}

    async def send(message):
        sent.append(message)

    await app({"type": "lifespan"}, receive, send)

    assert events == ["acp", "host"]
    assert sent == [{"type": "lifespan.shutdown.complete"}]
    assert "ASGI shutdown cleanup failed" in caplog.text
