"""Protocol-v2 binds every command to the caller that opened the socket."""

import copy
from unittest.mock import MagicMock

import pytest

from connectonion import address
from connectonion.network.connect import RemoteAgent
from connectonion.network.host import auth


@pytest.fixture(autouse=True)
def clean_replay_cache():
    auth._seen_signatures.clear()
    yield
    auth._seen_signatures.clear()


@pytest.fixture
def keys():
    return address.generate()


def test_connect_negotiates_signed_commands(keys):
    frame = RemoteAgent("0x" + "12" * 20, keys=keys)._build_connect_message()

    assert frame["payload"]["signed_commands"] == 1
    assert auth.verify_signature(frame["payload"], frame["signature"], frame["from"])


def test_input_signature_covers_every_field(keys):
    frame = RemoteAgent("0x" + "12" * 20, keys=keys)._build_input_message(
        "hello", "input-1", images=["image"], files=[{"name": "a.txt"}]
    )

    assert frame["payload"]["type"] == "INPUT"
    assert frame["payload"]["input_id"] == "input-1"
    assert frame["payload"]["images"] == ["image"]
    assert frame["payload"]["files"] == [{"name": "a.txt"}]
    assert frame["payload"]["nonce"]
    assert auth.verify_signature(frame["payload"], frame["signature"], frame["from"])


def test_v1_host_can_read_a_v2_input(keys):
    from connectonion.network.host.ws_router.agent_io import verified_prompt

    frame = RemoteAgent("0x" + "12" * 20, keys=keys)._build_input_message(
        "hello", "input-1"
    )
    handlers = {
        "auth": lambda data, trust: auth.extract_and_authenticate(data, trust)
    }

    assert verified_prompt(frame, handlers) == ("hello", None)


def test_server_executes_the_signed_copy_not_tampered_top_level(keys):
    agent = RemoteAgent("0x" + "12" * 20, keys=keys)
    frame = agent._build_command_message(
        {"type": "EXEC", "exec_id": "e1", "tool": "safe", "args": {"path": "ok"}}
    )
    frame["tool"] = "bash"
    frame["args"] = {"command": "bad"}

    payload, error = auth.authenticated_command_payload(frame, keys["address"])

    assert error is None
    assert payload["tool"] == "safe"
    assert payload["args"] == {"path": "ok"}


def test_command_is_bound_to_connection_owner(keys):
    other = address.generate()
    frame = RemoteAgent("0x" + "12" * 20, keys=keys)._build_command_message(
        {"type": "EXEC", "exec_id": "e1", "tool": "safe", "args": {}}
    )

    payload, error = auth.authenticated_command_payload(frame, other["address"])

    assert payload is None
    assert "does not own" in error


def test_command_signature_cannot_be_replayed(keys):
    frame = RemoteAgent("0x" + "12" * 20, keys=keys)._build_command_message(
        {"type": "EXEC", "exec_id": "e1", "tool": "safe", "args": {}}
    )

    assert auth.authenticated_command_payload(frame, keys["address"])[1] is None
    assert "already used" in auth.authenticated_command_payload(
        copy.deepcopy(frame), keys["address"]
    )[1]


def test_command_is_bound_to_recipient(keys):
    recipient = "0x" + "12" * 20
    frame = RemoteAgent(recipient, keys=keys)._build_command_message(
        {"type": "EXEC", "exec_id": "e1", "tool": "safe", "args": {}},
        is_direct=True,
    )

    payload, error = auth.authenticated_command_payload(
        frame, keys["address"], "0x" + "34" * 20
    )

    assert payload is None
    assert "wrong recipient" in error


def test_top_level_type_cannot_relabel_a_signed_command(keys):
    frame = RemoteAgent("0x" + "12" * 20, keys=keys)._build_command_message(
        {"type": "INPUT", "input_id": "i1", "prompt": "hello"}
    )
    frame["type"] = "EXEC"

    payload, error = auth.authenticated_command_payload(frame, keys["address"])

    assert payload is None
    assert "type mismatch" in error


