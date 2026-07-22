"""Focused regressions for hosted-session lifecycle security."""

import asyncio
import gc
import json
import threading
import time
from unittest.mock import patch
from uuid import uuid4

import pytest
from nacl.signing import SigningKey

from connectonion.network.host import server
from connectonion.network.host.auth import canonical_attachments_sha256
from connectonion.network.host.session import (
    ActiveSessionRegistry,
    Session,
    SessionStorage,
    narrow_server_state,
)
from connectonion.network.host.ws_router.agent_io import start_agent
from connectonion.network.trust import TrustAgent


def _lease(generation, turns, used):
    lease = {"turns": turns, "turns_used": used}
    if generation is not None:
        lease["generation"] = generation
    return {"mode": "ulw", "ulw": lease}


def _signed(payload):
    key = SigningKey.generate()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "payload": payload,
        "from": "0x" + key.verify_key.encode().hex(),
        "signature": "0x" + key.sign(canonical.encode()).signature.hex(),
    }


class TestLeaseGenerations:
    @pytest.mark.parametrize("mode", [[], {}])
    def test_unhashable_persisted_mode_fails_closed(self, mode):
        assert narrow_server_state({"mode": mode}) == {}

    def test_same_generation_is_monotonic(self):
        generation = uuid4().hex
        previous = _lease(generation, 100, 20)
        incoming = _lease(generation, 80, 5)

        merged = narrow_server_state(incoming, previous)

        assert merged["ulw"] == {
            "generation": generation,
            "turns": 100,
            "turns_used": 20,
        }

    def test_new_generation_replaces_exhausted_lease(self):
        previous = _lease(uuid4().hex, 1000, 1000)
        generation = uuid4().hex
        incoming = _lease(generation, 100, 0)

        merged = narrow_server_state(incoming, previous)

        assert merged["ulw"] == {
            "generation": generation,
            "turns": 100,
            "turns_used": 0,
        }

    def test_malformed_generation_fails_closed(self):
        state = _lease("not-a-uuid", 100, 0)

        assert narrow_server_state(state) == {"mode": "safe"}

    def test_legacy_lease_remains_compatible_and_can_migrate(self):
        legacy = _lease(None, 100, 9)
        assert narrow_server_state(_lease(None, 80, 2), legacy)["ulw"] == {
            "turns": 100,
            "turns_used": 9,
        }

        generation = uuid4().hex
        migrated = narrow_server_state(_lease(generation, 50, 0), legacy)
        assert migrated["ulw"]["generation"] == generation
        assert migrated["ulw"]["turns_used"] == 0

    def test_legacy_writer_cannot_erase_generated_lease(self):
        generation = uuid4().hex
        previous = _lease(generation, 100, 12)

        assert narrow_server_state(_lease(None, 100, 1), previous) == previous


