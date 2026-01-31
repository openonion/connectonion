"""
Tests for host() HTTP endpoints.

Based on docs/network/host.md specification.
"""

import asyncio
import json
import time
import pytest
from unittest.mock import MagicMock


# === Helper for async execution ===

def run_async(coro):
    """Run async code safely, creating new event loop to avoid pollution from other tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# === Simple ASGI Test Client ===

def create_signed_request(prompt: str, timestamp: float = None) -> dict:
    """Create a properly signed request for testing."""
    from nacl.signing import SigningKey

    signing_key = SigningKey.generate()
    public_key = f"0x{signing_key.verify_key.encode().hex()}"

    payload = {"prompt": prompt, "timestamp": timestamp or time.time()}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = f"0x{signing_key.sign(canonical.encode()).signature.hex()}"

    return {
        "payload": payload,
        "from": public_key,
        "signature": signature
    }


class ASGITestClient:
    """Minimal ASGI test client - no external dependencies."""

    def __init__(self, app):
        self.app = app

    def _run(self, coro):
        # Use new_event_loop to avoid "no current event loop" error in Python 3.10+
        # when previous tests have closed or consumed the default event loop
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def get(self, path: str) -> "Response":
        return self._run(self._request("GET", path))

    def post(self, path: str, json_data: dict = None) -> "Response":
        return self._run(self._request("POST", path, json_data))

    def post_signed(self, path: str, prompt: str) -> "Response":
        """POST with a signed request (protocol requirement)."""
        signed_data = create_signed_request(prompt)
        return self._run(self._request("POST", path, signed_data))

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
    def create_mock_agent(self):
        """Create a factory that returns mock agents for testing.

        Each call returns a fresh mock agent instance, matching
        the factory pattern used by host().
        """
        def factory():
            agent = MagicMock()
            agent.name = "test-agent"
            agent.tools = MagicMock()
            agent.tools.names = MagicMock(return_value=["tool1", "tool2"])
            agent.input = MagicMock(return_value="Hello response")
            agent.current_session = {"messages": [], "trace": [], "turn": 1}
            return agent
        return factory

    @pytest.fixture
    def app(self, create_mock_agent, tmp_path):
        """Create test ASGI app."""
        from connectonion.network.host import create_app, SessionStorage

        storage = SessionStorage(str(tmp_path / ".co" / "session_results.jsonl"))
        return create_app(create_agent=create_mock_agent, storage=storage, trust="open", result_ttl=3600)

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return ASGITestClient(app)

    # === POST /input tests ===

    def test_post_input_creates_session(self, client):
        """POST /input should create session and return session_id."""
        response = client.post_signed("/input", "Hello")

        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "done"

    def test_post_input_returns_result(self, client):
        """POST /input should include result."""
        response = client.post_signed("/input", "Hello")

        data = response.json()
        assert data["status"] == "done"
        assert data["result"] == "Hello response"

    def test_post_input_returns_duration_ms(self, client):
        """POST /input should include duration_ms."""
        response = client.post_signed("/input", "Hello")

        data = response.json()
        assert "duration_ms" in data
        assert isinstance(data["duration_ms"], int)

    def test_post_input_full_uuid(self, client):
        """POST /input should return full UUID session_id."""
        response = client.post_signed("/input", "Hello")

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

        response = run_async(test())
        assert response.status_code == 400

    # === GET /sessions/{session_id} tests ===

    def test_get_session_by_id(self, client):
        """GET /sessions/{session_id} should return session."""
        create_response = client.post_signed("/input", "Hello")
        session_id = create_response.json()["session_id"]

        response = client.get(f"/sessions/{session_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

    def test_get_session_partial_id_not_allowed(self, client):
        """GET /sessions/{session_id} should NOT match partial ID (security fix)."""
        create_response = client.post_signed("/input", "Hello")
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
        create_response = client.post_signed("/input", "Hello")
        session_id = create_response.json()["session_id"]

        response = client.get(f"/sessions/{session_id}")

        data = response.json()
        assert "expires" in data
        assert data["expires"] > time.time()  # Should be in the future

    def test_get_session_includes_duration_ms(self, client):
        """GET /sessions/{session_id} should include duration_ms for done sessions."""
        create_response = client.post_signed("/input", "Hello")
        session_id = create_response.json()["session_id"]

        response = client.get(f"/sessions/{session_id}")

        data = response.json()
        assert "duration_ms" in data

    # === GET /sessions tests ===

    def test_get_sessions_list(self, client):
        """GET /sessions should list all sessions."""
        client.post_signed("/input", "Session 1")
        client.post_signed("/input", "Session 2")

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
        client.post_signed("/input", "First")
        time.sleep(0.01)  # Ensure different timestamps
        client.post_signed("/input", "Second")

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
        from connectonion.network.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        session = Session(session_id="abc123", status="done", prompt="test", result="result", created=time.time())

        storage.save(session)
        retrieved = storage.get("abc123")

        assert retrieved.session_id == "abc123"
        assert retrieved.result == "result"

    def test_get_requires_exact_id(self, tmp_path):
        """SessionStorage should require exact session_id match (security fix)."""
        from connectonion.network.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        session = Session(session_id="abc12345-6789", status="done", prompt="test", created=time.time())
        storage.save(session)

        # Partial ID should return None
        assert storage.get("abc") is None
        # Exact match should work
        assert storage.get("abc12345-6789").session_id == "abc12345-6789"

    def test_list_sessions(self, tmp_path):
        """SessionStorage should list all sessions (latest state)."""
        from connectonion.network.host import SessionStorage, Session

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
        from connectonion.network.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        storage.save(Session(session_id="old", status="done", prompt="1", created=100))
        storage.save(Session(session_id="new", status="done", prompt="2", created=200))

        sessions = storage.list()

        assert sessions[0].session_id == "new"  # Newest first
        assert sessions[1].session_id == "old"

    def test_session_with_expires(self, tmp_path):
        """Session should support expires field."""
        from connectonion.network.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        now = time.time()
        session = Session(session_id="abc", status="done", prompt="test", created=now, expires=now + 3600)
        storage.save(session)

        retrieved = storage.get("abc")

        assert retrieved.expires == now + 3600

    def test_session_with_duration_ms(self, tmp_path):
        """Session should support duration_ms field."""
        from connectonion.network.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        session = Session(session_id="abc", status="done", prompt="test", created=time.time(), duration_ms=1234)
        storage.save(session)

        retrieved = storage.get("abc")

        assert retrieved.duration_ms == 1234

    def test_get_expired_session_returns_none(self, tmp_path):
        """SessionStorage.get() should return None for expired done sessions."""
        from connectonion.network.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        now = time.time()
        session = Session(session_id="abc", status="done", prompt="test", created=now - 100, expires=now - 1)
        storage.save(session)

        retrieved = storage.get("abc")

        assert retrieved is None

    def test_get_expired_running_session_still_returns(self, tmp_path):
        """SessionStorage.get() should return running sessions even if expired."""
        from connectonion.network.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        now = time.time()
        session = Session(session_id="abc", status="running", prompt="test", created=now - 100, expires=now - 1)
        storage.save(session)

        retrieved = storage.get("abc")

        assert retrieved is not None
        assert retrieved.session_id == "abc"

    def test_list_excludes_expired_done_sessions(self, tmp_path):
        """SessionStorage.list() should exclude expired done sessions."""
        from connectonion.network.host import SessionStorage, Session

        storage = SessionStorage(str(tmp_path / "session_results.jsonl"))
        now = time.time()
        storage.save(Session(session_id="valid", status="done", prompt="1", created=now, expires=now + 3600))
        storage.save(Session(session_id="expired", status="done", prompt="2", created=now - 100, expires=now - 1))

        sessions = storage.list()

        assert len(sessions) == 1
        assert sessions[0].session_id == "valid"

    def test_list_includes_expired_running_sessions(self, tmp_path):
        """SessionStorage.list() should include running sessions even if expired."""
        from connectonion.network.host import SessionStorage, Session

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
        from connectonion.network.host import get_agent_address

        class MockAgent:
            name = "test-agent"

        address = get_agent_address(MockAgent())

        assert address.startswith("0x")
        assert len(address) == 42  # 0x + 40 hex chars

    def test_agent_address_is_deterministic(self):
        """Same agent name should produce same address."""
        from connectonion.network.host import get_agent_address

        class MockAgent:
            name = "translator"

        addr1 = get_agent_address(MockAgent())
        addr2 = get_agent_address(MockAgent())

        assert addr1 == addr2


class TestInfoAddress:
    """Test /info endpoint includes address."""

    @pytest.fixture
    def create_mock_agent(self):
        """Create a factory that returns mock agents for testing."""
        def factory():
            agent = MagicMock()
            agent.name = "test-agent"
            agent.tools = MagicMock()
            agent.tools.names = MagicMock(return_value=["tool1", "tool2"])
            agent.input = MagicMock(return_value="Hello response")
            agent.current_session = {"messages": [], "trace": [], "turn": 1}
            return agent
        return factory

    @pytest.fixture
    def app(self, create_mock_agent, tmp_path):
        from connectonion.network.host import create_app, SessionStorage
        storage = SessionStorage(str(tmp_path / ".co" / "session_results.jsonl"))
        return create_app(create_agent=create_mock_agent, storage=storage, trust="open", result_ttl=3600)

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
    """Test authentication and blacklist/whitelist.

    All requests must be signed (protocol requirement).
    Trust levels control additional policies AFTER signature verification.
    """

    def _create_signed_request(self, prompt: str, public_key: str = None, timestamp: float = None):
        """Helper to create a properly signed request."""
        from nacl.signing import SigningKey
        import time

        signing_key = SigningKey.generate()
        if public_key is None:
            public_key = f"0x{signing_key.verify_key.encode().hex()}"

        payload = {"prompt": prompt, "timestamp": timestamp or time.time()}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = f"0x{signing_key.sign(canonical.encode()).signature.hex()}"

        return {
            "payload": payload,
            "from": public_key,
            "signature": signature
        }, signing_key

    def test_extract_and_authenticate_requires_signed_request(self):
        """extract_and_authenticate should require signed requests."""
        from connectonion.network.host import extract_and_authenticate

        # Unsigned request should fail
        prompt, identity, valid, err = extract_and_authenticate(
            {"prompt": "hello"}, trust="open"
        )

        assert prompt is None
        assert err == "unauthorized: signed request required"

    def test_extract_and_authenticate_blacklist_blocks(self):
        """extract_and_authenticate should block blacklisted identities."""
        from connectonion.network.host import extract_and_authenticate
        from nacl.signing import SigningKey
        import time

        # Create signed request with blacklisted identity
        signing_key = SigningKey.generate()
        bad_identity = "0xbad"
        payload = {"prompt": "hello", "timestamp": time.time()}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = f"0x{signing_key.sign(canonical.encode()).signature.hex()}"

        prompt, identity, valid, err = extract_and_authenticate(
            {"payload": payload, "from": bad_identity, "signature": signature},
            trust="open",
            blacklist=["0xbad"]
        )

        assert prompt is None
        assert err == "forbidden: blacklisted"

    def test_extract_and_authenticate_whitelist_allows(self):
        """extract_and_authenticate should allow whitelisted identities (bypass signature check)."""
        from connectonion.network.host import extract_and_authenticate
        import time

        # Whitelisted identity bypasses signature verification
        good_identity = "0xgood"
        payload = {"prompt": "hello", "timestamp": time.time()}

        prompt, identity, valid, err = extract_and_authenticate(
            {"payload": payload, "from": good_identity, "signature": "0x" + "00" * 64},
            trust="strict",
            whitelist=["0xgood"]
        )

        assert prompt == "hello"
        assert err is None

    def test_extract_and_authenticate_strict_without_whitelist(self):
        """extract_and_authenticate strict mode without whitelist requires valid signature."""
        from connectonion.network.host import extract_and_authenticate
        from nacl.signing import SigningKey
        import time

        signing_key = SigningKey.generate()
        public_key = f"0x{signing_key.verify_key.encode().hex()}"
        payload = {"prompt": "hello", "timestamp": time.time()}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = f"0x{signing_key.sign(canonical.encode()).signature.hex()}"

        # Without whitelist, strict mode requires valid signature
        prompt, identity, valid, err = extract_and_authenticate(
            {"payload": payload, "from": public_key, "signature": signature},
            trust="strict"
        )

        assert prompt == "hello"
        assert valid is True
        assert err is None

    def test_extract_and_authenticate_missing_from_field(self):
        """extract_and_authenticate should reject request without 'from' field."""
        from connectonion.network.host import extract_and_authenticate
        import time

        payload = {"prompt": "hello", "timestamp": time.time()}

        prompt, identity, valid, err = extract_and_authenticate(
            {"payload": payload, "signature": "0x" + "00" * 64},
            trust="open"
        )

        assert prompt is None
        assert err == "unauthorized: 'from' field required"


class TestSignatureVerification:
    """Test Ed25519 signature verification."""

    def test_verify_signature_valid(self):
        """verify_signature should return True for valid signature."""
        from connectonion.network.host import verify_signature
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
        from connectonion.network.host import verify_signature
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
        from connectonion.network.host import verify_signature
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
        from connectonion.network.host import extract_and_authenticate
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
        from connectonion.network.host import extract_and_authenticate
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
        from connectonion.network.host import extract_and_authenticate
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
        from connectonion.network.host import extract_and_authenticate
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
        from connectonion.network.host import extract_and_authenticate
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


class TestCORS:
    """Test CORS headers for cross-origin requests."""

    @pytest.fixture
    def create_mock_agent(self):
        """Create a factory that returns mock agents for testing."""
        def factory():
            agent = MagicMock()
            agent.name = "test-agent"
            agent.tools = MagicMock()
            agent.tools.names = MagicMock(return_value=["tool1"])
            agent.input = MagicMock(return_value="Hello response")
            agent.current_session = {"messages": [], "trace": [], "turn": 1}
            return agent
        return factory

    @pytest.fixture
    def app(self, create_mock_agent, tmp_path):
        """Create test ASGI app."""
        from connectonion.network.host import create_app, SessionStorage
        storage = SessionStorage(str(tmp_path / ".co" / "session_results.jsonl"))
        return create_app(create_agent=create_mock_agent, storage=storage, trust="open", result_ttl=3600)

    def test_options_preflight_returns_204(self, app):
        """OPTIONS request should return 204 with CORS headers."""
        async def test():
            scope = {
                "type": "http",
                "method": "OPTIONS",
                "path": "/input",
                "query_string": b"",
                "headers": [],
            }
            response = Response()
            response.headers = []

            async def receive():
                return {"type": "http.disconnect"}

            async def send(message):
                if message["type"] == "http.response.start":
                    response.status_code = message["status"]
                    response.headers = message.get("headers", [])
                elif message["type"] == "http.response.body":
                    response.body = message.get("body", b"")

            await app(scope, receive, send)
            return response

        response = run_async(test())
        assert response.status_code == 204

        # Check CORS headers
        headers_dict = {h[0].decode(): h[1].decode() for h in response.headers}
        assert headers_dict.get("access-control-allow-origin") == "*"
        assert "GET" in headers_dict.get("access-control-allow-methods", "")
        assert "POST" in headers_dict.get("access-control-allow-methods", "")

    def test_json_response_includes_cors_headers(self, app):
        """JSON responses should include CORS headers."""
        async def test():
            scope = {
                "type": "http",
                "method": "GET",
                "path": "/health",
                "query_string": b"",
                "headers": [],
            }
            response = Response()
            response.headers = []

            async def receive():
                return {"type": "http.disconnect"}

            async def send(message):
                if message["type"] == "http.response.start":
                    response.status_code = message["status"]
                    response.headers = message.get("headers", [])
                elif message["type"] == "http.response.body":
                    response.body = message.get("body", b"")

            await app(scope, receive, send)
            return response

        response = run_async(test())
        assert response.status_code == 200

        # Check CORS headers in response
        headers_dict = {h[0].decode(): h[1].decode() for h in response.headers}
        assert headers_dict.get("access-control-allow-origin") == "*"


class TestAdminEndpoints:
    """Test admin endpoints requiring API key authentication."""

    @pytest.fixture
    def create_mock_agent(self):
        """Create a factory that returns mock agents for testing."""
        def factory():
            agent = MagicMock()
            agent.name = "test-agent"
            agent.tools = MagicMock()
            agent.tools.names = MagicMock(return_value=["tool1"])
            agent.input = MagicMock(return_value="Hello response")
            agent.current_session = {"messages": [], "trace": [], "turn": 1}
            return agent
        return factory

    @pytest.fixture
    def app(self, create_mock_agent, tmp_path):
        """Create test ASGI app."""
        from connectonion.network.host import create_app, SessionStorage
        storage = SessionStorage(str(tmp_path / ".co" / "session_results.jsonl"))
        return create_app(create_agent=create_mock_agent, storage=storage, trust="open", result_ttl=3600)

    def _make_request(self, app, method: str, path: str, headers: list = None):
        """Helper to make async request with headers."""
        async def test():
            scope = {
                "type": "http",
                "method": method,
                "path": path,
                "query_string": b"",
                "headers": headers or [],
            }
            response = Response()

            async def receive():
                return {"type": "http.disconnect"}

            async def send(message):
                if message["type"] == "http.response.start":
                    response.status_code = message["status"]
                elif message["type"] == "http.response.body":
                    response.body = message.get("body", b"")

            await app(scope, receive, send)
            return response

        return run_async(test())

    def test_admin_logs_requires_auth(self, app):
        """GET /admin/logs without API key should return 401."""
        response = self._make_request(app, "GET", "/admin/logs")
        assert response.status_code == 401
        assert b"unauthorized" in response.body

    def test_admin_sessions_requires_auth(self, app):
        """GET /admin/sessions without API key should return 401."""
        response = self._make_request(app, "GET", "/admin/sessions")
        assert response.status_code == 401
        assert b"unauthorized" in response.body

    def test_admin_logs_with_wrong_key(self, app, monkeypatch):
        """GET /admin/logs with wrong API key should return 401."""
        monkeypatch.setenv("OPENONION_API_KEY", "correct-key")

        response = self._make_request(
            app, "GET", "/admin/logs",
            headers=[[b"authorization", b"Bearer wrong-key"]]
        )
        assert response.status_code == 401

    def test_admin_logs_with_correct_key(self, app, monkeypatch, tmp_path):
        """GET /admin/logs with correct API key should return 200."""
        monkeypatch.setenv("OPENONION_API_KEY", "test-api-key")

        # Create a log file
        log_dir = tmp_path / ".co" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "test-agent.log").write_text("Test log content\n")

        # Change to tmp_path so the handler finds the logs
        import os
        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            response = self._make_request(
                app, "GET", "/admin/logs",
                headers=[[b"authorization", b"Bearer test-api-key"]]
            )
            # Should return 200 or 404 (if no logs) - not 401
            assert response.status_code in [200, 404]
        finally:
            os.chdir(original_cwd)

    def test_admin_sessions_with_correct_key(self, app, monkeypatch, tmp_path):
        """GET /admin/sessions with correct API key should return 200."""
        monkeypatch.setenv("OPENONION_API_KEY", "test-api-key")

        # Change to tmp_path
        import os
        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            response = self._make_request(
                app, "GET", "/admin/sessions",
                headers=[[b"authorization", b"Bearer test-api-key"]]
            )
            assert response.status_code == 200
            data = json.loads(response.body)
            assert "sessions" in data
        finally:
            os.chdir(original_cwd)

    def test_admin_unknown_endpoint_returns_404(self, app, monkeypatch):
        """GET /admin/unknown should return 404."""
        monkeypatch.setenv("OPENONION_API_KEY", "test-api-key")

        response = self._make_request(
            app, "GET", "/admin/unknown",
            headers=[[b"authorization", b"Bearer test-api-key"]]
        )
        assert response.status_code == 404
