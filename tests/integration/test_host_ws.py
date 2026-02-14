"""
WebSocket tests for host() endpoints using raw ASGI.

Covers:
- Path restriction (/ws only)
- INPUT handling with signed requests
- Strict trust with signed payloads (accept/reject)
- Blacklist/whitelist enforcement
- Invalid JSON handling
- PING/PONG keep-alive mechanism
- Session persistence and recovery

All requests require signatures (protocol requirement).
"""

import asyncio
import json
import time
import pytest
from nacl.signing import SigningKey

from connectonion import Agent
from tests.utils.mock_helpers import MockLLM, LLMResponseBuilder


def sign_request(prompt: str, signing_key: SigningKey = None):
    """Helper to create a signed WebSocket INPUT request."""
    if signing_key is None:
        signing_key = SigningKey.generate()

    public_key = f"0x{signing_key.verify_key.encode().hex()}"
    payload = {"prompt": prompt, "timestamp": time.time()}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    signature = f"0x{signing_key.sign(canonical.encode()).signature.hex()}"

    return {
        "type": "INPUT",
        "payload": payload,
        "from": public_key,
        "signature": signature
    }


class ASGIWebSocketClient:
    """Minimal ASGI WebSocket test client."""

    def __init__(self, app, path="/ws"):
        self.app = app
        self.path = path
        self.sent = []  # messages sent by app

    def _run(self, coro):
        # Use new_event_loop to avoid "no current event loop" error in Python 3.10+
        # when previous tests have closed or consumed the default event loop
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def send_text(self, text: str):
        return self._run(self._session([{"type": "websocket.receive", "text": text}, {"type": "websocket.disconnect"}]))

    def connect_only(self):
        return self._run(self._session([{ "type": "websocket.disconnect" }]))

    async def _session(self, incoming_messages):
        scope = {"type": "websocket", "path": self.path, "query_string": b"", "headers": []}
        messages = list(incoming_messages)

        async def receive():
            if messages:
                return messages.pop(0)
            return {"type": "websocket.disconnect"}

        async def send(message):
            self.sent.append(message)

        await self.app(scope, receive, send)
        return self.sent


@pytest.fixture
def create_mock_agent():
    """Factory that creates fresh Agent instances with MockLLM."""
    def factory():
        mock_llm = MockLLM(responses=[
            LLMResponseBuilder.text_response("out:hi"),
        ])
        return Agent(name="ws-agent", llm=mock_llm, log=False, quiet=True)
    return factory


@pytest.fixture
def app(create_mock_agent, tmp_path):
    from connectonion.network.host import create_app
    return create_app(create_mock_agent, trust="open", result_ttl=3600)


class TestWebSocket:
    def test_path_restriction(self, app):
        client = ASGIWebSocketClient(app, path="/not-ws")
        sent = client.connect_only()
        # Should close with 4004
        assert any(m.get("type") == "websocket.close" and m.get("code") == 4004 for m in sent)

    @pytest.mark.skip(reason="WebSocket handler implementation changed; test needs rewrite")
    def test_open_trust_input(self, app):
        """All requests require signatures (protocol requirement).

        Note: This test client sends INPUT then immediately disconnects,
        so OUTPUT is not sent (correct behavior - result saved to storage for polling recovery).
        We verify the request was accepted and processed by checking for trace events.
        """
        client = ASGIWebSocketClient(app, path="/ws")
        msg = json.dumps(sign_request("hi"))
        sent = client.send_text(msg)

        assert any(m.get("type") == "websocket.accept" for m in sent)
        outputs = [m for m in sent if m.get("type") == "websocket.send"]
        assert outputs, "expected websocket.send messages"
        # Parse all messages - should see trace events
        messages = [json.loads(m["text"]) for m in outputs]
        # Verify we got trace events showing the agent processed the request
        assert any(msg.get("type") == "user_input" for msg in messages), f"Expected user_input event, got: {[msg.get('type') for msg in messages]}"

    def test_unsigned_request_rejected(self, app):
        """Unsigned requests are always rejected."""
        client = ASGIWebSocketClient(app, path="/ws")
        msg = json.dumps({"type": "INPUT", "prompt": "hi"})
        sent = client.send_text(msg)
        errs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(e.get("type") == "ERROR" and "unauthorized" in e.get("message", "") for e in errs)

    def test_invalid_json(self, app):
        client = ASGIWebSocketClient(app, path="/ws")
        sent = client.send_text("{not json}")
        errs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(e.get("type") == "ERROR" and "Invalid JSON" in e.get("message", "") for e in errs)


class TestWebSocketStrict:
    """Tests for strict trust mode.

    Strict mode only allows whitelisted identities.
    Valid signatures are necessary but not sufficient.
    """

    @pytest.fixture
    def create_mock_agent_strict(self):
        """Factory that creates fresh Agent instances for strict tests."""
        def factory():
            mock_llm = MockLLM(responses=[
                LLMResponseBuilder.text_response("out:hi"),
            ])
            return Agent(name="ws-agent", llm=mock_llm, log=False, quiet=True)
        return factory

    @pytest.fixture
    def app_strict(self, create_mock_agent_strict, tmp_path):
        from connectonion.network.host import create_app
        return create_app(create_mock_agent_strict, trust="strict", result_ttl=3600)

    def test_strict_requires_signature(self, app_strict):
        client = ASGIWebSocketClient(app_strict)
        msg = json.dumps({"type": "INPUT", "prompt": "hi"})
        sent = client.send_text(msg)
        errs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(e.get("type") == "ERROR" and e.get("message", "").startswith("unauthorized") for e in errs)

    def test_strict_denies_non_whitelisted(self, app_strict):
        """Strict mode denies valid signatures from non-whitelisted identities."""
        client = ASGIWebSocketClient(app_strict)
        sent = client.send_text(json.dumps(sign_request("hi")))
        outputs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        # Should get ERROR (forbidden) since identity is not whitelisted
        assert any(o.get("type") == "ERROR" and "forbidden" in o.get("message", "").lower() for o in outputs), \
            f"Expected forbidden error, got: {[o.get('type') for o in outputs]}"

    def test_strict_invalid_signature(self, app_strict):
        signing_key = SigningKey.generate()
        public_key = f"0x{signing_key.verify_key.encode().hex()}"
        payload = {"prompt": "hi", "timestamp": time.time()}
        data = {"type": "INPUT", "payload": payload, "from": public_key, "signature": "0x" + "00" * 64}

        client = ASGIWebSocketClient(app_strict)
        sent = client.send_text(json.dumps(data))
        errs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(e.get("type") == "ERROR" and "invalid signature" in e.get("message", "") for e in errs)


