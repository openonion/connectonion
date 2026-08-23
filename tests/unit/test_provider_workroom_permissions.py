import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest

from connectonion.network.host.provider_permissions import (
    ProviderPermissionError,
    commit_provider_permission,
    provider_permission_state,
)
from connectonion.network.host.session import Session, SessionStorage
from connectonion.network.host.session.mode import HostPermissionPolicy
from connectonion.plugins.coding_agents import CodexPlugin, PermissionMode


def _storage(tmp_path: Path, *, mode: str = "auto", requester_level: str = "admin"):
    storage = SessionStorage(tmp_path / "sessions.jsonl")
    storage.save(Session(
        session_id="owned-session",
        status="done",
        prompt="delegate",
        session={
            "mode": mode,
            **({"turns_left": 2} if mode == "full-access" else {}),
            "requester": {"address": "0xowner", "level": requester_level},
            "trace": [{
                "type": "provider_invocation",
                "invocationId": "codex:call-7",
                "parentToolCallId": "call-7",
                "workroomId": "codex:call-7",
                "provider": "codex",
                "providerDisplayName": "Codex",
                "status": "completed",
                "sessionId": "thread-7",
                "stateRevision": 4,
                "taskTitle": "Implement and verify the requested change",
                "resultSummary": "The provider completed its run",
            }],
        },
    ))
    return storage


def test_codex_state_keeps_workspace_boundary_and_reviewer_separate():
    state = provider_permission_state("codex", "codex:workspace-ask", "auto")

    assert state["activeOptionId"] == "codex:workspace-ask"
    options = {option["id"]: option for option in state["options"]}
    assert options["codex:workspace-ask"]["nativeProfileId"] == ":workspace"
    assert options["codex:workspace-ask"]["reviewer"] == "user"
    assert options["codex:workspace-auto"]["nativeProfileId"] == ":workspace"
    assert options["codex:workspace-auto"]["reviewer"] == "auto"
    assert options["codex:full-access"]["selectable"] is False
    assert options["codex:full-access"]["disabledReason"] == "Host permission ceiling is Auto."


def test_commit_is_revision_bound_persisted_and_applies_to_subsequent_work(tmp_path):
    storage = _storage(tmp_path)

    result = commit_provider_permission(
        storage,
        "owned-session",
        "0xowner",
        "codex:call-7",
        4,
        "codex:workspace-auto",
        request_id="permission-1",
        confirm_risk=False,
    )

    assert result["stateRevision"] == 5
    assert result["providerPermission"]["activeOptionId"] == "codex:workspace-auto"
    assert result["providerPermission"]["appliesTo"] == "subsequent_turn"
    current = storage.get("owned-session")
    assert current.session["_provider_permission_options"]["codex:call-7"] == "codex:workspace-auto"
    newest = current.session["trace"][-1]
    assert newest["type"] == "provider_invocation"
    assert newest["sessionId"] == "thread-7"
    assert newest["stateRevision"] == 5
    assert newest["providerPermission"] == result["providerPermission"]


@pytest.mark.parametrize(
    ("address", "revision", "option_id", "confirm_risk", "code"),
    [
        ("0xother", 4, "codex:workspace-auto", False, "not_owner"),
        ("0xowner", 3, "codex:workspace-auto", False, "stale_revision"),
        ("0xowner", 4, "codex:full-access", True, "ceiling_denied"),
    ],
)
def test_commit_fails_closed_for_wrong_owner_stale_state_or_host_ceiling(
    tmp_path, address, revision, option_id, confirm_risk, code,
):
    storage = _storage(tmp_path)
    with pytest.raises(ProviderPermissionError) as error:
        commit_provider_permission(
            storage,
            "owned-session",
            address,
            "codex:call-7",
            revision,
            option_id,
            request_id="permission-1",
            confirm_risk=confirm_risk,
        )
    assert error.value.code == code


def test_full_access_requires_separate_confirmation(tmp_path):
    storage = _storage(tmp_path, mode="full-access")
    with pytest.raises(ProviderPermissionError) as error:
        commit_provider_permission(
            storage,
            "owned-session",
            "0xowner",
            "codex:call-7",
            4,
            "codex:full-access",
            request_id="permission-1",
            confirm_risk=False,
        )
    assert error.value.code == "confirmation_required"

    accepted = commit_provider_permission(
        storage,
        "owned-session",
        "0xowner",
        "codex:call-7",
        4,
        "codex:full-access",
        request_id="permission-2",
        confirm_risk=True,
    )
    assert accepted["providerPermission"]["activeOptionId"] == "codex:full-access"


@pytest.mark.parametrize("requester_level", ["contact", "whitelist", "admin"])
def test_authenticated_session_actor_can_change_its_own_provider_profile(
    tmp_path, requester_level,
):
    storage = _storage(tmp_path, requester_level=requester_level)
    accepted = commit_provider_permission(
        storage,
        "owned-session",
        "0xowner",
        "codex:call-7",
        4,
        "codex:read-only",
        request_id="permission-1",
        confirm_risk=False,
    )
    assert accepted["providerPermission"]["activeOptionId"] == "codex:read-only"


