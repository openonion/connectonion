import asyncio
import threading
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from connectonion.core.acp_wire import (
    ACP_SCHEMA_VERSION,
    acp_session_mode_state,
    acp_set_mode_error_frame,
    acp_set_mode_request,
    acp_set_mode_request_frame,
    acp_set_mode_request_id,
    acp_set_mode_response,
    acp_set_mode_response_frame,
    host_session_mode_state,
)
from connectonion.network.connect import ACPModeError, RemoteAgent
from connectonion.network.host.session import SessionStorage
from connectonion.network.host.session.mode import (
    HostModePolicy,
    ModeTransactionError,
    claim_host_prompt,
    commit_host_session_mode,
    ensure_host_mode_session,
)

SESSION_ID = "session-mode-883"
REQUEST_ID = "request-mode-883"


@pytest.fixture
def storage(tmp_path):
    return SessionStorage(tmp_path / "sessions.jsonl")


def requester(address="0xowner", level="admin"):
    return {"address": address, "level": level}


def request(*, session_id=SESSION_ID, mode_id="auto_approve", **message_fields):
    return {
        "type": "ACP_REQUEST",
        "acpSchema": ACP_SCHEMA_VERSION,
        "message": {
            "jsonrpc": "2.0",
            "id": REQUEST_ID,
            "method": "session/set_mode",
            "params": {"sessionId": session_id, "modeId": mode_id},
            **message_fields,
        },
    }


def test_exact_official_session_mode_state_uses_persisted_ids():
    assert acp_session_mode_state(
        "auto_approve", ["default", "auto_approve", "full_access"]
    ) == {
        "currentModeId": "auto_approve",
        "availableModes": [
            {
                "id": "default",
                "name": "Default",
                "description": "Ask before unapproved sensitive actions.",
            },
            {
                "id": "auto_approve",
                "name": "Auto-approve",
                "description": "Apply edits automatically; other sensitive actions follow policy.",
            },
            {
                "id": "full_access",
                "name": "Full access (YOLO)",
                "description": "Run without approval prompts within the Host launch ceiling.",
            },
        ],
    }


def test_mode_state_rejects_plan_unknown_duplicates_and_unadvertised_current():
    with pytest.raises(ValueError, match="Unsupported approval mode"):
        acp_session_mode_state("plan", ["default"])
    with pytest.raises(ValueError, match="Unsupported approval mode"):
        acp_session_mode_state("default", ["default", "future"])
    with pytest.raises(ValueError, match="duplicate"):
        acp_session_mode_state("default", ["default", "default"])
    with pytest.raises(ValueError, match="not advertised"):
        acp_session_mode_state("auto_approve", ["default"])


def test_exact_set_mode_request_parses_through_official_model():
    assert acp_set_mode_request_frame(
        REQUEST_ID, SESSION_ID, "auto_approve"
    ) == request()
    assert acp_set_mode_request(
        request(), expected_session_id=SESSION_ID
    ) == (REQUEST_ID, "auto_approve")
    assert acp_set_mode_request_id(request()) == REQUEST_ID


@pytest.mark.parametrize(
    ("legacy", "canonical"),
    [
        ("safe", "default"),
        ("accept_edits", "auto_approve"),
        ("ulw", "full_access"),
    ],
)
def test_rolling_upgrade_requests_normalize_before_commit(legacy, canonical):
    assert acp_set_mode_request(
        request(mode_id=legacy), expected_session_id=SESSION_ID
    ) == (REQUEST_ID, canonical)


@pytest.mark.parametrize(
    "frame, message",
    [
        (request(session_id="another-session"), "another session"),
        (request(mode_id="plan"), "Unsupported approval mode"),
        (request(extra=True), "exact JSON-RPC request"),
        ({**request(), "acpSchema": "future"}, "carrier schema"),
        ({**request(), "type": "ACP_RESPONSE"}, "request carrier"),
    ],
)
def test_set_mode_request_fails_closed(frame, message):
    with pytest.raises(ValueError, match=message):
        acp_set_mode_request(frame, expected_session_id=SESSION_ID)


def test_set_mode_request_allows_meta_but_never_reads_authority_from_it():
    frame = request(mode_id="default")
    frame["message"]["params"]["_meta"] = {
        "turns": 999999,
        "modeId": "full_access",
    }

    assert acp_set_mode_request(
        frame, expected_session_id=SESSION_ID
    ) == (REQUEST_ID, "default")


