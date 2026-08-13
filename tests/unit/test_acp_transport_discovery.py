"""Transport discovery selects one browser protocol without granting authority."""

import json
from unittest.mock import Mock

import pytest
from acp import PROTOCOL_VERSION

from connectonion.network.host.acp_gateway import acp_transport_descriptor
from connectonion.network.host.http_router import info_handler


def _trust():
    trust = Mock()
    trust.trust = "careful"
    return trust


def _capture_host_app(tmp_path, monkeypatch, *, acp_enabled):
    from connectonion import Agent, address
    from connectonion.network.host import server

    project = tmp_path / ("native" if acp_enabled else "legacy")
    co_dir = project / ".co"
    co_dir.mkdir(parents=True)
    address.save(address.generate(), co_dir)
    monkeypatch.chdir(project)

    captured = {}
    monkeypatch.setattr(
        server.uvicorn,
        "run",
        lambda app, **kwargs: captured.update(app=app, kwargs=kwargs),
    )
    monkeypatch.setattr(server, "_print_host_banner", lambda **kwargs: None)
    monkeypatch.setattr(server, "create_schedule_lifespan", lambda *args, **kwargs: (None, None))

    agent = Agent(
        "test",
        tools=[],
        model="co/gemini-2.5-flash",
        api_key="test-key",
        quiet=True,
    )
    server.host(
        agent,
        co_dir=co_dir,
        relay_url=None,
        acp_agent_factory=(lambda principal: Mock()) if acp_enabled else None,
    )
    return captured["app"]


async def _get(app, path):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "scheme": "http",
            "client": ("127.0.0.1", 40000),
            "server": ("127.0.0.1", 8000),
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = next(message["body"] for message in sent if message["type"] == "http.response.body")
    return start, json.loads(body)


def test_legacy_info_omits_transport_discovery():
    metadata = {"name": "agent", "tools": [], "address": "0x123"}

    result = info_handler(metadata, _trust())

    assert "transports" not in result


def test_info_returns_only_the_public_acp_transport_descriptor():
    metadata = {
        "name": "agent",
        "tools": [],
        "address": "0x123",
        "transports": {"acp": acp_transport_descriptor()},
    }

    result = info_handler(metadata, _trust())

    assert result["transports"] == {
        "acp": {
            "protocol_version": PROTOCOL_VERSION,
            "type": "websocket",
            "path": "/acp",
            "authorization": {
                "type": "connectonion-ticket",
                "path": "/acp/authorize",
            },
        }
    }
    public = repr(result["transports"]).lower()
    assert "ticket." not in public
    assert "session_id" not in public
    assert "permission" not in public


@pytest.mark.asyncio
async def test_generic_host_omits_acp_and_forbids_cached_fallback(tmp_path, monkeypatch):
    app = _capture_host_app(tmp_path, monkeypatch, acp_enabled=False)

    response, info = await _get(app, "/info")

    assert "transports" not in info
    assert dict(response["headers"])[b"cache-control"] == b"no-store"


@pytest.mark.asyncio
async def test_host_advertises_acp_only_after_mounting_the_gateway(tmp_path, monkeypatch):
    app = _capture_host_app(tmp_path, monkeypatch, acp_enabled=True)

    response, info = await _get(app, "/info")
    assert info["transports"]["acp"] == acp_transport_descriptor()
    assert dict(response["headers"])[b"cache-control"] == b"no-store"

    # The same composite app must actually dispatch the advertised endpoint.
    acp_response, acp_body = await _get(app, "/acp")
    assert acp_response["status"] == 426
    assert acp_body == {
        "error": "ACP Streamable HTTP is not enabled",
        "transport": "websocket",
        "path": "/acp",
    }
