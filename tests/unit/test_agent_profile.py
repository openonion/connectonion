"""Tests for the authenticated AGENT_PROFILE frame and the public /info subset."""
import pytest
from unittest.mock import AsyncMock, Mock

FULL_SKILLS = [
    {"name": "ship-feature", "description": "ship", "location": "builtin"},
    {"name": "my-project-skill", "description": "proj", "location": "project"},
    {"name": "lark-approval", "description": "private", "location": "user"},
    {"name": "aaron-review", "description": "private", "location": "claude-user"},
]
METADATA = {"name": "oo", "address": "0xabc", "model": "gemini-3.6-flash",
            "tools": ["read_file", "bash"], "skills": FULL_SKILLS, "balance_usd": 12.5}


def test_info_publishes_only_project_tree_skills():
    from connectonion.network.host.http_router import info_handler
    trust = Mock(); trust.trust = "careful"
    result = info_handler(METADATA, trust)

    names = {s["name"] for s in result["skills"]}
    assert names == {"my-project-skill"}, "/info is unauthenticated; only published skills belong in it"
    # The operator's machine must not be advertised by the agent.
    assert "lark-approval" not in names and "aaron-review" not in names
    assert result["protocol"] == {
        "name": "oip",
        "version": "0.1",
        "min_version": "0.1",
        "max_version": "0.1",
        "websocket_path": "/ws",
    }


@pytest.mark.asyncio
async def test_authenticated_connect_gets_the_full_skill_list():
    from connectonion.network.host.ws_router.connect import establish_connection
    sent = []
    send_msg = AsyncMock(side_effect=lambda m: sent.append(m))
    storage = Mock(); storage.get.return_value = None
    registry = Mock(); registry.get.return_value = None

    await establish_connection({}, "0xvisitor", send_msg, {}, storage, registry,
                               {"agent_metadata": METADATA})

    profile = next(m for m in sent if m["type"] == "AGENT_PROFILE")
    assert {s["name"] for s in profile["skills"]} == {s["name"] for s in FULL_SKILLS}
    assert profile["balance_usd"] == 12.5
    types = [m["type"] for m in sent]
    assert types.index("CONNECTED") < types.index("AGENT_PROFILE")
    connected = next(m for m in sent if m["type"] == "CONNECTED")
    assert connected["protocol"]["min_version"] == "0.1"
    assert connected["protocol"]["max_version"] == "0.1"


@pytest.mark.asyncio
async def test_connect_accepts_legacy_client_without_protocol_descriptor():
    from connectonion.network.host.ws_router.connect import establish_connection
    sent = []
    storage = Mock(); storage.get.return_value = None
    registry = Mock(); registry.get.return_value = None

    await establish_connection({}, "0xvisitor", AsyncMock(side_effect=sent.append),
                               {}, storage, registry)

    assert sent[0]["type"] == "CONNECTED"


@pytest.mark.asyncio
async def test_connect_negotiates_session_sync_without_upgrading_legacy_commands():
    from connectonion.network.host.ws_router.connect import establish_connection

    sent = []
    storage = Mock(); storage.get.return_value = None
    registry = Mock(); registry.get.return_value = None
    conn = {}
    await establish_connection(
        {
            "payload": {
                "extensions": {"session-sync": ["0.1"]},
                "to": "0xhost",
            },
        },
        "0xvisitor",
        AsyncMock(side_effect=sent.append),
        conn,
        storage,
        registry,
    )

    assert conn["signed_commands"] is False
    assert conn["session_sync"] is True
    assert sent[0]["protocol"]["extensions"] == {"session-sync": "0.1"}


@pytest.mark.asyncio
async def test_session_index_connection_does_not_create_a_blank_chat():
    from connectonion.network.host.ws_router.connect import establish_connection

    sent = []
    storage = Mock()
    registry = Mock()
    conn = {}
    await establish_connection(
        {
            "payload": {
                "extensions": {"session-sync": ["0.1"]},
                "session_sync_only": 1,
                "to": "0xhost",
            },
        },
        "0xvisitor",
        AsyncMock(side_effect=sent.append),
        conn,
        storage,
        registry,
        {"session_modes": Mock()},
    )

    assert sent == [{
        "type": "CONNECTED",
        "status": "index",
        "protocol": {
            "name": "oip",
            "version": "0.1",
            "min_version": "0.1",
            "max_version": "0.1",
            "websocket_path": "/ws",
            "extensions": {"session-sync": "0.1"},
        },
    }]
    assert conn["session_id"] is None
    assert conn["session_sync_only"] is True
    storage.get.assert_not_called()
    registry.get.assert_not_called()


@pytest.mark.asyncio
async def test_connect_rejects_unsupported_oip_once_without_creating_session():
    from connectonion.network.host.ws_router.connect import establish_connection
    sent = []
    storage = Mock(); registry = Mock()

    await establish_connection(
        {"protocol": {"name": "oip", "version": "9.0"}},
        "0xvisitor", AsyncMock(side_effect=sent.append), {}, storage, registry,
    )

    assert sent == [{
        "type": "ERROR",
        "code": -32010,
        "message": "Unsupported OIP protocol",
        "retryable": False,
        "protocol": {
            "name": "oip",
            "version": "0.1",
            "min_version": "0.1",
            "max_version": "0.1",
            "websocket_path": "/ws",
        },
    }]
    storage.get.assert_not_called()
    registry.get.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["direct", "relay"])
@pytest.mark.parametrize("protocol", [None, {"name": "oip", "version": "0.1"}])
async def test_rolling_oip_readers_have_direct_and_relay_parity(
    transport, protocol, monkeypatch
):
    from connectonion.network.host.ws_router import connect

    sent = []
    telemetry = []
    storage = Mock(); storage.get.return_value = None
    registry = Mock(); registry.get.return_value = None
    monkeypatch.setattr(connect.console, "print", telemetry.append)
    frame = {} if protocol is None else {"protocol": protocol}

    await connect.establish_connection(
        frame,
        "0xvisitor",
        AsyncMock(side_effect=sent.append),
        {"transport": transport},
        storage,
        registry,
    )

    assert sent[0]["type"] == "CONNECTED"
    assert telemetry[0] == (
        f"[dim]OIP_COMPAT transport={transport} "
        f"peer={'legacy' if protocol is None else 'oip/0.1'} outcome=accepted[/dim]"
    )


def test_oip_compatibility_telemetry_never_copies_untrusted_wire_values():
    from connectonion.network.host.protocol import oip_compatibility_record

    record = oip_compatibility_record(
        {"name": "prompt=secret", "version": "/Users/private/customer"},
        "attacker-controlled",
    )

    assert record == {
        "transport": "unknown",
        "peer": "unsupported",
        "outcome": "rejected",
    }


@pytest.mark.asyncio
async def test_no_profile_frame_without_route_handlers():
    """The optional argument keeps callers that only need the session half working."""
    from connectonion.network.host.ws_router.connect import establish_connection
    sent = []
    storage = Mock(); storage.get.return_value = None
    registry = Mock(); registry.get.return_value = None

    await establish_connection({}, "0xvisitor", AsyncMock(side_effect=lambda m: sent.append(m)),
                               {}, storage, registry)

    assert "AGENT_PROFILE" not in [m["type"] for m in sent]
