"""Security regressions for fully bound hosted INPUT requests."""

import asyncio
import json
import threading
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from nacl.signing import SigningKey

from connectonion.network.connect import RemoteAgent
from connectonion.network.host.auth import (
    authenticate_bound_input,
    canonical_attachments_sha256,
    canonical_session_sha256,
    extract_and_authenticate,
)
from connectonion.network.host.http_router import handle_http, input_handler
from connectonion.network.host.session import ActiveSessionRegistry, Session, SessionStorage
from connectonion.network.host.ws_router.agent_io import (
    forward_agent_msgs_to_client,
    start_agent,
)
from connectonion.network.host.ws_router.connect import establish_connection, handle_connect
from connectonion.network.host.ws_router.session import run_ws_session


HOST_A = "0xhost-a"
HOST_B = "0xhost-b"
SID = "session-1"


def _address(key):
    return "0x" + key.verify_key.encode().hex()


def _sign(key, payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "0x" + key.sign(canonical.encode()).signature.hex()


def _connect_frame(key, *, host=HOST_A, sid=SID, session=None):
    session = deepcopy(session) if session is not None else {"session_id": sid}
    payload = {
        "action": "session.connect",
        "to": host,
        "timestamp": time.time(),
        "session_id": sid,
        "session_sha256": canonical_session_sha256(session),
    }
    return {
        "type": "CONNECT",
        "to": host,
        "session_id": sid,
        "session": session,
        "payload": payload,
        "from": _address(key),
        "signature": _sign(key, payload),
    }


def _input_frame(
    key,
    *,
    host=HOST_A,
    sid=SID,
    request_id="request-1",
    request_field="input_id",
    prompt="hello",
    images=None,
    files=None,
    mode=None,
    session=None,
):
    payload = {
        "action": "session.input",
        "to": host,
        "timestamp": time.time(),
        "session_id": sid,
        request_field: request_id,
        "prompt": prompt,
        "attachments_sha256": canonical_attachments_sha256(images, files),
    }
    frame = {
        "type": "INPUT",
        "to": host,
        "session_id": sid,
        request_field: request_id,
        "prompt": prompt,
        "payload": payload,
        "from": _address(key),
    }
    if images is not None:
        frame["images"] = deepcopy(images)
    if files is not None:
        frame["files"] = deepcopy(files)
    if mode is not None:
        payload["mode"] = mode
        frame["mode"] = mode
    if session is not None:
        frame["session"] = deepcopy(session)
        payload["session_sha256"] = canonical_session_sha256(session)
    frame["signature"] = _sign(key, payload)
    return frame


def _auth_for(host):
    def authenticate(data, trust, **kwargs):
        return extract_and_authenticate(
            data,
            "open",
            recipient_address=host,
            blacklist=kwargs.get("blacklist"),
            whitelist=kwargs.get("whitelist"),
        )

    return authenticate


class TestBoundInputValidator:
    @pytest.mark.parametrize(
        ("mutate", "message"),
        [
            (lambda frame: frame.update(prompt="injected"), "prompt mismatch"),
            (lambda frame: frame.update(mode="safe"), "mode mismatch"),
            (lambda frame: frame.update(session_id="other"), "session_id mismatch"),
            (lambda frame: frame.update(input_id="other"), "input_id mismatch"),
            (lambda frame: frame.update(to=HOST_B), "recipient mismatch"),
            (lambda frame: frame.update(images=["changed"]), "attachments mismatch"),
            (lambda frame: frame.update(files=[{"name": "changed"}]), "attachments mismatch"),
        ],
    )
    def test_relay_visible_tampering_is_rejected(self, mutate, message):
        key = SigningKey.generate()
        frame = _input_frame(
            key,
            mode="ulw",
            images=["image"],
            files=[{"name": "a.txt", "data": "YQ=="}],
        )
        mutate(frame)

        binding, error = authenticate_bound_input(
            frame, recipient_address=HOST_A, expected_session_id=SID
        )

        assert binding is None
        assert message in error

    def test_signature_stripping_is_classified_as_unbound(self):
        frame = _input_frame(SigningKey.generate())
        frame.pop("signature")

        binding, error = authenticate_bound_input(
            frame, recipient_address=HOST_A, expected_session_id=SID
        )

        assert binding is None
        assert error is None

    def test_cross_host_and_cross_action_replay_are_rejected(self):
        key = SigningKey.generate()
        frame = _input_frame(key)

        assert "wrong recipient" in authenticate_bound_input(
            frame, recipient_address=HOST_B, expected_session_id=SID
        )[1]

        frame = _input_frame(key)
        frame["payload"]["action"] = "session.connect"
        frame["signature"] = _sign(key, frame["payload"])
        assert authenticate_bound_input(
            frame, recipient_address=HOST_A, expected_session_id=SID
        )[1] == "unauthorized: wrong signed action"


class TestRemoteAgentSigning:
    def test_direct_messages_bind_recipient_ids_attachments_and_session(self):
        agent = RemoteAgent(HOST_A, keys={"address": "0xowner"})
        agent._current_session = {"session_id": SID, "messages": []}

        with patch("connectonion.address.sign", return_value=b"x" * 64):
            connect = agent._build_connect_message(is_direct=True)
            request = agent._build_input_message(
                "hello",
                "input-1",
                is_direct=True,
                images=["image"],
                files=[{"name": "a"}],
                mode="safe",
                session_id=SID,
            )
            onboard = agent._build_onboard_submit({"invite_code": "code"})

        assert connect["to"] == HOST_A
        assert connect["payload"]["action"] == "session.connect"
        assert connect["payload"]["session_sha256"] == canonical_session_sha256(
            agent._current_session
        )
        assert request["to"] == request["payload"]["to"] == HOST_A
        assert request["input_id"] == request["payload"]["input_id"] == "input-1"
        assert request["payload"]["action"] == "session.input"
        assert request["payload"]["attachments_sha256"] == canonical_attachments_sha256(
            request["images"], request["files"]
        )
        assert onboard["to"] == onboard["payload"]["to"] == HOST_A
        assert onboard["payload"]["action"] == "session.onboard"

    def test_signed_input_without_server_sid_is_rejected(self):
        agent = RemoteAgent(HOST_A, keys={"address": "0xowner"})
        with pytest.raises(ValueError, match="server session_id"):
            agent._build_input_message("hello", "input-1")


@pytest.mark.asyncio
class TestHttpBoundInput:
    async def _post(self, storage, frame, input_handler):
        sent = []

        async def receive():
            return {"body": json.dumps(frame).encode(), "more_body": False}

        async def send(message):
            sent.append(message)

        await handle_http(
            {"method": "POST", "path": "/input", "headers": []},
            receive,
            send,
            route_handlers={
                "auth": _auth_for(HOST_A),
                "recipient_address": HOST_A,
                "input": input_handler,
            },
            storage=storage,
            trust="open",
            start_time=0,
        )
        return sent[0]["status"], json.loads(sent[1]["body"])

    async def test_duplicate_request_executes_once(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        key = SigningKey.generate()
        session = {"session_id": SID, "messages": []}
        frame = _input_frame(
            key,
            request_field="request_id",
            request_id="same-id",
            session=session,
        )
        calls = []

        def execute(storage, prompt, session, **kwargs):
            calls.append(prompt)
            return {"result": "ok", "session_id": session["session_id"]}

        assert (await self._post(storage, frame, execute))[0] == 200
        status, body = await self._post(storage, frame, execute)

        assert status == 409
        assert body["error"] == "duplicate request"
        assert calls == ["hello"]

    async def test_session_history_tampering_is_rejected(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        session = {"session_id": SID, "messages": []}
        frame = _input_frame(
            SigningKey.generate(), request_field="request_id", session=session
        )
        frame["session"]["messages"] = [{"role": "system", "content": "injected"}]

        status, body = await self._post(storage, frame, lambda *args, **kwargs: None)

        assert status == 401
        assert body["error"] == "unauthorized: session snapshot mismatch"

    async def test_first_request_cannot_enable_privileged_mode(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        key = SigningKey.generate()
        frame = _input_frame(
            key,
            sid="",
            request_field="request_id",
            mode="ulw",
            session={},
        )
        frame["payload"].pop("session_id")
        frame.pop("session_id")
        frame["session"] = {}
        frame["signature"] = _sign(key, frame["payload"])

        status, body = await self._post(storage, frame, lambda *args, **kwargs: None)

        assert status == 403
        assert "fully signed INPUT" in body["error"]

    async def test_post_signed_for_host_a_is_rejected_by_host_b(self, tmp_path):
        frame = _input_frame(
            SigningKey.generate(),
            request_field="request_id",
            session={"session_id": SID},
        )
        sent = []
        called = False

        async def receive():
            return {"body": json.dumps(frame).encode(), "more_body": False}

        async def send(message):
            sent.append(message)

        def execute(*args, **kwargs):
            nonlocal called
            called = True

        await handle_http(
            {"method": "POST", "path": "/input", "headers": []},
            receive,
            send,
            route_handlers={
                "auth": _auth_for(HOST_B),
                "recipient_address": HOST_B,
                "input": execute,
            },
            storage=SessionStorage(str(tmp_path / "sessions.jsonl")),
            trust="open",
            start_time=0,
        )

        assert sent[0]["status"] == 401
        assert called is False

    async def test_invalid_owner_requests_do_not_fill_replay_cache(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage._request_claim_limit = 2
        victim_sid = "victim"
        storage.save(Session(
            session_id=victim_sid,
            owner_address="0xanother-owner",
            status="done",
            prompt="prior",
            session={"session_id": victim_sid, "messages": []},
        ))

        class StubAgent:
            current_session = {}

            def input(self, prompt, *, session, images=None, files=None, mode=None):
                self.current_session = deepcopy(session)
                return "ok"

        def execute(storage, prompt, session, **kwargs):
            return input_handler(
                StubAgent,
                storage,
                prompt,
                3600,
                session=session,
                images=kwargs.get("images"),
                files=kwargs.get("files"),
                agent_address=kwargs.get("agent_address"),
                mode=kwargs.get("mode"),
                session_id_authenticated=kwargs.get("session_id_authenticated", False),
            )

        for request_id in ("invalid-1", "invalid-2"):
            frame = _input_frame(
                SigningKey.generate(),
                sid=victim_sid,
                request_field="request_id",
                request_id=request_id,
                session={"session_id": victim_sid, "messages": []},
            )
            status, body = await self._post(storage, frame, execute)
            assert status == 403
            assert body["error"] == "session owner mismatch"

        assert storage._request_claims == {}
        valid_frame = _input_frame(
            SigningKey.generate(),
            sid="valid",
            request_field="request_id",
            request_id="valid-request",
            session={"session_id": "valid", "messages": []},
        )
        status, body = await self._post(storage, valid_frame, execute)

        assert status == 200
        assert body["result"] == "ok"

    async def test_oversized_signed_post_session_id_is_clean_4xx(self, tmp_path):
        long_sid = "s" * 257
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        frame = _input_frame(
            SigningKey.generate(),
            sid=long_sid,
            request_field="request_id",
            session={"session_id": long_sid},
        )

        status, body = await self._post(
            storage,
            frame,
            lambda *args, **kwargs: pytest.fail("input must not execute"),
        )

        assert 400 <= status < 500
        assert "session_id" in body["error"]
        assert storage._request_claims == {}

    async def test_non_string_prompt_is_clean_400_and_remains_retryable(
        self, tmp_path
    ):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        key = SigningKey.generate()
        frame = _input_frame(
            key,
            request_field="request_id",
            request_id="retry-prompt",
            prompt={"not": "text"},
            session={"session_id": SID},
        )

        status, body = await self._post(
            storage,
            frame,
            lambda *args, **kwargs: pytest.fail("input must not execute"),
        )

        assert status == 400
        assert body["error"] == "prompt must be a non-empty string"
        assert storage.claim_request(
            _address(key), SID, "retry-prompt", now=time.time()
        )


class _RuntimeIO:
    def __init__(self):
        self.events = []

    def send_to_agent(self, event):
        self.events.append(deepcopy(event))

    def push_runtime_input(self, event):
        self.events.append(deepcopy(event))


@pytest.mark.asyncio
class TestWebSocketBoundInput:
    async def _run(self, tmp_path, frames, *, on_connected=None, ws_input=None):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        registry = ActiveSessionRegistry()
        incoming = iter(frames)
        sent = []

        async def recv():
            return next(incoming, None)

        async def send(message):
            sent.append(message)
            if message.get("type") == "CONNECTED" and on_connected:
                on_connected(registry, message)

        def default_input(storage, prompt, io, session, images, files, **kwargs):
            return {"result": "ok", "duration_ms": 1, "session": session}

        await run_ws_session(
            send,
            recv,
            route_handlers={
                "auth": _auth_for(HOST_A),
                "recipient_address": HOST_A,
                "trust_agent": object(),
                "ws_input": ws_input or default_input,
            },
            storage=storage,
            registry=registry,
            trust="open",
            enable_ping=False,
        )
        return storage, registry, sent

    async def _run_control_frame(self, tmp_path, frame):
        key = SigningKey.generate()

        class RunningIO(_RuntimeIO):
            def rewind_to(self, message_id):
                pass

            async def read_msgs_from_agent(self):
                await asyncio.Event().wait()
                yield  # pragma: no cover - cancellation ends the wait

        runtime = RunningIO()
        registry = ActiveSessionRegistry()
        registry.register(SID, runtime, threading.Thread(), _address(key))
        incoming = iter([_connect_frame(key), frame])
        sent = []

        async def recv():
            return next(incoming, None)

        async def send(message):
            sent.append(message)

        await run_ws_session(
            send,
            recv,
            route_handlers={
                "auth": _auth_for(HOST_A),
                "recipient_address": HOST_A,
                "trust_agent": object(),
            },
            storage=SessionStorage(str(tmp_path / "sessions.jsonl")),
            registry=registry,
            trust="open",
            enable_ping=False,
        )
        return runtime.events, sent

    async def test_duplicate_ws_request_executes_once(self, tmp_path):
        key = SigningKey.generate()
        request = _input_frame(key, request_id="same-id")
        calls = []

        def execute(storage, prompt, io, session, images, files, **kwargs):
            calls.append(prompt)
            return {"result": "ok", "duration_ms": 1, "session": session}

        _, _, sent = await self._run(
            tmp_path,
            [_connect_frame(key), request, deepcopy(request)],
            ws_input=execute,
        )

        assert calls == ["hello"]
        assert any(message.get("message") == "duplicate request" for message in sent)

    async def test_invalid_fresh_input_does_not_consume_request_id(self, tmp_path):
        key = SigningKey.generate()
        calls = []

        def execute(storage, prompt, io, session, images, files, **kwargs):
            calls.append(prompt)
            return {"result": "ok", "duration_ms": 1, "session": session}

        _, _, sent = await self._run(
            tmp_path,
            [
                _connect_frame(key),
                _input_frame(key, request_id="retry-id", prompt=""),
                _input_frame(key, request_id="retry-id", prompt="valid retry"),
            ],
            ws_input=execute,
        )

        assert calls == ["valid retry"]
        assert not any(message.get("message") == "duplicate request" for message in sent)

    async def test_unknown_mode_is_rejected_without_consuming_request_id(self, tmp_path):
        key = SigningKey.generate()
        calls = []

        def execute(storage, prompt, io, session, images, files, **kwargs):
            calls.append((prompt, kwargs.get("mode")))
            return {"result": "ok", "duration_ms": 1, "session": session}

        _, _, sent = await self._run(
            tmp_path,
            [
                _connect_frame(key),
                _input_frame(key, request_id="retry-id", mode="unknown"),
                _input_frame(
                    key,
                    request_id="retry-id",
                    prompt="valid retry",
                    mode="safe",
                ),
            ],
            ws_input=execute,
        )

        assert calls == [("valid retry", "safe")]
        assert any(message.get("message") == "unsupported mode" for message in sent)
        assert not any(message.get("message") == "duplicate request" for message in sent)

    async def test_non_string_prompt_does_not_reserve_or_consume_request(
        self, tmp_path
    ):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        registry = ActiveSessionRegistry()
        key = SigningKey.generate()
        owner = _address(key)
        registry.register(SID, object(), threading.Thread(), owner)
        registry.mark_session_connected(SID, owner)
        sent = []

        async def send(message):
            sent.append(message)

        result = await start_agent(
            _input_frame(
                key,
                request_id="retry-prompt",
                prompt={"not": "text"},
            ),
            send,
            {
                "authenticated": True,
                "agent_address": owner,
                "session_id": SID,
                "session_id_authenticated": True,
                "session_authenticated": True,
                "session": {"session_id": SID},
            },
            {
                "recipient_address": HOST_A,
                "ws_input": lambda *args, **kwargs: pytest.fail(
                    "input must not execute"
                ),
            },
            storage,
            registry,
        )

        assert result is None
        assert sent == [{
            "type": "ERROR",
            "message": "prompt must be a non-empty string",
        }]
        assert registry.get(SID).status == "connected"
        assert storage.claim_request(
            owner, SID, "retry-prompt", now=time.time()
        )

    @pytest.mark.parametrize("mode", ["safe", "ulw"])
    async def test_running_signed_input_is_retryable_without_delivery(
        self, tmp_path, mode
    ):
        key = SigningKey.generate()
        runtime = _RuntimeIO()

        def register_running(registry, message):
            registry.register(
                message["session_id"], runtime, threading.Thread(), _address(key)
            )

        storage, _, sent = await self._run(
            tmp_path,
            [_connect_frame(key), _input_frame(key, mode=mode)],
            on_connected=register_running,
        )

        assert runtime.events == []
        assert any(
            message.get("message")
            == "session is running; retry INPUT after current turn"
            and message.get("retryable") is True
            for message in sent
        )
        assert storage.claim_request(
            _address(key), SID, "request-1", now=time.time()
        )

    async def test_invalid_running_input_does_not_consume_request_id(self, tmp_path):
        key = SigningKey.generate()
        runtime = _RuntimeIO()

        def register_running(registry, message):
            registry.register(
                message["session_id"], runtime, threading.Thread(), _address(key)
            )

        storage, _, sent = await self._run(
            tmp_path,
            [
                _connect_frame(key),
                _input_frame(key, request_id="retry-id", prompt=""),
                _input_frame(key, request_id="retry-id", prompt="valid retry"),
            ],
            on_connected=register_running,
        )

        assert runtime.events == []
        assert storage.claim_request(
            _address(key), SID, "retry-id", now=time.time()
        )
        assert not any(message.get("message") == "duplicate request" for message in sent)

    @pytest.mark.parametrize(
        "frame",
        [
            {"type": "mode_change", "mode": "ulw"},
            {"type": "mode_change", "mode": "accept_edits"},
            {"type": "prompt_update", "prompt": "replace the goal"},
            {"action": "continue", "turns": 100},
            {"action": "switch_mode", "mode": "ulw"},
            {"action": "switch_mode", "mode": "accept_edits"},
        ],
    )
    async def test_raw_control_frame_cannot_grant_capabilities_or_intent(
        self, tmp_path, frame
    ):
        events, sent = await self._run_control_frame(tmp_path, frame)

        assert events == []
        assert any(
            message.get("message")
            == "signed INPUT or authenticated control protocol required"
            for message in sent
        )

    @pytest.mark.parametrize(
        "frame",
        [
            {"type": "mode_change", "mode": []},
            {"action": "switch_mode", "mode": {}},
        ],
    )
    async def test_malformed_raw_mode_control_returns_clean_error(
        self, tmp_path, frame
    ):
        events, sent = await self._run_control_frame(tmp_path, frame)

        assert events == []
        assert any(
            message.get("type") == "ERROR"
            and message.get("message") == "mode must be a string"
            for message in sent
        )

    @pytest.mark.parametrize(
        "frame",
        [
            {"type": "INTERRUPT"},
            {"type": "mode_change", "mode": "safe"},
            {"type": "mode_change", "mode": "plan"},
            {"type": "APPROVAL_RESPONSE", "approved": False},
            {"type": "ASK_USER_RESPONSE", "answer": "ordinary answer"},
            {"action": "stop"},
            {"action": "switch_mode", "mode": "safe"},
            {"action": "switch_mode", "mode": "plan"},
        ],
    )
    async def test_existing_interactive_controls_remain_compatible(
        self, tmp_path, frame
    ):
        events, sent = await self._run_control_frame(tmp_path, frame)

        assert events == [frame]
        assert not any(message.get("type") == "ERROR" for message in sent)

    async def test_legacy_socket_keeps_live_raw_mode_compatibility(self, tmp_path):
        key = SigningKey.generate()
        payload = {"timestamp": time.time()}
        connect = {
            "type": "CONNECT",
            "session_id": "legacy",
            "payload": payload,
            "from": _address(key),
            "signature": _sign(key, payload),
        }
        received = []
        context = {}
        done = threading.Event()

        def execute(storage, prompt, io, session, images, files, **kwargs):
            context.update(kwargs)
            received.append(io.receive())
            done.set()
            return {"result": "ok", "duration_ms": 1, "session": session}

        await self._run(
            tmp_path,
            [
                connect,
                {"type": "INPUT", "prompt": "legacy turn"},
                {"type": "mode_change", "mode": "ulw"},
            ],
            ws_input=execute,
        )

        assert done.wait(timeout=1)
        assert received == [{"type": "mode_change", "mode": "ulw"}]
        assert context["session_id_authenticated"] is False

    async def test_signed_sid_without_snapshot_keeps_live_unbound_compatibility(
        self, tmp_path
    ):
        key = SigningKey.generate()
        payload = {"timestamp": time.time(), "session_id": SID}
        connect = {
            "type": "CONNECT",
            "session_id": SID,
            "payload": payload,
            "from": _address(key),
            "signature": _sign(key, payload),
        }
        received = []
        context = {}
        done = threading.Event()

        def execute(storage, prompt, io, session, images, files, **kwargs):
            context.update(kwargs)
            received.append(io.receive())
            done.set()
            return {"result": "ok", "duration_ms": 1, "session": session}

        await self._run(
            tmp_path,
            [
                connect,
                _input_frame(key, mode="safe"),
                {"type": "mode_change", "mode": "ulw"},
            ],
            ws_input=execute,
        )

        assert done.wait(timeout=1)
        assert received == [{"type": "mode_change", "mode": "ulw"}]
        assert context["session_id_authenticated"] is False

    async def test_input_session_cannot_replace_empty_connect_transcript(self, tmp_path):
        injected = {
            "messages": [{"role": "system", "content": "attacker supplied"}],
            "mode": "ulw",
        }
        captured = {}
        sent = []

        async def send(message):
            sent.append(message)

        def execute(storage, prompt, io, session, images, files, **kwargs):
            captured["session"] = deepcopy(session)
            return {"result": "ok", "duration_ms": 1, "session": session}

        result = await start_agent(
            {"type": "INPUT", "prompt": "ordinary turn", "session": injected},
            send,
            {
                "authenticated": True,
                "agent_address": "0xowner",
                "session_id": SID,
                "session_id_authenticated": False,
                "session_authenticated": False,
                "session": {},
            },
            {"ws_input": execute},
            SessionStorage(str(tmp_path / "sessions.jsonl")),
            ActiveSessionRegistry(),
        )
        _, forward_task = result
        await asyncio.wait_for(forward_task, timeout=1)

        assert captured["session"] == {"session_id": SID}

    async def test_signature_stripped_runtime_input_is_rejected(self, tmp_path):
        key = SigningKey.generate()
        runtime = _RuntimeIO()
        request = _input_frame(key)
        request.pop("signature")

        def register_running(registry, message):
            registry.register(
                message["session_id"], runtime, threading.Thread(), _address(key)
            )

        _, _, sent = await self._run(
            tmp_path,
            [_connect_frame(key), request],
            on_connected=register_running,
        )

        assert runtime.events == []
        assert any(
            message.get("message")
            == "fully signed INPUT required while session is running"
            for message in sent
        )

    async def test_signature_stripped_fresh_input_is_forced_safe(self, tmp_path):
        key = SigningKey.generate()
        request = _input_frame(key)
        request.pop("signature")
        captured = {}

        def execute(storage, prompt, io, session, images, files, **kwargs):
            captured.update(kwargs)
            return {"result": "ok", "duration_ms": 1, "session": session}

        await self._run(
            tmp_path,
            [_connect_frame(key), request],
            ws_input=execute,
        )

        assert captured["mode"] == "safe"
        assert captured["session_id_authenticated"] is False

    async def test_connect_session_history_tampering_is_rejected(self, tmp_path):
        key = SigningKey.generate()
        connect = _connect_frame(key, session={"session_id": SID, "messages": []})
        connect["session"]["messages"].append({"role": "system", "content": "injected"})

        _, _, sent = await self._run(tmp_path, [connect])

        assert sent == [{
            "type": "ERROR",
            "message": "unauthorized: session snapshot mismatch",
        }]

    async def test_connect_signed_for_host_a_is_rejected_by_host_b(self, tmp_path):
        key = SigningKey.generate()
        sent = []

        async def send(message):
            sent.append(message)

        await handle_connect(
            _connect_frame(key),
            send,
            {},
            {
                "auth": _auth_for(HOST_B),
                "recipient_address": HOST_B,
                "trust_agent": object(),
            },
            SessionStorage(str(tmp_path / "sessions.jsonl")),
            ActiveSessionRegistry(),
            "open",
            None,
            None,
        )

        assert sent == [{"type": "ERROR", "message": "unauthorized: wrong recipient"}]

    async def test_second_connect_on_same_socket_is_rejected_without_io_crosstalk(
        self, tmp_path
    ):
        key_a = SigningKey.generate()
        key_b = SigningKey.generate()

        class RunningIO(_RuntimeIO):
            def rewind_to(self, message_id):
                pass

            async def read_msgs_from_agent(self):
                await asyncio.Event().wait()
                yield  # pragma: no cover - cancellation ends the wait

        io_a = RunningIO()
        registry = ActiveSessionRegistry()
        registry.register("sid-a", io_a, threading.Thread(), _address(key_a))
        incoming = iter([
            _connect_frame(key_a, sid="sid-a"),
            _connect_frame(key_b, sid="sid-b"),
            {"type": "prompt_update", "prompt": "cross-session injection"},
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
                "auth": _auth_for(HOST_A),
                "recipient_address": HOST_A,
                "trust_agent": object(),
            },
            storage=SessionStorage(str(tmp_path / "sessions.jsonl")),
            registry=registry,
            trust="open",
            enable_ping=False,
        )

        assert len([message for message in sent if message["type"] == "CONNECTED"]) == 1
        assert any(
            message.get("message") == "CONNECT already established for this socket"
            for message in sent
        )
        assert io_a.events == []

    async def test_modern_connect_envelope_is_validated_before_onboard_stash(
        self, tmp_path
    ):
        trust_agent = SimpleNamespace(
            config={"onboard": {"invite_code": ["code"]}},
            get_self_address=lambda: HOST_A,
        )
        frame = _connect_frame(SigningKey.generate())
        frame["payload"]["action"] = "session.input"
        sent = []
        conn = {}

        async def send(message):
            sent.append(message)

        await handle_connect(
            frame,
            send,
            conn,
            {
                "auth": lambda *args, **kwargs: (
                    None,
                    frame["from"],
                    True,
                    "forbidden: onboarding required",
                ),
                "recipient_address": HOST_A,
                "trust_agent": trust_agent,
            },
            SessionStorage(str(tmp_path / "sessions.jsonl")),
            ActiveSessionRegistry(),
            "careful",
            None,
            None,
        )

        assert sent == [{
            "type": "ERROR",
            "message": "unauthorized: wrong signed action",
        }]
        assert "pending_connect" not in conn

    async def test_onboard_signer_cannot_resume_another_identity_connect(
        self, tmp_path
    ):
        trust_agent = SimpleNamespace(
            config={"onboard": {"invite_code": ["code"]}},
            get_self_address=lambda: HOST_A,
            is_blocked=lambda address: False,
            verify_invite=lambda address, code: True,
            get_level=lambda address: "contact",
        )
        incoming = iter([
            {
                "type": "CONNECT",
                "session_id": SID,
                "payload": {"timestamp": time.time()},
                "from": "0xidentity-a",
                "signature": "0xsig-a",
            },
            {
                "type": "ONBOARD_SUBMIT",
                "payload": {"invite_code": "code"},
                "from": "0xidentity-b",
                "signature": "0xsig-b",
            },
        ])
        sent = []

        async def recv():
            return next(incoming, None)

        async def send(message):
            sent.append(message)

        def authenticate(data, trust, **kwargs):
            if data.get("type") == "CONNECT":
                return None, "0xidentity-a", True, "forbidden: onboarding required"
            return None, "0xidentity-b", True, None

        await run_ws_session(
            send,
            recv,
            route_handlers={
                "auth": authenticate,
                "trust_agent": trust_agent,
            },
            storage=SessionStorage(str(tmp_path / "sessions.jsonl")),
            registry=ActiveSessionRegistry(),
            trust="careful",
            enable_ping=False,
        )

        assert any(message.get("type") == "ONBOARD_REQUIRED" for message in sent)
        assert not any(message.get("type") == "ONBOARD_SUCCESS" for message in sent)
        assert any(
            message.get("message") == "unauthorized: onboarding identity mismatch"
            for message in sent
        )
        assert not any(message.get("type") == "CONNECTED" for message in sent)


@pytest.mark.asyncio
async def test_connect_storage_read_does_not_block_event_loop():
    started = threading.Event()
    release = threading.Event()

    class BlockingStorage:
        def get(self, session_id):
            started.set()
            release.wait(timeout=1)
            return None

    class Registry:
        def get(self, session_id):
            return None

    sent = []

    async def send(message):
        sent.append(message)

    task = asyncio.create_task(establish_connection(
        {
            "type": "CONNECT",
            "session_id": SID,
            "session": {"session_id": SID},
            "payload": {
                "session_id": SID,
                "session_sha256": canonical_session_sha256({"session_id": SID}),
            },
        },
        "0xowner",
        send,
        {},
        BlockingStorage(),
        Registry(),
    ))
    try:
        await asyncio.wait_for(asyncio.to_thread(started.wait, 0.5), timeout=0.6)
        await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.1)
    finally:
        release.set()
    await asyncio.wait_for(task, timeout=1)
    assert sent[0]["type"] == "CONNECTED"


@pytest.mark.asyncio
async def test_http_session_read_does_not_block_event_loop(monkeypatch):
    monkeypatch.setenv("OPENONION_API_KEY", "admin-key")
    started = threading.Event()
    release = threading.Event()
    sent = []

    def blocking_session(storage, session_id, owner_address, *, is_admin):
        started.set()
        release.wait(timeout=1)
        return {"session_id": session_id}

    async def receive():
        return {"body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    task = asyncio.create_task(handle_http(
        {
            "method": "GET",
            "path": f"/sessions/{SID}",
            "headers": [(b"authorization", b"Bearer admin-key")],
        },
        receive,
        send,
        route_handlers={"session": blocking_session},
        storage=object(),
        trust="open",
        start_time=0,
    ))
    try:
        await asyncio.wait_for(asyncio.to_thread(started.wait, 0.5), timeout=0.6)
        await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.1)
    finally:
        release.set()
    await asyncio.wait_for(task, timeout=1)
    assert sent[0]["status"] == 200


@pytest.mark.asyncio
async def test_resume_forwarding_surfaces_owner_bound_stored_error(tmp_path):
    class FinishedIO:
        async def read_msgs_from_agent(self):
            if False:
                yield  # pragma: no cover - makes this an async generator

    storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
    storage.save(Session(
        session_id=SID,
        owner_address="0xowner",
        status="error",
        prompt="failed turn",
        result="agent failed",
        session={"session_id": SID},
    ))
    sent = []

    async def send(message):
        sent.append(message)

    await forward_agent_msgs_to_client(
        send,
        FinishedIO(),
        SID,
        storage=storage,
        owner_address="0xowner",
    )

    assert sent == [{
        "type": "ERROR",
        "message": "agent failed",
        "session_id": SID,
    }]


@pytest.mark.asyncio
async def test_resume_forwarding_hides_other_owner_state_behind_generic_error(tmp_path):
    class FinishedIO:
        async def read_msgs_from_agent(self):
            if False:
                yield  # pragma: no cover - makes this an async generator

    storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
    storage.save(Session(
        session_id=SID,
        owner_address="0xowner",
        status="error",
        prompt="failed turn",
        result="private failure",
        session={"session_id": SID},
    ))
    sent = []

    async def send(message):
        sent.append(message)

    await forward_agent_msgs_to_client(
        send,
        FinishedIO(),
        SID,
        storage=storage,
        owner_address="0xother-owner",
    )

    assert sent == [{
        "type": "ERROR",
        "message": "Session result unavailable",
        "session_id": SID,
    }]


@pytest.mark.asyncio
async def test_resume_forwarding_missing_storage_returns_generic_error(tmp_path):
    class FinishedIO:
        async def read_msgs_from_agent(self):
            if False:
                yield  # pragma: no cover - makes this an async generator

    sent = []

    async def send(message):
        sent.append(message)

    await forward_agent_msgs_to_client(
        send,
        FinishedIO(),
        SID,
        storage=SessionStorage(str(tmp_path / "sessions.jsonl")),
        owner_address="0xowner",
    )

    assert sent == [{
        "type": "ERROR",
        "message": "Session result unavailable",
        "session_id": SID,
    }]


@pytest.mark.asyncio
@pytest.mark.parametrize("request_kind", ["post", "get"])
async def test_http_authentication_does_not_block_event_loop(request_kind):
    started = threading.Event()
    release = threading.Event()
    safety_release = threading.Timer(0.5, release.set)
    sent = []

    def blocking_auth(data, trust, **kwargs):
        started.set()
        release.wait(timeout=1)
        return data.get("payload", {}).get("prompt", ""), "0xowner", True, None

    async def receive():
        body = b""
        if request_kind == "post":
            body = json.dumps({
                "payload": {"prompt": "hello", "timestamp": time.time()},
                "from": "0xowner",
                "signature": "legacy",
                "session": {"session_id": SID},
            }).encode()
        return {"body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    if request_kind == "post":
        scope = {"method": "POST", "path": "/input", "headers": []}
        route_handlers = {
            "auth": blocking_auth,
            "recipient_address": HOST_A,
            "input": lambda storage, prompt, session, **kwargs: {
                "session_id": session["session_id"],
                "result": "ok",
            },
        }
    else:
        scope = {
            "method": "GET",
            "path": "/sessions",
            "headers": [
                (b"x-from", b"0xowner"),
                (b"x-signature", b"signature"),
                (b"x-timestamp", str(time.time()).encode()),
            ],
        }
        route_handlers = {
            "auth": blocking_auth,
            "recipient_address": HOST_A,
            "sessions": lambda *args, **kwargs: {"sessions": []},
        }

    task = asyncio.create_task(handle_http(
        scope,
        receive,
        send,
        route_handlers=route_handlers,
        storage=object(),
        trust="open",
        start_time=0,
    ))
    safety_release.start()
    start = time.monotonic()
    try:
        await asyncio.sleep(0.02)
        elapsed = time.monotonic() - start
        assert started.is_set()
        assert elapsed < 0.2
    finally:
        release.set()
        safety_release.cancel()
    await asyncio.wait_for(task, timeout=1)
    assert sent[0]["status"] == 200


@pytest.mark.asyncio
async def test_get_signature_cannot_replay_across_hosts():
    key = SigningKey.generate()
    timestamp = time.time()
    payload = {"action": "session.list", "timestamp": timestamp, "to": HOST_A}
    headers = [
        (b"x-from", _address(key).encode()),
        (b"x-signature", _sign(key, payload).encode()),
        (b"x-timestamp", str(timestamp).encode()),
    ]
    sent = []

    async def receive():
        return {"body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await handle_http(
        {"method": "GET", "path": "/sessions", "headers": headers},
        receive,
        send,
        route_handlers={
            "auth": _auth_for(HOST_B),
            "recipient_address": HOST_B,
            "sessions": lambda *args, **kwargs: {"sessions": []},
        },
        storage=object(),
        trust="open",
        start_time=0,
    )

    assert sent[0]["status"] == 401
    assert json.loads(sent[1]["body"])["error"] == "unauthorized: invalid signature"


@pytest.mark.asyncio
async def test_oversized_signed_get_session_id_is_clean_4xx():
    long_sid = "s" * 257
    sent = []

    async def receive():
        return {"body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await handle_http(
        {
            "method": "GET",
            "path": f"/sessions/{long_sid}",
            "headers": [
                (b"x-from", b"0xowner"),
                (b"x-signature", b"signature"),
                (b"x-timestamp", str(time.time()).encode()),
            ],
        },
        receive,
        send,
        route_handlers={
            "auth": lambda *args, **kwargs: pytest.fail("auth must not execute"),
            "recipient_address": HOST_A,
            "session": lambda *args, **kwargs: pytest.fail("read must not execute"),
        },
        storage=object(),
        trust="open",
        start_time=0,
    )

    assert sent[0]["status"] == 400
    assert "session_id" in json.loads(sent[1]["body"])["error"]


@pytest.mark.asyncio
async def test_agent_exception_marks_registry_connected(tmp_path):
    storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
    registry = ActiveSessionRegistry()
    sent = []

    async def send(message):
        sent.append(message)

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    result = await start_agent(
        {"type": "INPUT", "prompt": "safe legacy"},
        send,
        {
            "authenticated": True,
            "agent_address": "0xowner",
            "session_id": SID,
            "session_id_authenticated": False,
            "session_authenticated": False,
            "session": {"session_id": SID},
        },
        {"ws_input": explode},
        storage,
        registry,
    )
    _, forward_task = result
    await asyncio.wait_for(forward_task, timeout=1)

    assert registry.get_for_owner(SID, "0xowner").status == "connected"
    assert any(message.get("message") == "boom" for message in sent)