def test_exact_success_and_error_response_carriers():
    assert acp_set_mode_response_frame(REQUEST_ID, SESSION_ID) == {
        "type": "ACP_RESPONSE",
        "acpSchema": ACP_SCHEMA_VERSION,
        "sessionId": SESSION_ID,
        "message": {
            "jsonrpc": "2.0",
            "id": REQUEST_ID,
            "result": {},
        },
    }


def test_client_decodes_exact_advertisement_and_owned_response():
    connected = {
        "type": "CONNECTED",
        "carrier_capabilities": {
            "acp": {
                "schema": ACP_SCHEMA_VERSION,
                "client_requests": ["session/set_mode"],
            }
        },
        "session_modes": acp_session_mode_state(
            "default", ["default", "auto_approve"]
        ),
    }

    assert host_session_mode_state(connected)["currentModeId"] == "default"
    assert acp_set_mode_response(
        acp_set_mode_response_frame(REQUEST_ID, SESSION_ID),
        expected_request_id=REQUEST_ID,
        expected_session_id=SESSION_ID,
    ) == {"result": {}}
    assert acp_set_mode_response(
        acp_set_mode_error_frame(
            REQUEST_ID, SESSION_ID, -32000, "Session is busy",
            {"retryable": True},
        ),
        expected_request_id=REQUEST_ID,
        expected_session_id=SESSION_ID,
    ) == {
        "error": {
            "code": -32000,
            "message": "Session is busy",
            "data": {"retryable": True},
        }
    }
    assert acp_set_mode_error_frame(
        REQUEST_ID,
        SESSION_ID,
        -32000,
        "Session is busy",
        {"retryable": True},
    ) == {
        "type": "ACP_RESPONSE",
        "acpSchema": ACP_SCHEMA_VERSION,
        "sessionId": SESSION_ID,
        "message": {
            "jsonrpc": "2.0",
            "id": REQUEST_ID,
            "error": {
                "code": -32000,
                "message": "Session is busy",
                "data": {"retryable": True},
            },
        },
    }


def test_mode_policy_advertises_only_identity_and_launch_authority():
    safe_only = HostModePolicy()
    with_full_access = HostModePolicy(full_access_turns=7)

    assert safe_only.available_mode_ids(is_admin=False) == ("default",)
    assert safe_only.available_mode_ids(is_admin=True) == (
        "default", "auto_approve"
    )
    assert with_full_access.available_mode_ids(is_admin=False) == ("default",)
    assert with_full_access.available_mode_ids(is_admin=True) == (
        "default", "auto_approve", "full_access"
    )


@pytest.mark.parametrize("turns", [True, 0, -1, "7"])
def test_mode_policy_rejects_an_invalid_launch_ceiling(turns):
    with pytest.raises(ValueError, match="positive integer"):
        HostModePolicy(full_access_turns=turns)


def test_connect_persists_an_owned_default_session_before_first_prompt(storage):
    policy = HostModePolicy()

    record = ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )

    assert record.status == "connected"
    assert record.prompt == ""
    assert record.session == {
        "session_id": SESSION_ID,
        "messages": [],
        "trace": [],
        "turn": 0,
        "mode": "default",
        "requester": requester(),
    }
    assert storage.get(SESSION_ID).session == record.session
    assert 3599 <= record.expires - time.time() <= 3600


def test_idle_mode_commit_preserves_history_owner_and_ttl(storage):
    policy = HostModePolicy()
    original = ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )
    original.session["messages"] = [{"role": "user", "content": "keep"}]
    original.session["permissions"] = {"bash": ["git status"]}
    storage.save(original)

    changed = commit_host_session_mode(
        storage,
        registry=None,
        session_id=SESSION_ID,
        owner="0xowner",
        mode_id="auto_approve",
        policy=policy,
        is_admin=True,
    )

    assert changed.session["mode"] == "auto_approve"
    assert changed.session["messages"] == [
        {"role": "user", "content": "keep"}
    ]
    assert changed.session["permissions"] == {"bash": ["git status"]}
    assert changed.session["requester"] == requester()
    assert changed.created == original.created
    assert changed.expires == original.expires


def test_full_access_uses_only_server_ceiling_and_downgrade_removes_all_bypass(storage):
    policy = HostModePolicy(full_access_turns=7)
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )

    full_access = commit_host_session_mode(
        storage, None, SESSION_ID, "0xowner", "full_access", policy, True
    )
    assert full_access.session["mode"] == "full_access"
    assert full_access.session["full_access_turns"] == 7
    assert full_access.session["full_access_turns_used"] == 0
    assert full_access.session["skip_tool_approval"] is True

    safe = commit_host_session_mode(
        storage, None, SESSION_ID, "0xowner", "default", policy, True
    )
    assert safe.session["mode"] == "default"
    assert not {
        "full_access_turns", "full_access_turns_used", "skip_tool_approval"
    } & safe.session.keys()


