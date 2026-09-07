"""Host and Python client share one exact ConnectOnion 1.7 mode contract."""

import json

import pytest

from connectonion.network.connect import PermissionModeError, RemoteAgent
from connectonion.network.host.session.mode import (
    HostPermissionPolicy,
    ModeTransactionError,
    session_with_durable_policy,
)


def test_fresh_and_unknown_host_state_is_auto_for_every_participant():
    policy = HostPermissionPolicy()

    for is_admin in (False, True):
        assert policy.state({}, is_admin=is_admin) == {
            "currentModeId": "auto",
            "turnsLeft": None,
            "availableModes": [
                {"id": "read-only", "name": "Read only"},
                {"id": "auto", "name": "Auto"},
            ],
        }
        normalized = policy.normalized(
            {
                "mode": ":workspace",
                "permission_profile": ":workspace",
                "skip_tool_approval": True,
            },
            is_admin=is_admin,
        )
        assert normalized["mode"] == "auto"
        assert "permission_profile" not in normalized
        assert "skip_tool_approval" not in normalized


def test_host_accepts_only_exact_modes_and_bounds_full_access():
    policy = HostPermissionPolicy(full_access_turns=8)

    assert policy.apply({}, "read-only", is_admin=False)["mode"] == "read-only"
    assert policy.apply({}, "auto", is_admin=False)["mode"] == "auto"
    assert policy.apply({}, "full-access", is_admin=False) == {
        "mode": "full-access",
        "turns_left": 8,
    }
    with pytest.raises(ModeTransactionError, match="Unsupported mode"):
        policy.apply({}, ":danger-full-access", is_admin=True)
    with pytest.raises(ModeTransactionError, match="Unsupported mode"):
        policy.apply({}, "plan", is_admin=True)


def test_client_cannot_smuggle_authority_over_durable_host_state():
    merged = session_with_durable_policy(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "mode": "full-access",
            "turns_left": 999,
            "permission_profile": ":danger-full-access",
        },
        {"mode": "auto", "permissions": {"read": {"allowed": True}}},
    )

    assert merged == {
        "messages": [{"role": "user", "content": "hello"}],
        "mode": "auto",
        "permissions": {"read": {"allowed": True}},
    }


class _WebSocket:
    def __init__(self, *events):
        self.events = [json.dumps(event) for event in events]

    async def recv(self):
        return self.events.pop(0)

    async def send(self, _message):
        return None


@pytest.mark.asyncio
async def test_remote_client_records_the_acknowledged_full_access_budget():
    agent = RemoteAgent("0x123")
    agent._current_session = {"mode": "auto"}
    ws = _WebSocket({
        "type": "mode_changed",
        "mode": "full-access",
        "turns_left": 5,
    })

    await agent._wait_for_mode_response(ws, "full-access")

    assert agent.current_session == {"mode": "full-access", "turns_left": 5}


@pytest.mark.asyncio
async def test_remote_client_rejects_a_noncanonical_acknowledgement():
    agent = RemoteAgent("0x123")
    agent._current_session = {"mode": "auto"}
    ws = _WebSocket({"type": "mode_changed", "mode": ":workspace"})

    with pytest.raises(PermissionModeError, match="invalid mode"):
        await agent._wait_for_mode_response(ws, "auto")


def test_remote_client_accepts_one_canonical_connected_state():
    agent = RemoteAgent("0x123")
    agent._current_session = {"mode": "auto", "turns_left": 99}
    advertised = {
        "currentModeId": "full-access",
        "turnsLeft": 4,
        "availableModes": [
            {"id": "read-only", "name": "Read only"},
            {"id": "auto", "name": "Auto"},
            {"id": "full-access", "name": "Full access"},
        ],
    }

    assert agent._consume_connected_mode_state({"session_modes": advertised}) is advertised
    assert agent.current_session == {"mode": "full-access", "turns_left": 4}
    assert agent.available_modes == advertised["availableModes"]


@pytest.mark.parametrize(
    "advertised",
    [
        {
            "currentModeId": ":workspace",
            "turnsLeft": None,
            "availableModes": [{"id": ":workspace", "name": "Legacy"}],
        },
        {
            "currentModeId": "full-access",
            "turnsLeft": None,
            "availableModes": [{"id": "full-access", "name": "Full access"}],
        },
        {
            "currentModeId": "auto",
            "turnsLeft": 3,
            "availableModes": [{"id": "auto", "name": "Auto"}],
        },
        {
            "currentModeId": "auto",
            "turnsLeft": None,
            "availableModes": [
                {"id": "auto", "name": "Auto"},
                {"id": "auto", "name": "Duplicate"},
            ],
        },
        {
            "currentModeId": "auto",
            "turnsLeft": None,
            "availableModes": [{"id": "read-only", "name": "Read only"}],
        },
    ],
)
def test_remote_client_rejects_invalid_connected_mode_state(advertised):
    agent = RemoteAgent("0x123")
    agent._current_session = {"mode": "auto"}

    with pytest.raises(PermissionModeError, match="invalid|inconsistent"):
        agent._consume_connected_mode_state({"session_modes": advertised})
