"""
WebSocket tests for host() endpoints using raw ASGI.

Covers:
- Path restriction (/ws only)
- INPUT handling with signed requests
- Strict trust with signed payloads (accept/reject)
- Blacklist/whitelist enforcement
- Invalid JSON handling

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
        return asyncio.get_event_loop().run_until_complete(coro)

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
def mock_agent():
    """Create a real Agent with MockLLM that can be deep copied."""
    mock_llm = MockLLM(responses=[
        LLMResponseBuilder.text_response("out:hi"),
    ])
    return Agent(name="ws-agent", llm=mock_llm, log=False, quiet=True)


@pytest.fixture
def app(mock_agent, tmp_path):
    from connectonion.host import _make_app
    return _make_app(mock_agent, trust="open", result_ttl=3600)


class TestWebSocket:
    def test_path_restriction(self, app):
        client = ASGIWebSocketClient(app, path="/not-ws")
        sent = client.connect_only()
        # Should close with 4004
        assert any(m.get("type") == "websocket.close" and m.get("code") == 4004 for m in sent)

    def test_open_trust_input(self, app):
        """All requests require signatures (protocol requirement)."""
        client = ASGIWebSocketClient(app, path="/ws")
        msg = json.dumps(sign_request("hi"))
        sent = client.send_text(msg)

        assert any(m.get("type") == "websocket.accept" for m in sent)
        outputs = [m for m in sent if m.get("type") == "websocket.send"]
        assert outputs, "expected websocket.send messages"
        data = json.loads(outputs[-1]["text"])
        assert data["type"] == "OUTPUT"
        assert data["result"] == "out:hi"

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
    @pytest.fixture
    def mock_agent_strict(self):
        """Fresh agent for strict tests."""
        mock_llm = MockLLM(responses=[
            LLMResponseBuilder.text_response("out:hi"),
        ])
        return Agent(name="ws-agent", llm=mock_llm, log=False, quiet=True)

    @pytest.fixture
    def app_strict(self, mock_agent_strict, tmp_path):
        from connectonion.host import _make_app
        return _make_app(mock_agent_strict, trust="strict", result_ttl=3600)

    def test_strict_requires_signature(self, app_strict):
        client = ASGIWebSocketClient(app_strict)
        msg = json.dumps({"type": "INPUT", "prompt": "hi"})
        sent = client.send_text(msg)
        errs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(e.get("type") == "ERROR" and e.get("message", "").startswith("unauthorized") for e in errs)

    def test_strict_valid_signature(self, app_strict):
        client = ASGIWebSocketClient(app_strict)
        sent = client.send_text(json.dumps(sign_request("hi")))
        outputs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(o.get("type") == "OUTPUT" and o.get("result") == "out:hi" for o in outputs)

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
    def mock_agent_bw(self):
        """Fresh agent for access list tests."""
        mock_llm = MockLLM(responses=[
            LLMResponseBuilder.text_response("out:hi"),
        ])
        return Agent(name="ws-agent", llm=mock_llm, log=False, quiet=True)

    @pytest.fixture
    def app_strict_bw(self, mock_agent_bw, tmp_path):
        from connectonion.host import _make_app
        return _make_app(mock_agent_bw, trust="strict", result_ttl=3600, blacklist=["0xbad"], whitelist=["0xgood"])

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

    def test_whitelisted(self, app_strict_bw):
        data = {
            "type": "INPUT",
            "payload": {"prompt": "hi", "timestamp": time.time()},
            "from": "0xgood",
            "signature": "0x" + "00" * 64  # even with bad signature, whitelist allows
        }
        client = ASGIWebSocketClient(app_strict_bw)
        sent = client.send_text(json.dumps(data))
        outs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(o.get("type") == "OUTPUT" and o.get("result") == "out:hi" for o in outs)
