"""SESSION_STATUS reveals state only to the session owner (#766)."""

import copy
from types import SimpleNamespace
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


async def _run(messages, *, owner, monkeypatch=None, connect_as=None):
    from connectonion.network.host.ws_router import session

    if connect_as is not None:
        async def fake_connect(data, send, conn, *args):
            conn.update(authenticated=True, agent_address=connect_as,
                        signed_commands=False, session_id="connected-session")

        monkeypatch.setattr(session, "handle_connect", fake_connect)
        messages = [{"type": "CONNECT", "from": connect_as}, *messages]

    queue = list(messages)
    sent = []

    async def recv():
        return queue.pop(0) if queue else None

    async def send(message):
        sent.append(message)

    registry = MagicMock()
    registry.get.side_effect = lambda sid: (
        SimpleNamespace(status="running", owner=owner) if sid == "s1" else None
    )
    await session.run_ws_session(
        send,
        recv,
        route_handlers={"agent_metadata": {"address": "0x" + "12" * 20}},
        storage=MagicMock(),
        registry=registry,
        trust="open",
        enable_ping=False,
    )
    return [message for message in sent if message["type"] == "SESSION_STATUS"]


@pytest.mark.asyncio
async def test_unsigned_temporary_probe_fails_closed():
    replies = await _run(
        [{"type": "SESSION_STATUS", "session": {"session_id": "s1"}}],
        owner="0xowner",
    )

    assert replies == [
        {"type": "SESSION_STATUS", "session_id": "s1", "status": "not_found"}
    ]


@pytest.mark.asyncio
async def test_authenticated_owner_can_read_status(monkeypatch):
    replies = await _run(
        [{"type": "SESSION_STATUS", "session": {"session_id": "s1"}}],
        owner="0xowner",
        monkeypatch=monkeypatch,
        connect_as="0xowner",
    )

    assert replies[-1]["status"] == "running"


@pytest.mark.asyncio
async def test_authenticated_non_owner_cannot_distinguish_the_session(monkeypatch):
    replies = await _run(
        [{"type": "SESSION_STATUS", "session": {"session_id": "s1"}}],
        owner="0xowner",
        monkeypatch=monkeypatch,
        connect_as="0xstranger",
    )

    assert replies[-1]["status"] == "not_found"


def _signed_status(keys, recipient):
    return RemoteAgent(recipient, keys=keys)._build_command_message(
        {"type": "SESSION_STATUS", "session_id": "s1"}
    )


@pytest.mark.asyncio
async def test_signed_temporary_probe_is_bound_to_owner():
    keys = address.generate()
    replies = await _run(
        [_signed_status(keys, "0x" + "12" * 20)], owner=keys["address"]
    )

    assert replies[-1]["status"] == "running"


@pytest.mark.asyncio
async def test_signed_non_owner_gets_the_same_not_found_answer():
    keys = address.generate()
    replies = await _run(
        [_signed_status(keys, "0x" + "12" * 20)], owner="0xowner"
    )

    assert replies[-1]["status"] == "not_found"


@pytest.mark.asyncio
async def test_temporary_probe_replay_fails_closed():
    keys = address.generate()
    frame = _signed_status(keys, "0x" + "12" * 20)
    replies = await _run(
        [frame, copy.deepcopy(frame)], owner=keys["address"]
    )

    assert [reply["status"] for reply in replies] == ["running", "not_found"]


@pytest.mark.asyncio
async def test_temporary_probe_for_another_host_fails_closed():
    keys = address.generate()
    replies = await _run(
        [_signed_status(keys, "0x" + "34" * 20)], owner=keys["address"]
    )

    assert replies[-1]["status"] == "not_found"
