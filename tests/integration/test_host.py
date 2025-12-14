"""
Tests for host() HTTP endpoints.

Based on docs/network/host.md specification.
"""

import asyncio
import json
import time
import pytest
from unittest.mock import MagicMock


# === Simple ASGI Test Client ===

class ASGITestClient:
    """Minimal ASGI test client - no external dependencies."""

    def __init__(self, app):
        self.app = app

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def get(self, path: str) -> "Response":
        return self._run(self._request("GET", path))

    def post(self, path: str, json_data: dict = None) -> "Response":
        return self._run(self._request("POST", path, json_data))

    async def _request(self, method: str, path: str, body: dict = None) -> "Response":
        scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [[b"content-type", b"application/json"]],
        }

        body_bytes = json.dumps(body).encode() if body else b""
        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return {"type": "http.disconnect"}

        response = Response()

        async def send(message):
            if message["type"] == "http.response.start":
                response.status_code = message["status"]
            elif message["type"] == "http.response.body":
                response.body = message.get("body", b"")

        await self.app(scope, receive, send)
        return response


class Response:
    """Simple response container."""

    def __init__(self):
        self.status_code = 0
        self.body = b""

    def json(self):
        return json.loads(self.body.decode())


# === Tests ===

class TestHostEndpoints:
    """Test HTTP endpoints for host()."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing."""
        agent = MagicMock()
        agent.name = "test-agent"
        agent.tools = MagicMock()
        agent.tools.list_names = MagicMock(return_value=["tool1", "tool2"])
        agent.input = MagicMock(return_value="Hello response")
        agent.current_session = {"messages": [], "trace": [], "turn": 1}
        return agent

    @pytest.fixture
    def app(self, mock_agent, tmp_path):
        """Create test ASGI app."""
        from connectonion.host import create_app, SessionStorage

        storage = SessionStorage(str(tmp_path / ".co" / "session_results.jsonl"))
        return create_app(agent=mock_agent, storage=storage, trust="open", result_ttl=3600)

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return ASGITestClient(app)

    # === POST /input tests ===

    def test_post_input_creates_session(self, client):
        """POST /input should create session and return session_id."""
        response = client.post("/input", json_data={"prompt": "Hello"})

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "done"

    def test_post_input_returns_result(self, client, mock_agent):
        """POST /input should include result."""
        mock_agent.input.return_value = "Quick response"

        response = client.post("/input", json_data={"prompt": "Hello"})

        data = response.json()
        assert data["status"] == "done"
        assert data["result"] == "Quick response"

    def test_post_input_returns_duration_ms(self, client):
        """POST /input should include duration_ms."""
        response = client.post("/input", json_data={"prompt": "Hello"})

        data = response.json()
        assert "duration_ms" in data
        assert isinstance(data["duration_ms"], int)

    def test_post_input_full_uuid(self, client):
        """POST /input should return full UUID session_id."""
        response = client.post("/input", json_data={"prompt": "Hello"})

        session_id = response.json()["session_id"]
        # Full UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert len(session_id) == 36
        assert session_id.count("-") == 4

    def test_post_input_invalid_json(self, client):
        """POST /input should return 400 for invalid JSON."""
        # Send invalid JSON by directly calling with malformed data
        async def test():
            scope = {"type": "http", "method": "POST", "path": "/input",
                    "query_string": b"", "headers": []}
            body_sent = False

            async def receive():
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": b"not valid json", "more_body": False}
                return {"type": "http.disconnect"}

            response = Response()

            async def send(message):
                if message["type"] == "http.response.start":
                    response.status_code = message["status"]
                elif message["type"] == "http.response.body":
                    response.body = message.get("body", b"")

            await client.app(scope, receive, send)
            return response

        response = asyncio.get_event_loop().run_until_complete(test())
        assert response.status_code == 400

    # === GET /sessions/{session_id} tests ===

    def test_get_session_by_id(self, client):
        """GET /sessions/{session_id} should return session."""
        create_response = client.post("/input", json_data={"prompt": "Hello"})
        session_id = create_response.json()["session_id"]

        response = client.get(f"/sessions/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

    def test_get_session_partial_id_not_allowed(self, client):
        """GET /sessions/{session_id} should NOT match partial ID (security fix)."""
        create_response = client.post("/input", json_data={"prompt": "Hello"})
        session_id = create_response.json()["session_id"]
        partial_id = session_id[:8]

        response = client.get(f"/sessions/{partial_id}")

        # Partial ID should return 404 - exact match required
        assert response.status_code == 404

    def test_get_session_not_found(self, client):
        """GET /sessions/{session_id} should return 404 for unknown session."""
        response = client.get("/sessions/nonexistent")

        assert response.status_code == 404

    def test_get_session_includes_expires(self, client):
        """GET /sessions/{session_id} should include expires field."""
        create_response = client.post("/input", json_data={"prompt": "Hello"})
        session_id = create_response.json()["session_id"]

        response = client.get(f"/sessions/{session_id}")

        data = response.json()
        assert "expires" in data
        assert data["expires"] > time.time()  # Should be in the future

    def test_get_session_includes_duration_ms(self, client):
        """GET /sessions/{session_id} should include duration_ms for done sessions."""
        create_response = client.post("/input", json_data={"prompt": "Hello"})
        session_id = create_response.json()["session_id"]

        response = client.get(f"/sessions/{session_id}")

        data = response.json()
        assert "duration_ms" in data

    # === GET /sessions tests ===

    def test_get_sessions_list(self, client):
        """GET /sessions should list all sessions."""
        client.post("/input", json_data={"prompt": "Session 1"})
        client.post("/input", json_data={"prompt": "Session 2"})

        response = client.get("/sessions")

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert len(data["sessions"]) >= 2

    def test_get_sessions_empty(self, client):
        """GET /sessions should return empty list if no sessions."""
        response = client.get("/sessions")

        assert response.status_code == 200
        assert response.json()["sessions"] == []

    def test_get_sessions_sorted_by_created_desc(self, client):
        """GET /sessions should return sessions sorted by created desc (newest first)."""
        client.post("/input", json_data={"prompt": "First"})
        time.sleep(0.01)  # Ensure different timestamps
        client.post("/input", json_data={"prompt": "Second"})

        response = client.get("/sessions")

        sessions = response.json()["sessions"]
        assert len(sessions) >= 2
        # Newest first
        assert sessions[0]["created"] >= sessions[1]["created"]

    # === GET /health tests ===

    def test_health_check(self, client):
        """GET /health should return healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["agent"] == "test-agent"
        assert "uptime" in data

    # === GET /info tests ===

    def test_info_returns_agent_metadata(self, client):
        """GET /info should return agent name, tools, trust."""
        response = client.get("/info")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "test-agent"
        assert "tools" in data
        assert "trust" in data
        assert "version" in data

    def test_info_includes_tools_list(self, client):
        """GET /info should list available tools."""
        response = client.get("/info")

        data = response.json()
        assert data["tools"] == ["tool1", "tool2"]


class TestSessionStorage:
    """Test SessionStorage class."""

    def test_save_and_get(self, tmp_path):
        """SessionStorage should save and retrieve sessions."""
        from connectonion.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        session = Session(session_id="abc123", status="done", prompt="test", result="result", created=time.time())

        storage.save(session)
        retrieved = storage.get("abc123")

        assert retrieved.session_id == "abc123"
        assert retrieved.result == "result"

    def test_get_requires_exact_id(self, tmp_path):
        """SessionStorage should require exact session_id match (security fix)."""
        from connectonion.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        session = Session(session_id="abc12345-6789", status="done", prompt="test", created=time.time())
        storage.save(session)

        # Partial ID should return None
        assert storage.get("abc") is None
        # Exact match should work
        assert storage.get("abc12345-6789").session_id == "abc12345-6789"

    def test_list_sessions(self, tmp_path):
        """SessionStorage should list all sessions (latest state)."""
        from connectonion.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        storage.save(Session(session_id="a", status="running", prompt="1", created=1))
        storage.save(Session(session_id="b", status="running", prompt="2", created=2))
        storage.save(Session(session_id="a", status="done", prompt="1", result="ok", created=1))

        sessions = storage.list()

        assert len(sessions) == 2
        a_session = next(s for s in sessions if s.session_id == "a")
        assert a_session.status == "done"

    def test_list_sorted_by_created_desc(self, tmp_path):
        """SessionStorage.list() should return sessions sorted by created desc."""
        from connectonion.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        storage.save(Session(session_id="old", status="done", prompt="1", created=100))
        storage.save(Session(session_id="new", status="done", prompt="2", created=200))

        sessions = storage.list()

        assert sessions[0].session_id == "new"  # Newest first
        assert sessions[1].session_id == "old"

    def test_session_with_expires(self, tmp_path):
        """Session should support expires field."""
        from connectonion.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        now = time.time()
        session = Session(session_id="abc", status="done", prompt="test", created=now, expires=now + 3600)
        storage.save(session)

        retrieved = storage.get("abc")

        assert retrieved.expires == now + 3600

    def test_session_with_duration_ms(self, tmp_path):
        """Session should support duration_ms field."""
        from connectonion.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        session = Session(session_id="abc", status="done", prompt="test", created=time.time(), duration_ms=1234)
        storage.save(session)

        retrieved = storage.get("abc")

        assert retrieved.duration_ms == 1234

    def test_get_expired_session_returns_none(self, tmp_path):
        """SessionStorage.get() should return None for expired done sessions."""
        from connectonion.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        now = time.time()
        session = Session(session_id="abc", status="done", prompt="test", created=now - 100, expires=now - 1)
        storage.save(session)

        retrieved = storage.get("abc")

        assert retrieved is None

    def test_get_expired_running_session_still_returns(self, tmp_path):
        """SessionStorage.get() should return running sessions even if expired."""
        from connectonion.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        now = time.time()
        session = Session(session_id="abc", status="running", prompt="test", created=now - 100, expires=now - 1)
        storage.save(session)

        retrieved = storage.get("abc")

        assert retrieved is not None
        assert retrieved.session_id == "abc"

    def test_list_excludes_expired_done_sessions(self, tmp_path):
        """SessionStorage.list() should exclude expired done sessions."""
        from connectonion.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        now = time.time()
        storage.save(Session(session_id="valid", status="done", prompt="1", created=now, expires=now + 3600))
        storage.save(Session(session_id="expired", status="done", prompt="2", created=now - 100, expires=now - 1))

        sessions = storage.list()

        assert len(sessions) == 1
        assert sessions[0].session_id == "valid"

    def test_list_includes_expired_running_sessions(self, tmp_path):
        """SessionStorage.list() should include running sessions even if expired."""
        from connectonion.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        now = time.time()
        storage.save(Session(session_id="running", status="running", prompt="1", created=now, expires=now - 1))

        sessions = storage.list()

        assert len(sessions) == 1
        assert sessions[0].session_id == "running"


class TestAgentAddress:
    """Test agent address generation."""

    def test_get_agent_address(self):
        """get_agent_address should return deterministic 0x-prefixed hash."""
        from connectonion.host import get_agent_address

        class MockAgent:
            name = "test-agent"

        address = get_agent_address(MockAgent())

        assert address.startswith("0x")
        assert len(address) == 42  # 0x + 40 hex chars

    def test_agent_address_is_deterministic(self):
        """Same agent name should produce same address."""
        from connectonion.host import get_agent_address

        class MockAgent:
            name = "translator"

        addr1 = get_agent_address(MockAgent())
        addr2 = get_agent_address(MockAgent())

        assert addr1 == addr2


class TestInfoAddress:
    """Test /info endpoint includes address."""

    @pytest.fixture
    def mock_agent(self):
        agent = MagicMock()
        agent.name = "test-agent"
        agent.tools = MagicMock()
        agent.tools.list_names = MagicMock(return_value=["tool1", "tool2"])
        agent.input = MagicMock(return_value="Hello response")
        agent.current_session = {"messages": [], "trace": [], "turn": 1}
        return agent

    @pytest.fixture
    def app(self, mock_agent, tmp_path):
        from connectonion.host import create_app, SessionStorage
        storage = SessionStorage(str(tmp_path / ".co" / "session_results.jsonl"))
        return create_app(agent=mock_agent, storage=storage, trust="open", result_ttl=3600)

    @pytest.fixture
    def client(self, app):
        return ASGITestClient(app)

    def test_info_includes_address(self, client):
        """GET /info should include agent address."""
        response = client.get("/info")

        data = response.json()
        assert "address" in data
        assert data["address"].startswith("0x")
        assert len(data["address"]) == 42


class TestAuthentication:
    """Test authentication and blacklist/whitelist."""

    def test_extract_and_authenticate_allows_open_trust(self):
        """extract_and_authenticate should allow any request with trust=open."""
        from connectonion.host import extract_and_authenticate

        prompt, identity, valid, err = extract_and_authenticate(
            {"prompt": "hello"}, trust="open"
        )

        assert prompt == "hello"
        assert valid is True
        assert err is None

    def test_extract_and_authenticate_blacklist_blocks(self):
        """extract_and_authenticate should block blacklisted identities."""
        from connectonion.host import extract_and_authenticate

        prompt, identity, valid, err = extract_and_authenticate(
            {"prompt": "hello", "from": "0xbad"},
            trust="open",
            blacklist=["0xbad"]
        )

        assert prompt is None
        assert err == "forbidden: blacklisted"

    def test_extract_and_authenticate_whitelist_allows(self):
        """extract_and_authenticate should allow whitelisted identities."""
        from connectonion.host import extract_and_authenticate

        prompt, identity, valid, err = extract_and_authenticate(
            {"prompt": "hello", "from": "0xgood"},
            trust="strict",
            whitelist=["0xgood"]
        )

        assert prompt == "hello"
        assert valid is True
        assert err is None

    def test_extract_and_authenticate_strict_requires_identity(self):
        """extract_and_authenticate should require identity for trust=strict."""
        from connectonion.host import extract_and_authenticate

        prompt, identity, valid, err = extract_and_authenticate(
            {"prompt": "hello"}, trust="strict"
        )

        assert prompt is None
        assert err == "unauthorized: identity required"

    def test_unknown_trust_level_logs_warning(self, caplog):
        """extract_and_authenticate should warn on unknown trust levels."""
        import logging
        from connectonion.host import extract_and_authenticate

        with caplog.at_level(logging.WARNING):
            prompt, identity, valid, err = extract_and_authenticate(
                {"prompt": "hello"}, trust="carful"  # typo
            )

        # Should fall back to careful and still work
        assert prompt == "hello"
        assert err is None
        # Should have logged a warning
        assert "Unknown trust level 'carful'" in caplog.text
        assert "careful" in caplog.text


class TestSignatureVerification:
    """Test Ed25519 signature verification."""

    def test_verify_signature_valid(self):
        """verify_signature should return True for valid signature."""
        from connectonion.host import verify_signature
        from nacl.signing import SigningKey
        import json

        # Generate keypair
        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key

        # Create payload and sign it
        payload = {"prompt": "hello", "timestamp": 1702234567}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = signing_key.sign(canonical.encode()).signature.hex()

        # Verify
        result = verify_signature(
            payload,
            f"0x{signature}",
            f"0x{verify_key.encode().hex()}"
        )

        assert result is True

    def test_verify_signature_invalid(self):
        """verify_signature should return False for invalid signature."""
        from connectonion.host import verify_signature
        from nacl.signing import SigningKey

        # Generate keypair
        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key

        payload = {"prompt": "hello", "timestamp": 1702234567}

        # Use wrong signature
        result = verify_signature(
            payload,
            "0x" + "00" * 64,  # Invalid signature
            f"0x{verify_key.encode().hex()}"
        )

        assert result is False

    def test_verify_signature_tampered_payload(self):
        """verify_signature should return False if payload was tampered."""
        from connectonion.host import verify_signature
        from nacl.signing import SigningKey
        import json

        signing_key = SigningKey.generate()
        verify_key = signing_key.verify_key

        # Sign original payload
        original = {"prompt": "hello", "timestamp": 1702234567}
        canonical = json.dumps(original, sort_keys=True, separators=(",", ":"))
        signature = signing_key.sign(canonical.encode()).signature.hex()

        # Try to verify with tampered payload
        tampered = {"prompt": "malicious", "timestamp": 1702234567}
        result = verify_signature(
            tampered,
            f"0x{signature}",
            f"0x{verify_key.encode().hex()}"
        )

        assert result is False

    def test_authenticate_signed_request_valid(self):
        """extract_and_authenticate should accept valid signed request."""
        from connectonion.host import extract_and_authenticate
        from nacl.signing import SigningKey
        import json
        import time

        signing_key = SigningKey.generate()
        public_key = f"0x{signing_key.verify_key.encode().hex()}"

        payload = {"prompt": "hello", "timestamp": time.time()}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = f"0x{signing_key.sign(canonical.encode()).signature.hex()}"

        data = {
            "payload": payload,
            "from": public_key,
            "signature": signature
        }

        prompt, identity, valid, err = extract_and_authenticate(data, trust="strict")

        assert prompt == "hello"
        assert identity == public_key
        assert valid is True
        assert err is None

    def test_authenticate_signed_request_expired(self):
        """extract_and_authenticate should reject expired signed request."""
        from connectonion.host import extract_and_authenticate
        from nacl.signing import SigningKey
        import json
        import time

        signing_key = SigningKey.generate()
        public_key = f"0x{signing_key.verify_key.encode().hex()}"

        # Timestamp 10 minutes ago (beyond 5 min window)
        payload = {"prompt": "hello", "timestamp": time.time() - 600}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = f"0x{signing_key.sign(canonical.encode()).signature.hex()}"

        data = {
            "payload": payload,
            "from": public_key,
            "signature": signature
        }

        prompt, identity, valid, err = extract_and_authenticate(data, trust="strict")

        assert prompt is None
        assert err == "unauthorized: signature expired"

    def test_authenticate_signed_request_invalid_signature(self):
        """extract_and_authenticate should reject invalid signature."""
        from connectonion.host import extract_and_authenticate
        from nacl.signing import SigningKey
        import time

        signing_key = SigningKey.generate()
        public_key = f"0x{signing_key.verify_key.encode().hex()}"

        payload = {"prompt": "hello", "timestamp": time.time()}

        data = {
            "payload": payload,
            "from": public_key,
            "signature": "0x" + "00" * 64  # Invalid signature
        }

        prompt, identity, valid, err = extract_and_authenticate(data, trust="strict")

        assert prompt is None
        assert err == "unauthorized: invalid signature"

    def test_authenticate_signed_request_wrong_recipient(self):
        """extract_and_authenticate should reject if 'to' doesn't match agent."""
        from connectonion.host import extract_and_authenticate
        from nacl.signing import SigningKey
        import json
        import time

        signing_key = SigningKey.generate()
        public_key = f"0x{signing_key.verify_key.encode().hex()}"

        payload = {"prompt": "hello", "timestamp": time.time(), "to": "0xwrong"}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = f"0x{signing_key.sign(canonical.encode()).signature.hex()}"

        data = {
            "payload": payload,
            "from": public_key,
            "signature": signature
        }

        prompt, identity, valid, err = extract_and_authenticate(
            data, trust="strict", agent_address="0xcorrect"
        )

        assert prompt is None
        assert err == "unauthorized: wrong recipient"

    def test_authenticate_signed_blacklist_checked_first(self):
        """Blacklist should be checked before signature verification."""
        from connectonion.host import extract_and_authenticate
        import time

        data = {
            "payload": {"prompt": "hello", "timestamp": time.time()},
            "from": "0xbad",
            "signature": "0x" + "00" * 64
        }

        prompt, identity, valid, err = extract_and_authenticate(
            data, trust="open", blacklist=["0xbad"]
        )

        assert err == "forbidden: blacklisted"


class TestHostApp:
    """Test host.app export."""

    def test_host_has_app_attribute(self):
        """host function should have app attribute."""
        from connectonion.host import host

        assert hasattr(host, "app")
        assert callable(host.app)

    def test_host_app_creates_asgi_app(self):
        """host.app should create ASGI app."""
        from connectonion.host import host

        class MockAgent:
            name = "test"
            tools = MagicMock()
            tools.list_names = MagicMock(return_value=[])
            input = MagicMock(return_value="response")

        app = host.app(MockAgent())

        assert callable(app)