async def _session_with(messages, monkeypatch, *, signed_commands, ran):
    from connectonion.network.host.ws_router import session

    async def fake_connect(data, send, conn, *args):
        conn.update(
            authenticated=True,
            agent_address=data["from"],
            signed_commands=signed_commands,
            session_id="s1",
            recipient_address=data.get("to"),
        )

    async def fake_exec(data, send, handlers, requester_address):
        ran.append((data, requester_address))

    monkeypatch.setattr(session, "handle_connect", fake_connect)
    monkeypatch.setattr(session, "run_exec", fake_exec)

    queue = list(messages)
    sent = []

    async def recv():
        if queue:
            return queue.pop(0)
        # Let a scheduled EXEC task reach fake_exec before the socket closes.
        import asyncio
        await asyncio.sleep(0.01)
        return None

    async def send(message):
        sent.append(message)

    await session.run_ws_session(
        send,
        recv,
        route_handlers={},
        storage=MagicMock(),
        registry=MagicMock(),
        trust="open",
        enable_ping=False,
    )
    return sent


@pytest.mark.asyncio
async def test_v2_session_rejects_unsigned_exec_before_it_runs(keys, monkeypatch):
    connect = {"type": "CONNECT", "from": keys["address"]}
    unsigned = {"type": "EXEC", "exec_id": "e1", "tool": "bash", "args": {}}
    ran = []

    sent = await _session_with(
        [connect, unsigned], monkeypatch, signed_commands=True, ran=ran
    )

    assert ran == []
    assert "signed command required" in sent[-1]["message"]


@pytest.mark.asyncio
async def test_v2_session_executes_the_verified_payload(keys, monkeypatch):
    agent = RemoteAgent("0x" + "12" * 20, keys=keys)
    connect = {"type": "CONNECT", "from": keys["address"]}
    signed = agent._build_command_message(
        {"type": "EXEC", "exec_id": "e1", "tool": "safe", "args": {"value": 1}}
    )
    signed["tool"] = "tampered"
    ran = []

    await _session_with(
        [connect, signed], monkeypatch, signed_commands=True, ran=ran
    )

    assert ran[0][0]["tool"] == "safe"
    assert ran[0][1] == keys["address"]


@pytest.mark.asyncio
async def test_legacy_session_keeps_accepting_connection_authenticated_exec(keys, monkeypatch):
    connect = {"type": "CONNECT", "from": keys["address"]}
    unsigned = {"type": "EXEC", "exec_id": "e1", "tool": "legacy", "args": {}}
    ran = []

    await _session_with(
        [connect, unsigned], monkeypatch, signed_commands=False, ran=ran
    )

    assert ran[0][0]["tool"] == "legacy"


@pytest.mark.asyncio
async def test_v2_session_binds_admin_action_to_signed_type(keys, monkeypatch):
    from connectonion.network.host.ws_router import session

    agent = RemoteAgent("0x" + "12" * 20, keys=keys)
    connect = {"type": "CONNECT", "from": keys["address"]}
    signed = agent._build_command_message(
        {"type": "ADMIN_PROMOTE", "client_id": "0xclient"}
    )
    signed["type"] = "ADMIN_BLOCK"
    called = []

    async def fake_admin(data, send, handlers):
        called.append(data)

    monkeypatch.setattr(session, "handle_admin_message", fake_admin)
    sent = await _session_with(
        [connect, signed], monkeypatch, signed_commands=True, ran=[]
    )

    assert called == []
    assert "type mismatch" in sent[-1]["message"]


@pytest.mark.asyncio
async def test_v2_session_passes_verified_admin_frame_to_independent_auth(keys, monkeypatch):
    from connectonion.network.host.ws_router import session

    agent = RemoteAgent("0x" + "12" * 20, keys=keys)
    connect = {"type": "CONNECT", "from": keys["address"]}
    signed = agent._build_command_message(
        {"type": "ADMIN_PROMOTE", "client_id": "0xclient"}
    )
    signed["client_id"] = "0xattacker-choice"
    called = []

    async def fake_admin(data, send, handlers):
        assert auth.extract_and_authenticate(data, "open")[2] is True
        called.append(data)

    monkeypatch.setattr(session, "handle_admin_message", fake_admin)
    await _session_with(
        [connect, signed], monkeypatch, signed_commands=True, ran=[]
    )

    assert called[0]["type"] == "ADMIN_PROMOTE"
    assert called[0]["client_id"] == "0xclient"
    assert called[0]["payload"]["client_id"] == "0xclient"
