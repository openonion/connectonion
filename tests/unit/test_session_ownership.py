"""Security regressions for owner-bound hosted sessions and trusted controls."""

import asyncio
import json
import threading
import time
from copy import deepcopy
from unittest.mock import patch

import pytest
from nacl.signing import SigningKey

from connectonion import Agent
from connectonion.network.connect import RemoteAgent
from connectonion.network.host.auth import (
    _authenticate_signed,
    canonical_attachments_sha256,
    canonical_session_sha256,
    verify_signature,
)
from connectonion.network.host.http_router import (
    handle_http,
    input_handler,
    session_handler,
    sessions_handler,
)
from connectonion.network.host.session import (
    ActiveSessionRegistry,
    Session,
    SessionStorage,
)
from connectonion.network.host.ws_router.agent_io import (
    forward_agent_msgs_to_client,
    start_agent,
)
from connectonion.network.host.ws_router.connect import establish_connection
from connectonion.network.host.ws_router.session import run_ws_session
from connectonion.useful_plugins.ulw import ulw
from tests.utils.mock_helpers import MockLLM


OWNER_A = "0xowner-a"
OWNER_B = "0xowner-b"
HOST_ADDRESS = "0xtarget"
ULW_STATE = {"mode": "ulw", "ulw": {"turns": 100, "turns_used": 3}}


def _stored_session(session_id, owner=OWNER_A, *, state=None, iteration=2):
    return Session(
        session_id=session_id,
        owner_address=owner,
        status="done",
        prompt="prior",
        session={
            "session_id": session_id,
            "messages": [{"role": "user", "content": "server"}],
            "trace": [],
            "iteration": iteration,
            "updated": time.time(),
        },
        server_state=deepcopy(state or ULW_STATE),
        created=time.time(),
        expires=time.time() + 3600,
    )


class RecordingAgent:
    def __init__(self, seen, mutate=None):
        self.seen = seen
        self.mutate = mutate
        self.current_session = {}

    def input(self, prompt, *, session, images=None, files=None, mode=None):
        self.seen.append({
            "state": deepcopy(self._trusted_server_state),
            "session": deepcopy(session),
            "owner": self._session_owner_address,
            "sid_authenticated": self._session_id_authenticated,
            "mode": mode,
        })
        self.current_session = deepcopy(session)
        if mode is not None:
            self.current_session["mode"] = mode
        elif self._trusted_server_state.get("mode"):
            self.current_session["mode"] = self._trusted_server_state["mode"]
        if self.mutate:
            self.mutate(self)
        return "ok"


def _factory(seen, mutate=None):
    return lambda: RecordingAgent(seen, mutate)


def _signed_frame(frame_type, payload, *, top=None):
    signing_key = SigningKey.generate()
    address = "0x" + signing_key.verify_key.encode().hex()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    data = {
        "type": frame_type,
        "payload": payload,
        "from": address,
        "signature": "0x" + signing_key.sign(canonical.encode()).signature.hex(),
        **(top or {}),
    }
    return data, address


def _signed_get_headers(action, *, session_id=None, signing_key=None):
    signing_key = signing_key or SigningKey.generate()
    address = "0x" + signing_key.verify_key.encode().hex()
    timestamp = time.time()
    payload = {"action": action, "timestamp": timestamp, "to": HOST_ADDRESS}
    if session_id is not None:
        payload["session_id"] = session_id
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = "0x" + signing_key.sign(canonical.encode()).signature.hex()
    return [
        (b"x-from", address.encode()),
        (b"x-signature", signature.encode()),
        (b"x-timestamp", str(timestamp).encode()),
    ], address


def _bound_input_frame(
    *, session_id="sid", mode=None, request_field="input_id", session=None
):
    signing_key = SigningKey.generate()
    address = "0x" + signing_key.verify_key.encode().hex()
    request_id = "request-1"
    payload = {
        "action": "session.input",
        "to": HOST_ADDRESS,
        "timestamp": time.time(),
        "session_id": session_id,
        request_field: request_id,
        "prompt": "hello",
        "attachments_sha256": canonical_attachments_sha256(),
    }
    data = {
        "type": "INPUT",
        "to": HOST_ADDRESS,
        "session_id": session_id,
        request_field: request_id,
        "prompt": "hello",
        "payload": payload,
        "from": address,
    }
    if mode is not None:
        payload["mode"] = mode
        data["mode"] = mode
    if session is not None:
        data["session"] = deepcopy(session)
        payload["session_sha256"] = canonical_session_sha256(session)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    data["signature"] = "0x" + signing_key.sign(canonical.encode()).signature.hex()
    return data, address