@pytest.mark.parametrize(
    "corrupt",
    [
        {
            "mode": "default",
            "skip_tool_approval": True,
            "full_access_turns": 7,
            "full_access_turns_used": 0,
        },
        {
            "mode": "full_access",
            "skip_tool_approval": True,
            "full_access_turns": 100,
            "full_access_turns_used": 0,
        },
    ],
)
def test_corrupt_durable_authority_fails_closed_without_append(storage, corrupt):
    policy = HostModePolicy(full_access_turns=7)
    record = ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )
    corrupt_session = deepcopy(record.session)
    corrupt_session.update(corrupt)
    storage.save(record.model_copy(update={"session": corrupt_session}))
    before = storage.path.read_text()

    with pytest.raises(ModeTransactionError) as exc_info:
        commit_host_session_mode(
            storage, None, SESSION_ID, "0xowner", "default", policy, True
        )

    assert exc_info.value.code == -32602
    assert storage.path.read_text() == before
    assert storage.get(SESSION_ID).session == corrupt_session


@pytest.mark.parametrize("mode_id", ["auto_approve", "full_access"])
def test_non_admin_cannot_select_more_authority(storage, mode_id):
    policy = HostModePolicy(full_access_turns=7)
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(level="contact"),
        result_ttl=3600,
        policy=policy,
        is_admin=False,
    )

    with pytest.raises(ModeTransactionError) as exc_info:
        commit_host_session_mode(
            storage, None, SESSION_ID, "0xowner", mode_id, policy, False
        )

    assert exc_info.value.code == -32602
    assert storage.get(SESSION_ID).session["mode"] == "default"


@pytest.mark.parametrize("status", ["running", "waiting_approval"])
def test_durable_busy_record_rejects_without_mutation(storage, status):
    policy = HostModePolicy()
    record = ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )
    storage.save(record.model_copy(update={"status": status}))

    with pytest.raises(ModeTransactionError) as exc_info:
        commit_host_session_mode(
            storage, None, SESSION_ID, "0xowner", "auto_approve", policy, True
        )

    assert exc_info.value.code == -32000
    assert exc_info.value.data == {"retryable": True}
    assert storage.get(SESSION_ID).session["mode"] == "default"


def test_wrong_owner_and_missing_session_are_indistinguishable(storage):
    policy = HostModePolicy()
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )

    for session_id, owner in [
        (SESSION_ID, "0xattacker"),
        ("missing", "0xowner"),
    ]:
        with pytest.raises(ModeTransactionError) as exc_info:
            commit_host_session_mode(
                storage, None, session_id, owner, "default", policy, True
            )
        assert exc_info.value.code == -32002
        assert exc_info.value.message == "Session not found"


@pytest.mark.parametrize(
    "claimant",
    [None, requester(address="0xattacker")],
)
def test_owned_prompt_cannot_be_claimed_without_matching_identity(storage, claimant):
    policy = HostModePolicy()
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )
    before = storage.path.read_text()

    with pytest.raises(ModeTransactionError) as exc_info:
        claim_host_prompt(
            storage,
            SESSION_ID,
            "steal this session",
            3600,
            {"session_id": SESSION_ID},
            requester=claimant,
            policy=policy,
            is_admin=False,
        )

    assert exc_info.value.code == -32002
    assert storage.path.read_text() == before


def test_process_local_running_registry_is_a_fast_busy_guard(storage):
    policy = HostModePolicy()
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )

    class Registry:
        def get(self, _session_id):
            return type("Active", (), {"status": "running", "owner": "0xowner"})()

    with pytest.raises(ModeTransactionError) as exc_info:
        commit_host_session_mode(
            storage, Registry(), SESSION_ID, "0xowner",
            "auto_approve", policy, True,
        )

    assert exc_info.value.code == -32000
    assert storage.get(SESSION_ID).session["mode"] == "default"


class Trust:
    def __init__(self, admin=True):
        self.admin = admin

    def is_admin(self, _address):
        return self.admin

    def get_level(self, _address):
        return "contact"