@pytest.mark.parametrize("requester_level", ["stranger", "blocked", None])
def test_untrusted_or_missing_session_actor_cannot_change_a_provider_profile(
    tmp_path, requester_level,
):
    storage = _storage(tmp_path, requester_level=requester_level)
    with pytest.raises(ProviderPermissionError) as error:
        commit_provider_permission(
            storage,
            "owned-session",
            "0xowner",
            "codex:call-7",
            4,
            "codex:read-only",
            request_id="permission-1",
            confirm_risk=False,
        )
    assert error.value.code == "operator_required"


def test_direct_codex_continuation_uses_the_committed_provider_option(tmp_path):
    plugin = CodexPlugin(workspace=tmp_path, use_host_permissions=True)
    agent = type("Agent", (), {})()
    agent.current_session = {
        "mode": "auto",
        "_provider_workroom_id": "codex:call-7",
        "_provider_permission_options": {
            "codex:call-7": "codex:workspace-auto",
        },
    }

    assert plugin._policy(agent) == (
        "workspace-write",
        "auto",
        PermissionMode.AUTO,
    )


def test_lowering_outer_mode_downgrades_stored_provider_authority_and_replay(tmp_path):
    storage = _storage(tmp_path, mode="full-access")
    committed = commit_provider_permission(
        storage,
        "owned-session",
        "0xowner",
        "codex:call-7",
        4,
        "codex:full-access",
        request_id="permission-full",
        confirm_risk=True,
    )
    session = storage.get("owned-session").session

    lowered = HostPermissionPolicy(full_access_turns=2).apply(
        session,
        "read-only",
        is_admin=True,
    )

    assert committed["providerPermission"]["activeOptionId"] == "codex:full-access"
    assert lowered["_provider_permission_options"]["codex:call-7"] == "codex:read-only"
    latest = lowered["trace"][-1]
    assert latest["stateRevision"] > committed["stateRevision"]
    assert latest["providerPermission"]["activeOptionId"] == "codex:read-only"
    assert all(
        option["id"] == "codex:read-only" or option["selectable"] is False
        for option in latest["providerPermission"]["options"]
    )


def _run_permission_frame(monkeypatch, storage, frame):
    from connectonion.network.host.ws_router import session as ws_session

    sent = []
    frames = [{"type": "CONNECT"}, frame]

    async def send_msg(data):
        sent.append(data)

    async def recv_msg():
        return frames.pop(0) if frames else None

    async def connect(data, send_msg, conn, *args, **kwargs):
        conn.update({
            "authenticated": True,
            "agent_address": "0xowner",
            "session_id": "owned-session",
            "session": storage.get("owned-session").session,
        })
        return None

    monkeypatch.setattr(ws_session, "handle_connect", connect)
    asyncio.run(ws_session.run_ws_session(
        send_msg,
        recv_msg,
        route_handlers={},
        storage=storage,
        registry=Mock(),
        trust=None,
        enable_ping=False,
    ))
    return sent


def test_websocket_permission_change_acks_then_streams_durable_state(
    tmp_path, monkeypatch,
):
    storage = _storage(tmp_path)

    sent = _run_permission_frame(monkeypatch, storage, {
        "type": "PROVIDER_PERMISSION_CHANGE",
        "requestId": "permission-1",
        "invocationId": "codex:call-7",
        "stateRevision": 4,
        "optionId": "codex:workspace-auto",
        "confirmRisk": False,
    })

    assert [message["type"] for message in sent] == [
        "PROVIDER_PERMISSION_ACK",
        "provider_invocation",
    ]
    assert sent[0]["accepted"] is True
    assert sent[0]["stateRevision"] == 5
    assert sent[0]["providerPermission"]["effectiveRevision"] == 5
    assert sent[1] == storage.get("owned-session").session["trace"][-1]


def test_websocket_permission_change_rejects_stale_revision_without_mutation(
    tmp_path, monkeypatch,
):
    storage = _storage(tmp_path)

    sent = _run_permission_frame(monkeypatch, storage, {
        "type": "PROVIDER_PERMISSION_CHANGE",
        "requestId": "permission-stale",
        "invocationId": "codex:call-7",
        "stateRevision": 3,
        "optionId": "codex:workspace-auto",
    })

    assert sent == [{
        "type": "PROVIDER_PERMISSION_ACK",
        "requestId": "permission-stale",
        "invocationId": "codex:call-7",
        "accepted": False,
        "reason": "stale_revision",
    }]
    current = storage.get("owned-session").session
    assert current.get("_provider_permission_options") is None
    assert len(current["trace"]) == 1