class TestStoredOwnership:
    def test_session_persists_owner_and_server_state(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))

        restored = storage.get("sid")

        assert restored.owner_address == OWNER_A
        assert restored.server_state == ULW_STATE

    def test_public_session_routes_hide_owner_and_server_state(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))

        one = session_handler(storage, "sid", OWNER_A)
        listed = sessions_handler(storage, OWNER_A)["sessions"][0]

        assert "owner_address" not in one
        assert "server_state" not in one
        assert "owner_address" not in listed
        assert "server_state" not in listed

    def test_checkpoint_keeps_owner_and_monotonic_lease(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))

        storage.checkpoint(
            {"session_id": "sid", "messages": []},
            owner_address=OWNER_A,
            server_state={"mode": "ulw", "ulw": {"turns": 100, "turns_used": 1}},
        )

        restored = storage.get("sid")
        assert restored.owner_address == OWNER_A
        assert restored.server_state["ulw"]["turns_used"] == 3

    def test_checkpoint_rejects_owner_change(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))

        with pytest.raises(PermissionError, match="owner mismatch"):
            storage.checkpoint({"session_id": "sid"}, owner_address=OWNER_B)

    def test_active_registry_is_owner_scoped(self):
        registry = ActiveSessionRegistry()
        thread = threading.Thread(target=lambda: None)
        registry.register("sid", object(), thread, OWNER_A)

        assert registry.get_for_owner("sid", OWNER_A) is not None
        assert registry.get_for_owner("sid", OWNER_B) is None
        with pytest.raises(PermissionError, match="owner mismatch"):
            registry.register("sid", object(), thread, OWNER_B)

    def test_expired_running_session_is_not_immortal(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        record = _stored_session("stale")
        record.status = "running"
        record.expires = time.time() - 1
        storage.save(record)

        assert storage.get("stale") is None
        assert storage.list() == []


class TestInputOwnership:
    def test_same_owner_restores_deepcopy_and_persists_runtime_state(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))
        seen = []

        def advance(agent):
            agent._trusted_server_state["ulw"]["turns_used"] = 4

        result = input_handler(
            _factory(seen, advance),
            storage,
            "next",
            3600,
            session={
                "session_id": "sid",
                "iteration": 0,
                "server_state": {"mode": "ulw", "ulw": {"turns": 999, "turns_used": 0}},
                "_trusted_server_state": {"mode": "ulw"},
            },
            agent_address=OWNER_A,
            session_id_authenticated=True,
        )

        assert seen[0]["state"] == ULW_STATE
        assert seen[0]["owner"] == OWNER_A
        assert seen[0]["session"]["iteration"] == 2
        assert "server_state" not in seen[0]["session"]
        assert "_trusted_server_state" not in seen[0]["session"]
        assert storage.get("sid").server_state["ulw"]["turns_used"] == 4
        assert "server_state" not in result
        assert "server_state" not in result["session"]

    def test_different_owner_cannot_merge_or_claim_sid(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("shared"))
        seen = []

        with pytest.raises(PermissionError, match="owner mismatch"):
            input_handler(
                _factory(seen),
                storage,
                "steal",
                3600,
                session={"session_id": "shared", "iteration": 99},
                agent_address=OWNER_B,
                session_id_authenticated=True,
            )

        assert seen == []
        assert storage.get("shared").owner_address == OWNER_A

    def test_explicit_client_owner_mismatch_is_rejected(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        with pytest.raises(PermissionError, match="owner mismatch"):
            input_handler(
                _factory([]),
                storage,
                "hello",
                3600,
                session={"session_id": "new", "owner_address": OWNER_B},
                agent_address=OWNER_A,
                session_id_authenticated=True,
            )

    def test_legacy_unsigned_sid_does_not_restore_or_roll_back_capability(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))
        seen = []

        input_handler(
            _factory(seen),
            storage,
            "legacy",
            3600,
            session={"session_id": "sid", "iteration": 0},
            agent_address=OWNER_A,
            session_id_authenticated=False,
        )

        assert seen[0]["state"] == {}
        assert seen[0]["session"]["iteration"] == 2
        assert storage.get("sid").server_state == ULW_STATE

    def test_same_sid_concurrent_turns_are_serialized_and_monotonic(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        initial = deepcopy(ULW_STATE)
        initial["ulw"]["turns_used"] = 0
        storage.save(_stored_session("sid", state=initial))
        seen = []
        errors = []

        def advance(agent):
            used = agent._trusted_server_state["ulw"]["turns_used"]
            time.sleep(0.02)
            agent._trusted_server_state["ulw"]["turns_used"] = used + 1

        def run():
            try:
                input_handler(
                    _factory(seen, advance),
                    storage,
                    "next",
                    3600,
                    session={"session_id": "sid", "iteration": 0},
                    agent_address=OWNER_A,
                    session_id_authenticated=True,
                )
            except Exception as exc:  # pragma: no cover - assertion reports it
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        assert errors == []
        assert sorted(item["state"]["ulw"]["turns_used"] for item in seen) == [0, 1]
        assert storage.get("sid").server_state["ulw"]["turns_used"] == 2

    def test_ownerless_legacy_session_cannot_be_claimed_by_input(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("legacy", None))
        seen = []

        with pytest.raises(PermissionError, match="ownerless"):
            input_handler(
                _factory(seen),
                storage,
                "claim",
                3600,
                session={"session_id": "legacy"},
                agent_address=OWNER_A,
                session_id_authenticated=True,
            )

        assert seen == []
        assert storage.get("legacy").owner_address is None

    def test_unbound_privileged_mode_is_rejected_before_agent_runs(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        seen = []

        with pytest.raises(PermissionError, match="signed session_id"):
            input_handler(
                _factory(seen),
                storage,
                "work",
                3600,
                session={"session_id": "client-chosen"},
                agent_address=OWNER_A,
                mode="ulw",
                session_id_authenticated=False,
            )

        assert seen == []
        assert storage.get("client-chosen") is None

    def test_fresh_unbound_sid_cannot_persist_runtime_capability(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        def forge_capability(agent):
            agent._trusted_server_state = deepcopy(ULW_STATE)
            agent.current_session["mode"] = "ulw"

        input_handler(
            _factory([], forge_capability),
            storage,
            "work",
            3600,
            session={"session_id": "client-chosen"},
            agent_address=OWNER_A,
            session_id_authenticated=False,
        )

        assert storage.get("client-chosen").server_state == {}

    def test_unbound_existing_owner_can_only_persist_safe_downgrade(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))

        input_handler(
            _factory([]),
            storage,
            "stop autonomous work",
            3600,
            session={"session_id": "sid"},
            agent_address=OWNER_A,
            mode="safe",
            session_id_authenticated=False,
        )

        assert storage.get("sid").server_state == {"mode": "safe"}

    def test_llm_exception_persists_consumed_ulw_turn_without_rollback(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))

        def fail_llm(messages, tools):
            raise RuntimeError("llm failed")

        def create_agent():
            return Agent(
                "failing-ulw",
                llm=MockLLM(on_complete=fail_llm),
                plugins=[ulw],
                log=False,
                quiet=True,
            )

        with pytest.raises(RuntimeError, match="llm failed"):
            input_handler(
                create_agent,
                storage,
                "continue",
                3600,
                session={"session_id": "sid"},
                agent_address=OWNER_A,
                session_id_authenticated=True,
            )

        latest = storage.get("sid")
        assert latest.status == "error"
        assert latest.result == "llm failed"
        assert latest.server_state["ulw"]["turns_used"] == 4


@pytest.mark.asyncio
class TestHttpSessionReadOwnership:
    @staticmethod
    def _auth(data, trust, **kwargs):
        prompt, address, error = _authenticate_signed(data)
        return prompt, address, error is None, error

    async def _get(self, storage, path, headers=None):
        sent = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await handle_http(
            {"method": "GET", "path": path, "headers": headers or []},
            receive,
            send,
            route_handlers={
                "auth": self._auth,
                "recipient_address": HOST_ADDRESS,
                "session": session_handler,
                "sessions": sessions_handler,
            },
            storage=storage,
            trust="open",
            start_time=0,
        )
        return sent[0]["status"], json.loads(sent[1]["body"])

    async def test_anonymous_session_reads_are_rejected(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        one_status, _ = await self._get(storage, "/sessions/sid")
        list_status, _ = await self._get(storage, "/sessions")

        assert one_status == 401
        assert list_status == 401

    async def test_signed_list_is_filtered_to_owner(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        key = SigningKey.generate()
        headers, owner = _signed_get_headers("session.list", signing_key=key)
        storage.save(_stored_session("mine", owner))
        storage.save(_stored_session("theirs", OWNER_B))
        storage.save(_stored_session("legacy", None))

        status, body = await self._get(storage, "/sessions", headers)

        assert status == 200
        assert [item["session_id"] for item in body["sessions"]] == ["mine"]

    async def test_cross_owner_and_legacy_ownerless_read_as_not_found(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("victim", OWNER_B))
        storage.save(_stored_session("legacy", None))
        key = SigningKey.generate()

        victim_headers, _ = _signed_get_headers(
            "session.get", session_id="victim", signing_key=key
        )
        legacy_headers, _ = _signed_get_headers(
            "session.get", session_id="legacy", signing_key=key
        )

        assert (await self._get(storage, "/sessions/victim", victim_headers))[0] == 404
        assert (await self._get(storage, "/sessions/legacy", legacy_headers))[0] == 404

    async def test_session_list_signature_cannot_replay_as_get(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        headers, _ = _signed_get_headers("session.list")

        status, _ = await self._get(storage, "/sessions/sid", headers)

        assert status == 401

    async def test_admin_bearer_can_read_legacy_and_list_all(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENONION_API_KEY", "admin-key")
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("legacy", None))
        headers = [(b"authorization", b"Bearer admin-key")]

        one_status, one = await self._get(storage, "/sessions/legacy", headers)
        list_status, listed = await self._get(storage, "/sessions", headers)

        assert one_status == 200
        assert one["session_id"] == "legacy"
        assert list_status == 200
        assert [item["session_id"] for item in listed["sessions"]] == ["legacy"]


class TestSignedBindings:
    def test_remote_connect_signature_covers_existing_session_id(self):
        agent = RemoteAgent("0xtarget", keys={"address": OWNER_A})
        agent._current_session = {"session_id": "sid", "messages": []}

        with patch("connectonion.address.sign", return_value=b"x" * 64) as sign:
            message = agent._build_connect_message()

        signed_payload = json.loads(sign.call_args.args[1])
        assert message["session_id"] == "sid"
        assert message["payload"]["session_id"] == "sid"
        assert signed_payload["session_id"] == "sid"

    def test_remote_input_signature_covers_mode(self):
        agent = RemoteAgent("0xtarget", keys={"address": OWNER_A})

        with patch("connectonion.address.sign", return_value=b"x" * 64) as sign:
            message = agent._build_input_message(
                "hello", "input", mode="ulw", session_id="sid"
            )

        signed_payload = json.loads(sign.call_args.args[1])
        assert message["mode"] == "ulw"
        assert message["session_id"] == "sid"
        assert message["payload"]["mode"] == "ulw"
        assert message["payload"]["session_id"] == "sid"
        assert signed_payload["mode"] == "ulw"
        assert signed_payload["session_id"] == "sid"

    def test_connect_rejects_top_level_payload_sid_mismatch(self):
        payload = {"timestamp": time.time(), "session_id": "signed"}
        data, _ = _signed_frame(
            "CONNECT", payload, top={"session_id": "tampered"}
        )

        _, _, error = _authenticate_signed(data)

        assert error == "unauthorized: session_id mismatch"

    def test_legacy_connect_without_signed_sid_is_still_authenticated(self):
        payload = {"timestamp": time.time()}
        data, address = _signed_frame(
            "CONNECT", payload, top={"session_id": "legacy"}
        )

        _, authenticated_address, error = _authenticate_signed(data)

        assert error is None
        assert authenticated_address == address

    def test_mode_tampering_is_rejected(self):
        payload = {"prompt": "hello", "timestamp": time.time(), "mode": "ulw"}
        data, _ = _signed_frame(
            "INPUT", payload, top={"prompt": "hello", "mode": "safe"}
        )

        _, _, error = _authenticate_signed(data)

        assert error == "unauthorized: mode mismatch"

    def test_payload_mode_tampering_breaks_signature(self):
        payload = {
            "prompt": "hello",
            "timestamp": time.time(),
            "mode": "ulw",
            "session_id": "sid",
        }
        data, address = _signed_frame(
            "INPUT",
            payload,
            top={"prompt": "hello", "mode": "ulw", "session_id": "sid"},
        )
        data["payload"]["mode"] = "safe"
        data["mode"] = "safe"

        assert verify_signature(data["payload"], data["signature"], address) is False
        assert _authenticate_signed(data)[2] == "unauthorized: invalid signature"


@pytest.mark.asyncio
class TestHttpOwnershipBoundary:
    async def _request(self, data, input_handler_fn):
        messages = []

        async def receive():
            return {"body": json.dumps(data).encode(), "more_body": False}

        async def send(message):
            messages.append(message)

        class Storage:
            @staticmethod
            def claim_request(*args):
                return True

        await handle_http(
            {"method": "POST", "path": "/input", "headers": []},
            receive,
            send,
            route_handlers={
                "auth": lambda body, trust, **kwargs: (
                    body["payload"].get("prompt", ""),
                    body.get("from") or OWNER_A,
                    True,
                    None,
                ),
                "recipient_address": HOST_ADDRESS,
                "input": input_handler_fn,
            },
            storage=Storage(),
            trust="open",
            start_time=0,
        )
        return messages[0]["status"], json.loads(messages[1]["body"])

    async def test_signed_mode_sid_and_owner_are_propagated(self):
        captured = {}

        def capture(storage, prompt, session, **kwargs):
            captured.update(kwargs)
            captured["session"] = session
            return {"result": "ok", "session_id": session["session_id"]}

        data, address = _bound_input_frame(
            session_id="sid",
            mode="ulw",
            request_field="request_id",
            session={"session_id": "sid"},
        )

        status, _ = await self._request(data, capture)

        assert status == 200
        assert captured["agent_address"] == address
        assert captured["mode"] == "ulw"
        assert captured["session_id_authenticated"] is True

    async def test_http_sid_mismatch_is_rejected_before_input(self):
        called = False

        def capture(*args, **kwargs):
            nonlocal called
            called = True

        status, body = await self._request({
            "payload": {"prompt": "hello", "timestamp": time.time(), "session_id": "signed"},
            "session": {"session_id": "tampered"},
            "from": OWNER_A,
            "signature": "mocked",
        }, capture)

        assert status == 401
        assert "mismatch" in body["error"]
        assert called is False

    async def test_legacy_http_sid_cannot_restore_capabilities(self):
        captured = {}

        def capture(storage, prompt, session, **kwargs):
            captured.update(kwargs)
            return {"result": "ok", "session_id": session["session_id"]}

        status, _ = await self._request({
            "payload": {"prompt": "hello", "timestamp": time.time()},
            "session": {"session_id": "legacy"},
            "from": OWNER_A,
            "signature": "mocked",
        }, capture)

        assert status == 200
        assert captured["session_id_authenticated"] is False

    async def test_unbound_http_ulw_is_rejected_before_input(self):
        called = False

        def capture(*args, **kwargs):
            nonlocal called
            called = True

        status, body = await self._request({
            "payload": {
                "prompt": "hello",
                "timestamp": time.time(),
                "mode": "ulw",
            },
            "session": {"session_id": "legacy"},
            "from": OWNER_A,
            "signature": "mocked",
        }, capture)

        assert status == 403
        assert "fully signed INPUT" in body["error"]
        assert called is False

    async def test_synchronous_http_input_does_not_block_event_loop(self):
        started = threading.Event()
        release = threading.Event()
        safety_release = threading.Timer(0.5, release.set)

        def blocking_input(storage, prompt, session, **kwargs):
            started.set()
            release.wait(timeout=1)
            return {"result": "ok", "session_id": session["session_id"]}

        request = {
            "payload": {
                "prompt": "hello",
                "timestamp": time.time(),
                "session_id": "sid",
            },
            "session": {"session_id": "sid"},
            "from": OWNER_A,
            "signature": "mocked",
        }
        safety_release.start()
        start = time.monotonic()
        task = asyncio.create_task(self._request(request, blocking_input))
        try:
            await asyncio.sleep(0.02)
            elapsed = time.monotonic() - start
            assert started.is_set()
            assert elapsed < 0.2
        finally:
            release.set()
            safety_release.cancel()

        status, _ = await asyncio.wait_for(task, timeout=1)
        assert status == 200


@pytest.mark.asyncio
class TestWebSocketOwnershipBoundary:
    async def test_same_owner_signed_sid_can_reattach_status(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))
        registry = ActiveSessionRegistry()
        registry.register("sid", object(), threading.Thread(), OWNER_A)
        registry.mark_session_connected("sid", OWNER_A)
        sent = []

        async def send(message):
            sent.append(message)

        await establish_connection(
            {"session_id": "sid", "payload": {"session_id": "sid"}},
            OWNER_A,
            send,
            {},
            storage,
            registry,
        )

        assert sent[0]["type"] == "CONNECTED"
        assert sent[0]["status"] == "connected"

    async def test_connect_rejects_oversized_session_id_cleanly(self, tmp_path):
        session_id = "s" * 257
        sent = []

        async def send(message):
            sent.append(message)

        await establish_connection(
            {"session_id": session_id, "payload": {"session_id": session_id}},
            OWNER_A,
            send,
            {},
            SessionStorage(str(tmp_path / "sessions.jsonl")),
            ActiveSessionRegistry(),
        )

        assert sent == [{
            "type": "ERROR",
            "message": "unauthorized: session_id is too long",
        }]

    async def test_persisted_transcript_beats_signed_client_newer_snapshot(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid", iteration=2))
        client_session = {
            "session_id": "sid",
            "messages": [{"role": "system", "content": "client injection"}],
            "trace": [],
            "iteration": 999,
        }
        conn = {}
        sent = []

        async def send(message):
            sent.append(message)

        await establish_connection(
            {
                "session_id": "sid",
                "session": client_session,
                "payload": {
                    "session_id": "sid",
                    "session_sha256": canonical_session_sha256(client_session),
                },
            },
            OWNER_A,
            send,
            conn,
            storage,
            ActiveSessionRegistry(),
        )

        assert conn["session"]["messages"] == [
            {"role": "user", "content": "server"}
        ]
        assert conn["session"]["iteration"] == 2
        assert sent[0]["server_newer"] is True

    async def test_empty_persisted_transcript_beats_client_snapshot(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        stored = _stored_session("sid")
        stored.session = {}
        storage.save(stored)
        client_session = {
            "session_id": "sid",
            "messages": [{"role": "system", "content": "client injection"}],
        }
        conn = {}
        sent = []

        async def send(message):
            sent.append(message)

        await establish_connection(
            {
                "session_id": "sid",
                "session": client_session,
                "payload": {
                    "session_id": "sid",
                    "session_sha256": canonical_session_sha256(client_session),
                },
            },
            OWNER_A,
            send,
            conn,
            storage,
            ActiveSessionRegistry(),
        )

        assert conn["session"] == {}
        assert sent[0]["server_newer"] is True
        assert sent[0]["session"] == {}

    async def test_different_owner_cannot_connect_to_stored_sid(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("shared"))
        sent = []
        conn = {}

        async def send(message):
            sent.append(message)

        await establish_connection(
            {"session_id": "shared", "payload": {"session_id": "shared"}},
            OWNER_B,
            send,
            conn,
            storage,
            ActiveSessionRegistry(),
        )

        assert sent == [{"type": "ERROR", "message": "forbidden: session owner mismatch"}]
        assert conn.get("authenticated") is not True

    async def test_ownerless_legacy_session_cannot_be_claimed_by_connect(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("legacy", None))
        sent = []
        conn = {}

        async def send(message):
            sent.append(message)

        await establish_connection(
            {"session_id": "legacy", "payload": {"session_id": "legacy"}},
            OWNER_A,
            send,
            conn,
            storage,
            ActiveSessionRegistry(),
        )

        assert sent == [{
            "type": "ERROR",
            "message": (
                "forbidden: legacy ownerless session cannot be resumed; "
                "start a new session without the old session_id"
            ),
        }]
        assert conn.get("authenticated") is not True

    async def test_different_owner_cannot_reattach_running_agent_before_storage(self):
        class StorageMustNotBeRead:
            def get(self, session_id):  # pragma: no cover - failure is the assertion
                raise AssertionError("running reconnect must not read storage")

        registry = ActiveSessionRegistry()
        registry.register("shared", object(), threading.Thread(), OWNER_A)
        sent = []
        conn = {}

        async def send(message):
            sent.append(message)

        await establish_connection(
            {"session_id": "shared", "payload": {"session_id": "shared"}},
            OWNER_B,
            send,
            conn,
            StorageMustNotBeRead(),
            registry,
        )

        assert sent == [{"type": "ERROR", "message": "forbidden: session owner mismatch"}]
        assert conn.get("authenticated") is not True

    async def test_legacy_unsigned_sid_cannot_reattach_active_agent(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))
        registry = ActiveSessionRegistry()
        registry.register("sid", object(), threading.Thread(), OWNER_A)
        sent = []
        conn = {}

        async def send(message):
            sent.append(message)

        await establish_connection(
            {"session_id": "sid", "payload": {}},
            OWNER_A,
            send,
            conn,
            storage,
            registry,
        )

        assert sent == [{
            "type": "ERROR",
            "message": "unauthorized: signed session_id required to resume active session",
        }]
        assert conn.get("authenticated") is not True

    async def test_running_reconnect_does_not_wait_for_session_storage_lock(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        lock_held = threading.Event()
        release_lock = threading.Event()

        def hold_session_lock():
            with storage.session_lock("sid"):
                lock_held.set()
                release_lock.wait(timeout=2)

        lock_thread = threading.Thread(target=hold_session_lock, daemon=True)
        lock_thread.start()
        assert lock_held.wait(timeout=1)

        class WaitingIO:
            def __init__(self):
                self.rewound_to = None

            def rewind_to(self, message_id):
                self.rewound_to = message_id

            async def read_msgs_from_agent(self):
                await asyncio.Event().wait()
                yield  # pragma: no cover - cancellation ends the wait

        io = WaitingIO()
        registry = ActiveSessionRegistry()
        registry.register("sid", io, lock_thread, OWNER_A)
        sent = []
        conn = {}

        async def send(message):
            sent.append(message)

        try:
            result = await asyncio.wait_for(
                establish_connection(
                    {
                        "session_id": "sid",
                        "payload": {"session_id": "sid"},
                        "last_msg_id": "event-7",
                    },
                    OWNER_A,
                    send,
                    conn,
                    storage,
                    registry,
                ),
                timeout=0.2,
            )
            _, forward_task = result

            assert sent[0] == {
                "type": "CONNECTED",
                "session_id": "sid",
                "status": "running",
            }
            assert io.rewound_to == "event-7"
            assert conn["session_id_authenticated"] is True
        finally:
            release_lock.set()
            lock_thread.join(timeout=1)
            if 'forward_task' in locals():
                forward_task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await forward_task

    async def test_running_reconnect_does_not_accept_client_transcript(self):
        class StorageMustNotBeRead:
            def get(self, session_id):  # pragma: no cover - failure is the assertion
                raise AssertionError("running reconnect must not read storage")

        class WaitingIO:
            def rewind_to(self, message_id):
                pass

            async def read_msgs_from_agent(self):
                await asyncio.Event().wait()
                yield  # pragma: no cover - cancellation ends the wait

        registry = ActiveSessionRegistry()
        registry.register("sid", WaitingIO(), threading.Thread(), OWNER_A)
        conn = {}
        sent = []

        async def send(message):
            sent.append(message)

        _, forward_task = await establish_connection(
            {
                "session_id": "sid",
                "session": {
                    "session_id": "sid",
                    "messages": [{"role": "system", "content": "client injection"}],
                },
                "payload": {"session_id": "sid"},
            },
            OWNER_A,
            send,
            conn,
            StorageMustNotBeRead(),
            registry,
        )
        forward_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await forward_task

        assert conn["session"] == {}

    async def test_next_turn_reloads_owner_bound_persisted_transcript(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(_stored_session("sid"))
        registry = ActiveSessionRegistry()
        registry.register("sid", object(), threading.Thread(), OWNER_A)
        registry.mark_session_connected("sid", OWNER_A)
        captured = {}
        sent = []

        async def send(message):
            sent.append(message)

        def ws_input(storage, prompt, io, session, images, files, **kwargs):
            captured["session"] = deepcopy(session)
            return {"result": "ok", "duration_ms": 1, "session": session}

        _, forward_task = await start_agent(
            {"type": "INPUT", "prompt": "next turn"},
            send,
            {
                "authenticated": True,
                "agent_address": OWNER_A,
                "session_id": "sid",
                "session_id_authenticated": True,
                "session_authenticated": True,
                "session": {
                    "session_id": "sid",
                    "messages": [
                        {"role": "system", "content": "client injection"}
                    ],
                },
            },
            {"ws_input": ws_input},
            storage,
            registry,
        )
        await asyncio.wait_for(forward_task, timeout=1)

        assert captured["session"]["messages"] == [
            {"role": "user", "content": "server"}
        ]

    async def test_legacy_same_owner_connected_session_can_start_plain_turn(self, tmp_path):
        registry = ActiveSessionRegistry()
        registry.register("sid", object(), threading.Thread(), OWNER_A)
        registry.mark_session_connected("sid", OWNER_A)
        captured = {}
        sent = []

        async def send(message):
            sent.append(message)

        def ws_input(storage, prompt, io, session, images, files, **kwargs):
            captured.update(kwargs)
            return {"result": "ok", "duration_ms": 1, "session": session}

        result = await start_agent(
            {"type": "INPUT", "prompt": "plain legacy turn"},
            send,
            {
                "authenticated": True,
                "agent_address": OWNER_A,
                "session_id": "sid",
                "session_id_authenticated": False,
                "session": {"session_id": "sid"},
            },
            {"ws_input": ws_input},
            SessionStorage(str(tmp_path / "sessions.jsonl")),
            registry,
        )
        _, forward_task = result
        await asyncio.wait_for(forward_task, timeout=1)

        assert captured["session_id_authenticated"] is False
        assert registry.get_for_owner("sid", OWNER_A).status == "connected"

    async def test_session_status_only_reports_matching_owner(self, tmp_path):
        registry = ActiveSessionRegistry()
        registry.register("mine", object(), threading.Thread(), OWNER_A)
        registry.mark_session_connected("mine", OWNER_A)
        registry.register("theirs", object(), threading.Thread(), OWNER_B)
        registry.mark_session_connected("theirs", OWNER_B)
        incoming = iter([
            {"type": "CONNECT", "session_id": "control", "payload": {"session_id": "control"}},
            {"type": "SESSION_STATUS", "session_id": "mine"},
            {"type": "SESSION_STATUS", "session_id": "theirs"},
        ])
        sent = []

        async def recv():
            return next(incoming, None)

        async def send(message):
            sent.append(message)

        await run_ws_session(
            send,
            recv,
            route_handlers={
                "auth": lambda *args, **kwargs: ("", OWNER_A, True, None),
                "trust_agent": object(),
            },
            storage=SessionStorage(str(tmp_path / "sessions.jsonl")),
            registry=registry,
            trust="open",
            enable_ping=False,
        )

        statuses = [m for m in sent if m["type"] == "SESSION_STATUS"]
        assert statuses[0]["status"] == "connected"
        assert statuses[1]["status"] == "not_found"

    async def test_signed_ws_mode_reaches_input_handler(self, tmp_path):
        data, address = _bound_input_frame(session_id="sid", mode="ulw")
        captured = {}
        sent = []

        async def send(message):
            sent.append(message)

        def ws_input(storage, prompt, io, session, images, files, **kwargs):
            captured.update(kwargs)
            return {"result": "ok", "duration_ms": 1, "session": session}

        result = await start_agent(
            data,
            send,
            {
                "authenticated": True,
                "agent_address": address,
                "session_id": "sid",
                "session_id_authenticated": True,
                "session_authenticated": True,
                "session": {"session_id": "sid"},
            },
            {"ws_input": ws_input, "recipient_address": HOST_ADDRESS},
            SessionStorage(str(tmp_path / "sessions.jsonl")),
            ActiveSessionRegistry(),
        )
        _, forward_task = result
        await asyncio.wait_for(forward_task, timeout=1)

        assert captured["agent_address"] == address
        assert captured["mode"] == "ulw"
        assert captured["session_id_authenticated"] is True

    async def test_tampered_ws_mode_never_starts_agent(self, tmp_path):
        payload = {"prompt": "hello", "timestamp": time.time(), "mode": "ulw"}
        data, address = _signed_frame(
            "INPUT", payload, top={"prompt": "hello", "mode": "safe"}
        )
        called = False
        sent = []

        async def send(message):
            sent.append(message)

        def ws_input(*args, **kwargs):
            nonlocal called
            called = True

        result = await start_agent(
            data,
            send,
            {
                "authenticated": True,
                "agent_address": address,
                "session_id": "sid",
                "session_id_authenticated": True,
                "session": {"session_id": "sid"},
            },
            {"ws_input": ws_input},
            SessionStorage(str(tmp_path / "sessions.jsonl")),
            ActiveSessionRegistry(),
        )

        assert result is None
        assert called is False
        assert sent[0]["message"] == "unauthorized: mode mismatch"

    async def test_signed_input_cannot_replay_across_same_owner_sessions(self, tmp_path):
        data, address = _bound_input_frame(session_id="sid-a", mode="ulw")
        called = False
        sent = []

        async def send(message):
            sent.append(message)

        def ws_input(*args, **kwargs):
            nonlocal called
            called = True

        result = await start_agent(
            data,
            send,
            {
                "authenticated": True,
                "agent_address": address,
                "session_id": "sid-b",
                "session_id_authenticated": True,
                "session_authenticated": True,
                "session": {"session_id": "sid-b"},
            },
            {"ws_input": ws_input, "recipient_address": HOST_ADDRESS},
            SessionStorage(str(tmp_path / "sessions.jsonl")),
            ActiveSessionRegistry(),
        )

        assert result is None
        assert called is False
        assert sent[0]["message"] == "unauthorized: INPUT session_id mismatch"

    async def test_unbound_ws_ulw_is_rejected_before_agent_runs(self, tmp_path):
        payload = {"prompt": "hello", "timestamp": time.time(), "mode": "ulw"}
        data, address = _signed_frame(
            "INPUT", payload, top={"prompt": "hello", "mode": "ulw"}
        )
        called = False
        sent = []

        async def send(message):
            sent.append(message)

        def ws_input(*args, **kwargs):
            nonlocal called
            called = True

        result = await start_agent(
            data,
            send,
            {
                "authenticated": True,
                "agent_address": address,
                "session_id": "legacy",
                "session_id_authenticated": False,
                "session": {"session_id": "legacy"},
            },
            {"ws_input": ws_input},
            SessionStorage(str(tmp_path / "sessions.jsonl")),
            ActiveSessionRegistry(),
        )

        assert result is None
        assert called is False
        assert sent[0]["message"] == "fully signed INPUT required for non-safe mode"

    async def test_legacy_ws_approval_response_remains_compatible(self, tmp_path):
        incoming = iter([
            {"type": "CONNECT", "session_id": "legacy", "payload": {}},
            {"type": "INPUT", "prompt": "ordinary turn"},
            {"type": "APPROVAL_RESPONSE", "approved": True},
        ])
        sent = []
        received = []
        done = threading.Event()

        async def recv():
            return next(incoming, None)

        async def send(message):
            sent.append(message)

        def ws_input(storage, prompt, io, session, images, files, **kwargs):
            received.append(io.receive())
            done.set()
            return {"result": "ok", "duration_ms": 1, "session": session}

        await run_ws_session(
            send,
            recv,
            route_handlers={
                "auth": lambda *args, **kwargs: ("", OWNER_A, True, None),
                "trust_agent": object(),
                "ws_input": ws_input,
            },
            storage=SessionStorage(str(tmp_path / "sessions.jsonl")),
            registry=ActiveSessionRegistry(),
            trust="open",
            enable_ping=False,
        )

        assert done.wait(timeout=1)
        assert received == [{"type": "APPROVAL_RESPONSE", "approved": True}]
        assert not any(message.get("type") == "ERROR" for message in sent)