@pytest.mark.asyncio
async def test_connected_advertises_exact_identity_bounded_mode_state(storage):
    from connectonion.network.host.ws_router.connect import establish_connection

    sent = []
    policy = HostModePolicy(full_access_turns=7)
    route_handlers = {
        "session_modes": policy,
        "trust_agent": Trust(admin=True),
        "result_ttl": 3600,
    }
    registry = Mock()
    registry.get.return_value = None

    await establish_connection(
        {"session_id": SESSION_ID},
        "0xowner",
        AsyncMock(side_effect=lambda message: sent.append(message)),
        {},
        storage,
        registry,
        route_handlers,
    )

    connected = next(message for message in sent if message["type"] == "CONNECTED")
    assert connected["carrier_capabilities"]["acp"]["client_requests"] == [
        "session/set_mode"
    ]
    assert connected["session_modes"] == policy.state(
        storage.get(SESSION_ID).session, is_admin=True
    )
    assert connected["session_modes"]["currentModeId"] == "default"


@pytest.mark.asyncio
async def test_connected_non_admin_sees_default_only(storage):
    from connectonion.network.host.ws_router.connect import establish_connection

    sent = []
    registry = Mock()
    registry.get.return_value = None
    await establish_connection(
        {"session_id": SESSION_ID},
        "0xcontact",
        AsyncMock(side_effect=lambda message: sent.append(message)),
        {},
        storage,
        registry,
        {
            "session_modes": HostModePolicy(full_access_turns=7),
            "trust_agent": Trust(admin=False),
            "result_ttl": 3600,
        },
    )

    connected = next(message for message in sent if message["type"] == "CONNECTED")
    assert connected["session_modes"]["availableModes"] == [{
        "id": "default",
        "name": "Default",
        "description": "Ask before unapproved sensitive actions.",
    }]


@pytest.mark.asyncio
async def test_connect_mode_initialization_failure_keeps_socket_unauthenticated(
    monkeypatch, storage, caplog
):
    from connectonion.network.host.ws_router.connect import establish_connection

    private_detail = "private mode storage failure"
    monkeypatch.setattr(
        storage,
        "atomic_update",
        Mock(side_effect=OSError(private_detail)),
    )
    sent = []
    conn = {}
    registry = Mock()
    registry.get.return_value = None

    await establish_connection(
        {"session_id": SESSION_ID},
        "0xowner",
        AsyncMock(side_effect=lambda message: sent.append(message)),
        conn,
        storage,
        registry,
        {
            "session_modes": HostModePolicy(),
            "trust_agent": Trust(admin=True),
            "result_ttl": 3600,
        },
    )

    assert conn.get("authenticated") is not True
    assert sent == [{
        "type": "ERROR",
        "message": "Unable to initialize session mode",
    }]
    assert private_detail not in str(sent)
    assert private_detail in caplog.text


@pytest.mark.asyncio
async def test_idle_mode_commit_survives_a_fresh_connection(storage):
    from connectonion.network.host.ws_router.connect import establish_connection

    policy = HostModePolicy()
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )
    commit_host_session_mode(
        storage, None, SESSION_ID, "0xowner", "auto_approve", policy, True
    )
    sent = []
    conn = {}
    registry = Mock()
    registry.get.return_value = None

    await establish_connection(
        {"session_id": SESSION_ID, "session": {"mode": "default"}},
        "0xowner",
        AsyncMock(side_effect=lambda message: sent.append(message)),
        conn,
        SessionStorage(storage.path),
        registry,
        {
            "session_modes": policy,
            "trust_agent": Trust(admin=True),
            "result_ttl": 3600,
        },
    )

    connected = next(message for message in sent if message["type"] == "CONNECTED")
    assert connected["session_modes"]["currentModeId"] == "auto_approve"
    assert conn["session"]["mode"] == "auto_approve"


async def run_mode_dispatch(
    monkeypatch,
    storage,
    *frames,
    is_admin=True,
    policy=None,
    registry_status=None,
):
    from connectonion.network.host.ws_router import session as ws_session

    policy = policy or HostModePolicy(full_access_turns=7)
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(level="admin" if is_admin else "contact"),
        result_ttl=3600,
        policy=policy,
        is_admin=is_admin,
    )
    queue = [{"type": "CONNECT"}, *frames]
    sent = []

    async def fake_connect(_data, _send_msg, conn, *_args):
        conn.update(
            authenticated=True,
            agent_address="0xowner",
            session_id=SESSION_ID,
            session=storage.get(SESSION_ID).session,
            mode_is_admin=is_admin,
        )
        return None

    async def recv_msg():
        return queue.pop(0) if queue else None

    async def send_msg(message):
        sent.append(message)

    monkeypatch.setattr(ws_session, "handle_connect", fake_connect)
    registry = Mock()
    registry.get.return_value = (
        SimpleNamespace(status=registry_status, owner="0xowner")
        if registry_status else None
    )
    await ws_session.run_ws_session(
        send_msg,
        recv_msg,
        route_handlers={"session_modes": policy},
        storage=storage,
        registry=registry,
        trust=None,
        enable_ping=False,
    )
    return sent