class TestRequestClaims:
    def test_request_id_is_once_only_and_bound_to_sid(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        assert storage.claim_request("owner", "sid-a", "request", now=10)
        assert not storage.claim_request("owner", "sid-a", "request", now=11)
        assert not storage.claim_request("owner", "sid-b", "request", now=11)
        assert storage.claim_request("other", "sid-b", "request", now=11)

    def test_expired_request_id_can_be_claimed_again(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        assert storage.claim_request("owner", "sid-a", "request", now=10)
        assert not storage.claim_request("owner", "sid-b", "request", now=310)
        assert storage.claim_request("owner", "sid-b", "request", now=310.001)

    def test_future_timestamp_covers_full_signature_window(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        assert storage.claim_request("owner", "sid", "request", 299, now=0)
        assert not storage.claim_request("owner", "sid", "request", now=598)
        assert not storage.claim_request("owner", "sid", "request", now=599)
        assert storage.claim_request("owner", "sid", "request", now=599.001)

    def test_full_cache_fails_closed_without_evicting_live_claims(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage._request_claim_limit = 1
        assert storage.claim_request("owner", "sid", "first", now=0)

        with pytest.raises(ValueError, match="cache is full"):
            storage.claim_request("owner", "sid", "second", now=1)
        assert not storage.claim_request("owner", "sid", "first", now=1)

    def test_request_claim_validates_binding_fields(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        with pytest.raises(ValueError, match="non-empty string"):
            storage.claim_request("owner", "", "request")
        with pytest.raises(ValueError, match="too long"):
            storage.claim_request("owner", "sid", "x" * 129)

    def test_long_session_id_is_rejected_before_lock_or_file_scan(self, tmp_path):
        path = tmp_path / "sessions.jsonl"
        path.write_text("not valid json\n")
        storage = SessionStorage(str(path))
        long_session_id = "s" * 257

        with pytest.raises(ValueError, match="session_id is too long"):
            with storage.session_lock(long_session_id):
                pass
        assert len(storage._session_locks) == 0

        with pytest.raises(ValueError, match="session_id is too long"):
            storage.get(long_session_id)
        assert len(storage._session_locks) == 0

        record = Session(
            session_id=long_session_id,
            status="complete",
            prompt="",
        )
        with pytest.raises(ValueError, match="session_id is too long"):
            storage.save(record)
        assert path.read_text() == "not valid json\n"

        with pytest.raises(ValueError, match="session_id is too long"):
            storage.claim_request("owner", long_session_id, "request")

    def test_idle_session_locks_are_weak(self, tmp_path):
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))

        with storage.session_lock("temporary"):
            assert len(storage._session_locks) == 1
        gc.collect()

        assert len(storage._session_locks) == 0


class TestActiveCleanup:
    def test_cleanup_preserves_live_running_thread(self):
        release = threading.Event()
        thread = threading.Thread(target=release.wait)
        thread.start()
        registry = ActiveSessionRegistry()
        registry.register("sid", object(), thread, "owner")
        registry.get("sid").last_ping = time.time() - 3601

        try:
            assert registry.cleanup_expired() == 0
            assert registry.get("sid") is not None
        finally:
            release.set()
            thread.join(timeout=1)

        assert registry.cleanup_expired() == 1
        assert registry.get("sid") is None


@pytest.mark.asyncio
class TestActiveTurnTransitions:
    async def test_two_sockets_can_start_only_one_turn(self, tmp_path):
        key = SigningKey.generate()
        owner = "0x" + key.verify_key.encode().hex()
        target = "0xhost"
        storage = SessionStorage(str(tmp_path / "sessions.jsonl"))
        storage.save(Session(
            session_id="sid",
            owner_address=owner,
            status="done",
            prompt="prior",
            session={"session_id": "sid", "messages": []},
        ))
        registry = ActiveSessionRegistry()
        registry.register("sid", object(), threading.Thread(), owner)
        registry.mark_session_connected("sid", owner)
        release = threading.Event()
        started = []
        started_lock = threading.Lock()

        def ws_input(storage, prompt, io, session, images, files, **kwargs):
            with started_lock:
                started.append(prompt)
            release.wait(timeout=1)
            return {"result": "ok", "duration_ms": 1, "session": session}

        def frame(prompt, request_id):
            payload = {
                "action": "session.input",
                "to": target,
                "timestamp": time.time(),
                "session_id": "sid",
                "input_id": request_id,
                "prompt": prompt,
                "attachments_sha256": canonical_attachments_sha256(),
                "mode": "safe",
            }
            canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            return {
                "type": "INPUT",
                "to": target,
                "session_id": "sid",
                "input_id": request_id,
                "prompt": prompt,
                "mode": "safe",
                "payload": payload,
                "from": owner,
                "signature": "0x" + key.sign(canonical.encode()).signature.hex(),
            }

        async def launch(prompt, request_id):
            sent = []

            async def send(message):
                sent.append(message)

            result = await start_agent(
                frame(prompt, request_id),
                send,
                {
                    "authenticated": True,
                    "agent_address": owner,
                    "session_id": "sid",
                    "session_id_authenticated": True,
                    "session_authenticated": True,
                    "session": {"session_id": "sid"},
                },
                {"ws_input": ws_input, "recipient_address": target},
                storage,
                registry,
            )
            return request_id, result, sent

        first, second = await asyncio.gather(
            launch("first", "request-first"),
            launch("second", "request-second"),
        )
        winners = [item for item in (first, second) if item[1] is not None]
        losers = [item for item in (first, second) if item[1] is None]
        release.set()
        for _, result, _ in winners:
            await asyncio.wait_for(result[1], timeout=1)

        assert len(winners) == 1
        assert len(losers) == 1
        assert len(started) == 1
        assert any(
            message.get("message") == "session already running"
            for message in losers[0][2]
        )
        assert storage.claim_request(owner, "sid", losers[0][0], now=time.time())

    async def test_cleanup_between_preflight_and_transition_never_starts_thread(
        self, tmp_path
    ):
        registry = ActiveSessionRegistry()
        registry.register("sid", object(), threading.Thread(), "owner")
        registry.mark_session_connected("sid", "owner")
        registry.get("sid").last_ping = time.time() - 601
        called = False
        sent = []

        class CleanupStorage:
            def get(self, session_id):
                assert registry.cleanup_expired() == 1
                return None

        async def send(message):
            sent.append(message)

        def ws_input(*args, **kwargs):
            nonlocal called
            called = True

        result = await start_agent(
            {"type": "INPUT", "prompt": "race"},
            send,
            {
                "authenticated": True,
                "agent_address": "owner",
                "session_id": "sid",
                "session_id_authenticated": False,
                "session_authenticated": False,
                "session": {"session_id": "sid"},
            },
            {"ws_input": ws_input},
            CleanupStorage(),
            registry,
        )

        assert result is None
        assert called is False
        assert sent[-1]["message"] == "session is not active"

    async def test_stale_thread_completion_cannot_finish_new_generation(self):
        registry = ActiveSessionRegistry()
        old_thread = threading.Thread()
        new_thread = threading.Thread()
        registry.register("sid", object(), old_thread, "owner")
        registry.mark_session_connected(
            "sid", "owner", expected_thread=old_thread
        )
        registry.mark_session_running("sid", object(), new_thread, "owner")

        assert not registry.mark_session_connected(
            "sid", "owner", expected_thread=old_thread
        )
        assert registry.get("sid").status == "running"
        assert registry.mark_session_connected(
            "sid", "owner", expected_thread=new_thread
        )
        assert registry.get("sid").status == "connected"


class TestServerBoundaries:
    def test_route_auth_is_bound_to_recipient(self):
        handlers = server._create_route_handlers(
            lambda: None,
            {"name": "host", "address": "0xhost"},
            3600,
            TrustAgent("open"),
            {},
        )
        data = _signed({"to": "0xother", "timestamp": time.time()})

        assert handlers["auth"](data, TrustAgent("open"))[3] == (
            "unauthorized: wrong recipient"
        )

    def test_host_rejects_multiple_workers_before_startup(self, tmp_path):
        config = {
            "port": 8000,
            "trust": "open",
            "result_ttl": 60,
            "workers": 2,
            "reload": False,
            "relay_url": None,
            "summary": None,
            "examples": None,
        }

        with patch.object(server, "load_host_config", return_value=config):
            with pytest.raises(ValueError, match="workers=1"):
                server.host(lambda: None, co_dir=tmp_path, relay_url=None)
