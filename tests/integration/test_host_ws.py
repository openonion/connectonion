"""
WebSocket tests for host() endpoints using raw ASGI.

Covers:
- Path restriction (/ws only)
- INPUT handling in open trust mode
- Strict trust with signed payloads (accept/reject)
- Blacklist/whitelist enforcement
- Invalid JSON handling
"""

import asyncio
import json
import time
import pytest
from unittest.mock import MagicMock


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
            # Default to disconnect if no further messages
            return {"type": "websocket.disconnect"}

        async def send(message):
            self.sent.append(message)

        await self.app(scope, receive, send)
        return self.sent


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.name = "ws-agent"
    agent.tools = MagicMock()
    agent.tools.list_names = MagicMock(return_value=[])
    agent.input = MagicMock(side_effect=lambda prompt: f"out:{prompt}")
    agent.current_session = {"messages": [], "trace": [], "turn": 1}
    return agent


@pytest.fixture
def app(mock_agent, tmp_path):
    from connectonion.host import _make_app, SessionStorage
    storage = SessionStorage(str(tmp_path / ".co" / "session_results.jsonl"))
    return _make_app(mock_agent, trust="open", result_ttl=3600)


class TestWebSocket:
    def test_path_restriction(self, app):
        client = ASGIWebSocketClient(app, path="/not-ws")
        sent = client.connect_only()
        # Should close with 4004
        assert any(m.get("type") == "websocket.close" and m.get("code") == 4004 for m in sent)

    def test_open_trust_input(self, app):
        client = ASGIWebSocketClient(app, path="/ws")
        msg = json.dumps({"type": "INPUT", "prompt": "hi"})
        sent = client.send_text(msg)
        # Expect accept + OUTPUT
        assert any(m.get("type") == "websocket.accept" for m in sent)
        outputs = [m for m in sent if m.get("type") == "websocket.send"]
        assert outputs, "expected websocket.send messages"
        data = json.loads(outputs[-1]["text"])  # last send should be OUTPUT
        assert data["type"] == "OUTPUT"
        assert data["result"] == "out:hi"

    def test_invalid_json(self, app):
        client = ASGIWebSocketClient(app, path="/ws")
        sent = client.send_text("{not json}")
        errs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(e.get("type") == "ERROR" and "Invalid JSON" in e.get("message", "") for e in errs)


class TestWebSocketStrict:
    @pytest.fixture
    def app_strict(self, mock_agent, tmp_path):
        from connectonion.host import _make_app, SessionStorage
        storage = SessionStorage(str(tmp_path / ".co" / "session_results.jsonl"))
        return _make_app(mock_agent, trust="strict", result_ttl=3600)

    def test_strict_requires_signature(self, app_strict):
        client = ASGIWebSocketClient(app_strict)
        msg = json.dumps({"type": "INPUT", "prompt": "hi"})
        sent = client.send_text(msg)
        errs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(e.get("type") == "ERROR" and e.get("message", "").startswith("unauthorized") for e in errs)

    def test_strict_valid_signature(self, app_strict):
        from nacl.signing import SigningKey
        signing_key = SigningKey.generate()
        public_key = f"0x{signing_key.verify_key.encode().hex()}"
        payload = {"prompt": "hi", "timestamp": time.time()}
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = f"0x{signing_key.sign(canonical.encode()).signature.hex()}"

        data = {"type": "INPUT", "payload": payload, "from": public_key, "signature": signature}

        client = ASGIWebSocketClient(app_strict)
        sent = client.send_text(json.dumps(data))
        outputs = [json.loads(m["text"]) for m in sent if m.get("type") == "websocket.send"]
        assert any(o.get("type") == "OUTPUT" and o.get("result") == "out:hi" for o in outputs)

    def test_strict_invalid_signature(self, app_strict):
        from nacl.signing import SigningKey
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
    def app_strict_bw(self, mock_agent, tmp_path):
        from connectonion.host import _make_app, SessionStorage
        storage = SessionStorage(str(tmp_path / ".co" / "session_results.jsonl"))
        return _make_app(mock_agent, trust="strict", result_ttl=3600, blacklist=["0xbad"], whitelist=["0xgood"])

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