@pytest.mark.asyncio
async def test_idle_acp_request_commits_then_acknowledges(monkeypatch, storage):
    sent = await run_mode_dispatch(monkeypatch, storage, request())

    assert sent == [acp_set_mode_response_frame(REQUEST_ID, SESSION_ID)]
    assert storage.get(SESSION_ID).session["mode"] == "auto_approve"


@pytest.mark.asyncio
async def test_busy_acp_request_returns_owned_retryable_error(monkeypatch, storage):
    sent = await run_mode_dispatch(
        monkeypatch, storage, request(), registry_status="running"
    )

    assert sent[0]["type"] == "ACP_RESPONSE"
    assert sent[0]["message"]["id"] == REQUEST_ID
    assert sent[0]["message"]["error"] == {
        "code": -32000,
        "message": "Session is busy",
        "data": {"retryable": True},
    }
    assert storage.get(SESSION_ID).session["mode"] == "default"


@pytest.mark.asyncio
async def test_malformed_owned_request_returns_invalid_params(monkeypatch, storage):
    malformed = request()
    malformed["message"]["params"]["modeId"] = "plan"

    sent = await run_mode_dispatch(monkeypatch, storage, malformed)

    assert sent[0]["type"] == "ACP_RESPONSE"
    assert sent[0]["message"]["error"]["code"] == -32602
    assert storage.get(SESSION_ID).session["mode"] == "default"


@pytest.mark.asyncio
async def test_request_for_another_session_returns_not_found(monkeypatch, storage):
    sent = await run_mode_dispatch(
        monkeypatch, storage, request(session_id="another-session")
    )

    assert sent[0]["message"]["error"] == {
        "code": -32002,
        "message": "ACP mode request belongs to another session",
    }
    assert storage.get(SESSION_ID).session["mode"] == "default"


@pytest.mark.asyncio
async def test_non_admin_dispatch_cannot_gain_auto_approve(monkeypatch, storage):
    sent = await run_mode_dispatch(
        monkeypatch, storage, request(), is_admin=False
    )

    assert sent[0]["message"]["error"] == {
        "code": -32602,
        "message": "Session mode is not available",
    }
    assert storage.get(SESSION_ID).session["mode"] == "default"


@pytest.mark.asyncio
async def test_persistence_failure_returns_internal_error_without_granting_mode(
    monkeypatch, storage
):
    from connectonion.network.host.ws_router.mode import handle_acp_mode_request

    policy = HostModePolicy()
    record = ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )
    conn = {
        "authenticated": True,
        "agent_address": "0xowner",
        "session_id": SESSION_ID,
        "session": deepcopy(record.session),
        "mode_is_admin": True,
    }
    sent = []
    monkeypatch.setattr(
        storage,
        "atomic_update",
        Mock(side_effect=OSError("private storage path and details")),
    )

    handled = await handle_acp_mode_request(
        request(),
        AsyncMock(side_effect=lambda message: sent.append(message)),
        conn,
        {"session_modes": policy},
        storage,
        registry=None,
    )

    assert handled is True
    assert sent[0]["message"]["error"] == {
        "code": -32603,
        "message": "Unable to change session mode",
    }
    assert "private" not in str(sent)
    assert conn["session"]["mode"] == "default"
    assert storage.get(SESSION_ID).session["mode"] == "default"