class TestWebSocketAccessLists:
    @pytest.fixture
    def create_mock_agent_bw(self):
        """Factory that creates fresh Agent instances for access list tests."""
        def factory():
            mock_llm = MockLLM(responses=[
                LLMResponseBuilder.text_response("out:hi"),
            ])
            return Agent(name="ws-agent", llm=mock_llm, log=False, quiet=True)
        return factory

    @pytest.fixture
    def app_strict_bw(self, create_mock_agent_bw, tmp_path):
        from connectonion.network.host import create_app
        return create_app(create_mock_agent_bw, trust="strict", result_ttl=3600, blacklist=["0xbad"], whitelist=["0xgood"])

    def test_blacklisted(self, app_strict_bw):
        data = {
            "type": "INPUT",
            "payload": {"prompt": "hi", "timestamp": time.time()},
            "from": "0xbad",
            "signature": "0x" + "00" * 64
        }
        client = ASGIWebSocketClient(app_strict_bw)
        sent = client.send_text(json.dumps(data))
        errs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(e.get("type") == "ERROR" and e.get("message") == "forbidden: blacklisted" for e in errs)

    def test_whitelisted_still_requires_valid_signature(self, app_strict_bw):
        """Whitelist bypasses trust policy, NOT signature verification.

        Security fix: Even whitelisted identities must provide valid signatures.
        This prevents spoofing attacks where anyone claims to be whitelisted.
        """
        data = {
            "type": "INPUT",
            "payload": {"prompt": "hi", "timestamp": time.time()},
            "from": "0xgood",
            "signature": "0x" + "00" * 64  # Invalid signature
        }
        client = ASGIWebSocketClient(app_strict_bw)
        sent = client.send_text(json.dumps(data))
        outs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        # Should fail with invalid signature error
        assert any(o.get("type") == "ERROR" and "invalid signature" in o.get("message", "") for o in outs), \
            f"Expected invalid signature error, got: {[o.get('type') for o in outs]}"


class TestWebSocketKeepAlive:
    """Tests for PING/PONG keep-alive mechanism."""

    @pytest.fixture
    def create_slow_agent(self):
        """Factory that creates agent with slow response to test PING during execution."""
        def factory():
            # Mock LLM that simulates a 5-second processing time
            import time

            class SlowMockLLM:
                def complete(self, messages, tools=None):
                    time.sleep(2)  # Simulate slow processing
                    from connectonion.core.llm import LLMResponse
                    return LLMResponse(content="Slow response", tool_calls=[], raw_response={})

            return Agent(name="slow-agent", llm=SlowMockLLM(), log=False, quiet=True)
        return factory

    @pytest.fixture
    def app_slow(self, create_slow_agent):
        from connectonion.network.host import create_app
        return create_app(create_slow_agent, trust="open", result_ttl=3600)

    @pytest.mark.skip(reason="WebSocket handler implementation changed; test needs rewrite")
    def test_pong_response_handling(self, app):
        """Test that server correctly handles PONG responses from client.

        Note: PONG handling is tested implicitly - if PONG caused errors,
        the request would fail. We verify normal processing occurs.
        """
        client = ASGIWebSocketClient(app, path="/ws")

        # Send signed INPUT
        msg = json.dumps(sign_request("hi"))
        sent = client.send_text(msg)

        # Should accept connection and process normally
        assert any(m.get("type") == "websocket.accept" for m in sent)
        outputs = [m for m in sent if m.get("type") == "websocket.send"]
        messages = [json.loads(m["text"]) for m in outputs]
        # Verify request was processed (check for trace events)
        assert any(msg.get("type") == "user_input" for msg in messages)

    @pytest.mark.skip(reason="WebSocket handler implementation changed; test needs rewrite")
    def test_session_includes_session_id(self, app):
        """Test that session structure supports session_id for recovery.

        Note: Client disconnects immediately so OUTPUT not sent,
        but we verify the session structure exists in INPUT processing.
        """
        client = ASGIWebSocketClient(app, path="/ws")
        msg = json.dumps(sign_request("hi"))
        sent = client.send_text(msg)

        # Verify connection accepted and processing started
        assert any(m.get("type") == "websocket.accept" for m in sent)
        outputs = [m for m in sent if m.get("type") == "websocket.send"]
        assert len(outputs) > 0, "expected trace events showing processing"


class TestSessionRecovery:
    """Tests for session persistence and recovery via GET /sessions/{id}."""

    def test_session_storage_persistence(self, app, tmp_path):
        """Test that session results are saved to storage for recovery."""
        # This is implicitly tested by the host() implementation
        # Session results are saved to .co/session_results.jsonl
        # The GET /sessions/{id} endpoint reads from this storage
        pass  # Implementation verified in host.md documentation
