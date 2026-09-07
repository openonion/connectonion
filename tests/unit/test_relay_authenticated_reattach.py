"""A relay reload may reattach to the still-live logical OIP session."""

import copy
import json
from unittest.mock import MagicMock

import pytest

from connectonion import address
from connectonion.network.connect import RemoteAgent
from connectonion.network.host import auth
from connectonion.network.host.ws_router.connect import handle_authenticated_reconnect
from connectonion.network.trust.trust_agent import TrustAgent


RECIPIENT = "0x" + "12" * 20
SESSION_ID = "relay-session"


@pytest.fixture(autouse=True)
def clean_replay_cache():
    auth._seen_signatures.clear()
    yield
    auth._seen_signatures.clear()


@pytest.fixture
def keys():
    return address.generate()


def connect_frame(keys, recipient=RECIPIENT, session_id=SESSION_ID):
    frame = RemoteAgent(recipient, keys=keys)._build_connect_message()
    frame["session_id"] = session_id
    return frame


def freshly_resign(frame, keys):
    fresh = copy.deepcopy(frame)
    fresh["payload"]["timestamp"] += 1
    fresh["timestamp"] = fresh["payload"]["timestamp"]
    canonical = json.dumps(
        fresh["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    fresh["signature"] = address.sign(keys, canonical.encode()).hex()
    return fresh


def authenticated_conn(keys):
    return {
        "authenticated": True,
        "agent_address": keys["address"],
        "session_id": SESSION_ID,
        "session": None,
        "signed_commands": True,
        "recipient_address": RECIPIENT,
    }


async def reattach(frame, conn, trust="open", blacklist=None, route_handlers=None):
    sent = []
    storage = MagicMock()
    storage.get.return_value = None
    registry = MagicMock()
    registry.get.return_value = None

    async def send(message):
        sent.append(message)

    await handle_authenticated_reconnect(
        frame,
        send,
        conn,
        route_handlers or {"agent_metadata": {"address": RECIPIENT}},
        storage,
        registry,
        trust,
        blacklist,
        None,
    )
    return sent


@pytest.mark.asyncio
async def test_reattach_does_not_repeat_mutable_trust_policy(keys, monkeypatch):
    """A live connection was already authorized; reattach only re-authenticates it."""
    trust = TrustAgent("open")
    should_allow = MagicMock(side_effect=FileNotFoundError(2, "No such file or directory"))
    monkeypatch.setattr(trust, "should_allow", should_allow)
    sent = await reattach(connect_frame(keys), authenticated_conn(keys), trust=trust)

    assert sent[0]["type"] == "CONNECTED"
    should_allow.assert_not_called()


@pytest.mark.asyncio
async def test_reattach_does_not_reinitialize_identity_bound_mode_policy(keys):
    trust = TrustAgent("open")
    trust.is_admin = MagicMock(side_effect=FileNotFoundError(2, "No such file or directory"))
    trust.get_level = MagicMock(side_effect=FileNotFoundError(2, "No such file or directory"))
    policy = MagicMock()
    policy.state.return_value = {"currentModeId": "read-only"}
    conn = authenticated_conn(keys)
    conn.update({"mode_is_admin": False, "session": {"mode": "read-only"}})

    sent = await reattach(
        connect_frame(keys),
        conn,
        trust=trust,
        route_handlers={
            "agent_metadata": {"address": RECIPIENT},
            "session_modes": policy,
            "trust_agent": trust,
            "result_ttl": 60,
        },
    )

    assert sent[0]["type"] == "CONNECTED"
    assert sent[0]["session_modes"] == {"currentModeId": "read-only"}
    trust.is_admin.assert_not_called()
    trust.get_level.assert_not_called()


@pytest.mark.asyncio
async def test_reattach_still_enforces_current_blacklist(keys):
    sent = await reattach(
        connect_frame(keys),
        authenticated_conn(keys),
        blacklist=[keys["address"]],
    )

    assert sent == [{"type": "ERROR", "message": "forbidden: blacklisted"}]


@pytest.mark.asyncio
async def test_equivalent_fresh_connect_reattaches(keys):
    sent = await reattach(connect_frame(keys), authenticated_conn(keys))

    assert sent[0]["type"] == "CONNECTED"
    assert sent[0]["session_id"] == SESSION_ID
    assert sent[0]["status"] == "new"
    assert sent[0]["protocol"]["name"] == "oip"


@pytest.mark.asyncio
async def test_session_loop_treats_a_fresh_equivalent_connect_as_reattach(keys):
    from connectonion.network.host.ws_router.session import run_ws_session

    first = connect_frame(keys)
    queue = [first, freshly_resign(first, keys)]
    sent = []
    storage = MagicMock()
    storage.get.return_value = None
    registry = MagicMock()
    registry.get.return_value = None

    async def recv():
        return queue.pop(0) if queue else None

    async def send(message):
        sent.append(message)

    await run_ws_session(
        send,
        recv,
        route_handlers={"agent_metadata": {"address": RECIPIENT}},
        storage=storage,
        registry=registry,
        trust="open",
        enable_ping=False,
    )

    connected = [message for message in sent if message["type"] == "CONNECTED"]
    assert [message["session_id"] for message in connected] == [SESSION_ID, SESSION_ID]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["identity", "recipient", "capability", "session", "protocol"]
)
async def test_reattach_cannot_change_authenticated_connection(keys, change):
    frame = connect_frame(keys)
    if change == "identity":
        frame = connect_frame(address.generate())
    elif change == "recipient":
        frame = connect_frame(keys, recipient="0x" + "34" * 20)
    elif change == "capability":
        frame["payload"]["signed_commands"] = 0
    elif change == "session":
        frame["session_id"] = "other-session"
    else:
        frame["protocol"] = {"name": "legacy", "version": "1"}

    sent = await reattach(frame, authenticated_conn(keys))

    assert sent == [{
        "type": "ERROR",
        "message": "already authenticated: open a new connection",
    }]


@pytest.mark.asyncio
async def test_reattach_connect_signature_cannot_be_replayed(keys):
    frame = connect_frame(keys)
    conn = authenticated_conn(keys)

    assert (await reattach(frame, conn))[0]["type"] == "CONNECTED"
    replay = await reattach(frame, conn)

    assert replay[0]["type"] == "ERROR"
    assert "already used" in replay[0]["message"]