@pytest.mark.asyncio
async def test_mode_commit_does_not_block_the_async_event_loop(
    monkeypatch, storage
):
    from connectonion.network.host.ws_router import mode as mode_router

    policy = HostModePolicy()
    record = ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )
    entered = threading.Event()
    release = threading.Event()

    def blocking_commit(*_args, **_kwargs):
        entered.set()
        release.wait(timeout=0.5)
        return record

    monkeypatch.setattr(mode_router, "commit_host_session_mode", blocking_commit)
    conn = {
        "authenticated": True,
        "agent_address": "0xowner",
        "session_id": SESSION_ID,
        "session": deepcopy(record.session),
        "mode_is_admin": True,
    }
    started = time.monotonic()
    task = asyncio.create_task(mode_router.handle_acp_mode_request(
        request(mode_id="default"),
        AsyncMock(),
        conn,
        {"session_modes": policy},
        storage,
        registry=None,
    ))
    try:
        while not entered.is_set() and time.monotonic() - started < 0.2:
            await asyncio.sleep(0.001)
        assert entered.is_set()
        assert time.monotonic() - started < 0.2
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_duplicate_request_id_is_consumed_once(monkeypatch, storage):
    sent = await run_mode_dispatch(monkeypatch, storage, request(), request())

    assert sent[0] == acp_set_mode_response_frame(REQUEST_ID, SESSION_ID)
    assert sent[1]["message"]["error"]["code"] == -32602
    assert sent[1]["message"]["error"]["message"] == "Duplicate request ID"


def test_request_id_cache_evicts_only_the_oldest_entry():
    from connectonion.network.host.ws_router.mode import _request_id_was_seen

    conn = {}
    for index in range(257):
        assert not _request_id_was_seen(conn, f"request-{index}")

    assert len(conn["mode_request_ids"]) == 256
    assert "request-0" not in conn["mode_request_ids"]
    assert _request_id_was_seen(conn, "request-256")


@pytest.mark.asyncio
async def test_unknown_acp_request_is_not_forwarded_to_agent(monkeypatch, storage):
    unknown = request()
    unknown["message"]["method"] = "session/future"

    sent = await run_mode_dispatch(monkeypatch, storage, unknown)

    assert sent == [{
        "type": "ERROR",
        "message": "unsupported ACP client request",
    }]
    assert storage.get(SESSION_ID).session["mode"] == "default"


@pytest.mark.asyncio
async def test_legacy_mode_change_uses_same_commit_and_plan_alias(monkeypatch, storage):
    policy = HostModePolicy()
    sent = await run_mode_dispatch(
        monkeypatch,
        storage,
        {"type": "mode_change", "mode": "auto_approve"},
        {"type": "mode_change", "mode": "plan", "turns": 999999},
        policy=policy,
    )

    assert sent == [
        {"type": "mode_changed", "mode": "auto_approve", "session_id": SESSION_ID},
        {"type": "mode_changed", "mode": "default", "session_id": SESSION_ID},
    ]
    safe = storage.get(SESSION_ID).session
    assert safe["mode"] == "default"
    assert "full_access_turns" not in safe


@pytest.mark.asyncio
async def test_legacy_full_access_ignores_client_turns_and_uses_launch_ceiling(
    monkeypatch, storage
):
    sent = await run_mode_dispatch(
        monkeypatch,
        storage,
        {"type": "mode_change", "mode": "full_access", "turns": 999999},
        policy=HostModePolicy(full_access_turns=7),
    )

    assert sent == [{
        "type": "mode_changed",
        "mode": "full_access",
        "session_id": SESSION_ID,
    }]
    durable = storage.get(SESSION_ID).session
    assert durable["full_access_turns"] == 7
    assert durable["full_access_turns_used"] == 0


class RecordingAgent:
    def __init__(self, seen, started=None, release=None):
        self.seen = seen
        self.started = started
        self.release = release
        self.current_session = None
        self._yolo_turns = 999999
        self._yolo_needs_activation = True
        self.io = None
        self.storage = None

    def input(self, prompt, session, images=None, files=None):
        self.seen.append({
            "prompt": prompt,
            "session": deepcopy(session),
            "yolo_turns": self._yolo_turns,
            "yolo_needs_activation": self._yolo_needs_activation,
            "host_full_access_turns_ceiling": getattr(
                self, "_host_full_access_turns_ceiling", None
            ),
        })
        if self.started:
            self.started.set()
        if self.release:
            assert self.release.wait(timeout=2)
        self.current_session = deepcopy(session)
        self.current_session["messages"].append({
            "role": "assistant", "content": "done"
        })
        return "done"


def test_mode_before_first_prompt_drives_agent_and_disarms_auto_yolo(storage):
    from connectonion.network.host.http_router import input_handler

    policy = HostModePolicy(full_access_turns=7)
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )
    commit_host_session_mode(
        storage, None, SESSION_ID, "0xowner", "auto_approve", policy, True
    )
    seen = []

    result = input_handler(
        lambda: RecordingAgent(seen),
        storage,
        "first prompt",
        3600,
        {"session_id": SESSION_ID},
        requester=requester(),
        mode_policy=policy,
        is_admin=True,
    )

    assert seen[0]["session"]["mode"] == "auto_approve"
    assert seen[0]["yolo_turns"] is None
    assert seen[0]["yolo_needs_activation"] is False
    assert seen[0]["host_full_access_turns_ceiling"] == 7
    assert result["session"]["mode"] == "auto_approve"


def test_final_host_snapshot_downgrades_invalid_agent_authority(storage, caplog):
    from connectonion.network.host.http_router import input_handler

    class CorruptingAgent(RecordingAgent):
        def input(self, *args, **kwargs):
            result = super().input(*args, **kwargs)
            self.current_session.update({
                "mode": "full_access",
                "full_access_turns": 999999,
                "full_access_turns_used": 0,
                "skip_tool_approval": True,
                "requester": requester(address="0xattacker"),
            })
            return result

    policy = HostModePolicy(full_access_turns=7)
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )

    result = input_handler(
        lambda: CorruptingAgent([]),
        storage,
        "prompt",
        3600,
        {"session_id": SESSION_ID},
        requester=requester(),
        mode_policy=policy,
        is_admin=True,
    )

    assert result["session"]["mode"] == "default"
    assert result["session"]["requester"] == requester()
    assert not {
        "full_access_turns", "full_access_turns_used", "skip_tool_approval"
    } & result["session"].keys()
    assert storage.get(SESSION_ID).session == result["session"]
    assert "invalid Host session policy" in caplog.text


def test_agent_factory_failure_releases_the_durable_prompt_claim(storage):
    from connectonion.network.host.http_router import input_handler

    policy = HostModePolicy()
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )

    def fail_factory():
        raise RuntimeError("factory failed")

    with pytest.raises(RuntimeError, match="factory failed"):
        input_handler(
            fail_factory,
            storage,
            "prompt",
            3600,
            {"session_id": SESSION_ID},
            requester=requester(),
            mode_policy=policy,
            is_admin=True,
        )

    failed = storage.get(SESSION_ID)
    assert failed.status == "failed"
    assert failed.session["mode"] == "default"
    changed = commit_host_session_mode(
        storage, None, SESSION_ID, "0xowner",
        "auto_approve", policy, True,
    )
    assert changed.session["mode"] == "auto_approve"


def test_cross_worker_mode_write_loses_to_running_prompt_claim(storage):
    from connectonion.network.host.http_router import input_handler

    policy = HostModePolicy()
    ensure_host_mode_session(
        storage,
        SESSION_ID,
        requester=requester(),
        result_ttl=3600,
        policy=policy,
        is_admin=True,
    )
    started = threading.Event()
    release = threading.Event()
    seen = []
    failures = []

    def run_prompt():
        try:
            input_handler(
                lambda: RecordingAgent(seen, started, release),
                storage,
                "blocking prompt",
                3600,
                {"session_id": SESSION_ID},
                requester=requester(),
                mode_policy=policy,
                is_admin=True,
            )
        except Exception as exc:
            failures.append(exc)

    thread = threading.Thread(target=run_prompt)
    thread.start()
    assert started.wait(timeout=2)

    other_worker_storage = SessionStorage(storage.path)
    with pytest.raises(ModeTransactionError) as exc_info:
        commit_host_session_mode(
            other_worker_storage, None, SESSION_ID, "0xowner",
            "auto_approve", policy, True,
        )
    assert exc_info.value.code == -32000

    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert failures == []
    assert storage.get(SESSION_ID).session["mode"] == "default"


class ModeClientSocket:
    def __init__(self, *, error=None, advertise=True):
        self.error = error
        self.advertise = advertise
        self.sent = []
        self.outbox = []

    async def send(self, raw):
        message = __import__("json").loads(raw)
        self.sent.append(message)
        if message.get("type") == "CONNECT":
            connected = {
                "type": "CONNECTED",
                "session_id": SESSION_ID,
                "status": "new",
            }
            if self.advertise:
                connected.update({
                    "carrier_capabilities": {
                        "acp": {
                            "schema": ACP_SCHEMA_VERSION,
                            "client_requests": ["session/set_mode"],
                        }
                    },
                    "session_modes": acp_session_mode_state(
                        "default", ["default", "auto_approve"]
                    ),
                })
            self.outbox.append(connected)
        elif message.get("type") == "ACP_REQUEST":
            request_id = message["message"]["id"]
            response_frame = (
                acp_set_mode_error_frame(
                    request_id,
                    SESSION_ID,
                    self.error["code"],
                    self.error["message"],
                    self.error.get("data"),
                )
                if self.error else
                acp_set_mode_response_frame(request_id, SESSION_ID)
            )
            self.outbox.append(response_frame)

    async def recv(self):
        if not self.outbox:
            raise AssertionError("client waited without an owned response")
        return __import__("json").dumps(self.outbox.pop(0))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def python_mode_client(socket):
    agent = RemoteAgent("0xagent", keys=False, relay_url="ws://relay.test")
    agent._try_resolve_endpoint = AsyncMock()
    agent._open_best_connection = AsyncMock(return_value=(socket, True))
    return agent


@pytest.mark.asyncio
async def test_python_client_waits_for_ack_and_applies_mode_once():
    socket = ModeClientSocket()
    agent = python_mode_client(socket)

    await agent.set_session_mode_async("auto_approve")

    assert agent.current_session == {
        "session_id": SESSION_ID,
        "mode": "auto_approve",
    }
    assert [mode["id"] for mode in agent.available_modes] == [
        "default", "auto_approve"
    ]
    request_frame = next(
        frame for frame in socket.sent if frame["type"] == "ACP_REQUEST"
    )
    assert request_frame["message"]["params"] == {
        "sessionId": SESSION_ID,
        "modeId": "auto_approve",
    }


@pytest.mark.asyncio
async def test_python_client_ack_clears_stale_full_access_authority():
    socket = ModeClientSocket()
    agent = python_mode_client(socket)
    agent._current_session = {
        "session_id": SESSION_ID,
        "mode": "full_access",
        "full_access_turns": 7,
        "full_access_turns_used": 2,
        "skip_tool_approval": True,
    }

    await agent.set_session_mode_async("default")

    assert agent.current_session == {
        "session_id": SESSION_ID,
        "mode": "default",
    }


class PingingModeClientSocket(ModeClientSocket):
    async def recv(self):
        await asyncio.sleep(0.01)
        return __import__("json").dumps({"type": "PING"})


@pytest.mark.asyncio
async def test_python_client_timeout_is_one_total_deadline_across_pings():
    agent = python_mode_client(PingingModeClientSocket())

    started = time.monotonic()
    with pytest.raises(TimeoutError, match="timed out"):
        await agent.set_session_mode_async("default", timeout=0.025)

    assert time.monotonic() - started < 0.2


class CommitWithoutAckSocket(ModeClientSocket):
    def __init__(self):
        super().__init__()
        self.committed_mode = None

    async def send(self, raw):
        message = __import__("json").loads(raw)
        if message.get("type") == "ACP_REQUEST":
            self.sent.append(message)
            self.committed_mode = message["message"]["params"]["modeId"]
            return
        await super().send(raw)

    async def recv(self):
        if self.outbox:
            return await super().recv()
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_python_client_timeout_keeps_local_state_until_reconnect():
    socket = CommitWithoutAckSocket()
    agent = python_mode_client(socket)

    with pytest.raises(TimeoutError):
        await agent.set_session_mode_async("auto_approve", timeout=0.025)

    assert socket.committed_mode == "auto_approve"
    assert agent.current_session["mode"] == "default"

    agent._consume_connected_mode_state({
        "type": "CONNECTED",
        "session_id": SESSION_ID,
        "carrier_capabilities": {
            "acp": {
                "schema": ACP_SCHEMA_VERSION,
                "client_requests": ["session/set_mode"],
            }
        },
        "session_modes": acp_session_mode_state(
            "auto_approve", ["default", "auto_approve"]
        ),
    })

    assert agent.current_session["mode"] == "auto_approve"


@pytest.mark.asyncio
async def test_python_client_keeps_mode_on_owned_policy_error():
    socket = ModeClientSocket(error={
        "code": -32000,
        "message": "Session is busy",
        "data": {"retryable": True},
    })
    agent = python_mode_client(socket)

    with pytest.raises(ACPModeError) as exc_info:
        await agent.set_session_mode_async("auto_approve")

    assert exc_info.value.code == -32000
    assert exc_info.value.data == {"retryable": True}
    assert agent.current_session["mode"] == "default"


@pytest.mark.asyncio
async def test_python_client_rejects_old_host_instead_of_inventing_durability():
    socket = ModeClientSocket(advertise=False)
    agent = python_mode_client(socket)

    with pytest.raises(ConnectionError, match="does not support"):
        await agent.set_session_mode_async("auto_approve")

    assert [frame["type"] for frame in socket.sent] == ["CONNECT"]
