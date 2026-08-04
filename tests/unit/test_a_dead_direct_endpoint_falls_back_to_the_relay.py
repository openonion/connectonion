"""A direct endpoint that stops answering must not take the agent with it.

#643 made `resolve_endpoint` work for the first time, so clients now reach an
agent on its own address — localhost, LAN, then public — instead of always
going through the relay. The endpoint is resolved once and cached for the life
of the RemoteAgent:

    if self._endpoint_resolved:
        return
    self._endpoint_resolved = True
    self._resolved_endpoint = await resolve_endpoint(...)

and then used with no way back:

    if self._resolved_endpoint:
        ws_url = self._resolved_endpoint
        is_direct = True
    else:
        ws_url = f"{self._relay_url}/ws/input"

So if the agent restarts on another port, or the caller moves off that network,
every later call on that RemoteAgent fails — over a path that worked before
#643, because before #643 resolution never succeeded and everything went
through the relay. That is the regression the change brought with it.

The relay is still there and still reaches the agent. Falling back to it costs
one failed connection; not falling back costs the conversation.

The cached endpoint is forgotten at the same time, so the next call resolves
again rather than retrying a corpse every turn.
"""

import asyncio
import json

import pytest

from connectonion.network.connect import RemoteAgent


AGENT = "0x" + "e" * 64
DEAD = "ws://10.0.0.99:9999/ws"
RELAY = "wss://relay.test"


class FakeWebSocket:
    def __init__(self, script):
        self.script = list(script)
        self.sent = []
        self._outbox = []

    async def send(self, raw):
        message = json.loads(raw)
        self.sent.append(message)
        for trigger, replies in self.script:
            if message.get("type") == trigger:
                for reply in replies:
                    reply = dict(reply)
                    if reply.get("type") == "EXEC_RESULT" and "exec_id" in message:
                        reply["exec_id"] = message["exec_id"]
                    if reply.get("type") == "OUTPUT" and "input_id" in message:
                        reply["input_id"] = message["input_id"]
                    self._outbox.append(reply)

    async def recv(self):
        if not self._outbox:
            raise AssertionError(
                f"waited for a frame nobody sent; sent so far: "
                f"{[m.get('type') for m in self.sent]}")
        return json.dumps(self._outbox.pop(0))

    def __await__(self):
        """`websockets.connect(url)` is awaitable and returns the protocol; the
        code now awaits it before entering, so the stand-in must be too."""
        async def _self():
            return self
        return _self().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


EXEC_OK = [
    ("CONNECT", [{"type": "CONNECTED", "session_id": "s1"}]),
    ("EXEC", [{"type": "EXEC_RESULT", "status": "success", "result": "FROM-RELAY"}]),
]

INPUT_OK = [
    ("CONNECT", [{"type": "CONNECTED", "session_id": "s1"}]),
    ("INPUT", [{"type": "OUTPUT", "result": "FROM-RELAY", "session": {}}]),
]


def _agent_whose_direct_endpoint_is_dead(monkeypatch, script):
    """Connecting to DEAD refuses; the relay answers."""
    import websockets

    relay_socket = FakeWebSocket(script)
    attempts = []

    def connect(url, *a, **k):
        attempts.append(url)
        if url == DEAD:
            raise ConnectionRefusedError("nothing is listening there any more")
        return relay_socket

    monkeypatch.setattr(websockets, "connect", connect)

    agent = RemoteAgent(AGENT, keys=None, relay_url=RELAY)
    agent._endpoint_resolved = True          # already resolved, as after one call
    agent._resolved_endpoint = DEAD
    return agent, attempts, relay_socket


class TestCallFallsBack:

    def test_it_still_returns_a_result(self, monkeypatch):
        agent, _, _ = _agent_whose_direct_endpoint_is_dead(monkeypatch, EXEC_OK)

        assert agent.call("bash", command="pwd").ok

    def test_the_result_came_from_the_relay(self, monkeypatch):
        agent, attempts, _ = _agent_whose_direct_endpoint_is_dead(monkeypatch, EXEC_OK)

        result = agent.call("bash", command="pwd")

        assert "FROM-RELAY" in result.text
        assert attempts == [DEAD, f"{RELAY}/ws/input"], attempts

    def test_the_dead_endpoint_is_forgotten(self, monkeypatch):
        """Otherwise every later call pays for the same refusal first."""
        agent, _, _ = _agent_whose_direct_endpoint_is_dead(monkeypatch, EXEC_OK)

        agent.call("bash", command="pwd")

        assert agent._resolved_endpoint is None


class TestInputFallsBackToo:

    def test_it_still_answers(self, monkeypatch):
        agent, _, _ = _agent_whose_direct_endpoint_is_dead(monkeypatch, INPUT_OK)

        assert "FROM-RELAY" in agent.input("hello").text

    def test_it_tried_direct_first(self, monkeypatch):
        agent, attempts, _ = _agent_whose_direct_endpoint_is_dead(monkeypatch, INPUT_OK)

        agent.input("hello")

        assert attempts[0] == DEAD


class TestTheConnectMessageMatchesThePathItIsSentOn:
    """`_build_connect_message(is_direct)` differs between the two. A fallback
    that reused the direct message would be signed for the wrong recipient."""

    def test_the_relay_gets_a_relay_shaped_connect(self, monkeypatch):
        agent, _, socket = _agent_whose_direct_endpoint_is_dead(monkeypatch, EXEC_OK)

        agent.call("bash", command="pwd")

        sent = [m for m in socket.sent if m.get("type") == "CONNECT"][0]
        expected = agent._build_connect_message(False)
        assert set(sent) == set(expected)


class TestWhatMustNotChange:

    def test_a_working_direct_endpoint_is_not_second_guessed(self, monkeypatch):
        import websockets

        socket = FakeWebSocket(EXEC_OK)
        attempts = []
        monkeypatch.setattr(websockets, "connect",
                            lambda url, *a, **k: (attempts.append(url), socket)[1])

        agent = RemoteAgent(AGENT, keys=None, relay_url=RELAY)
        agent._endpoint_resolved = True
        agent._resolved_endpoint = "ws://10.0.0.5:8797/ws"

        assert agent.call("bash", command="pwd").ok
        assert attempts == ["ws://10.0.0.5:8797/ws"]
        assert agent._resolved_endpoint == "ws://10.0.0.5:8797/ws"

    def test_a_relay_only_agent_is_untouched(self, monkeypatch):
        import websockets

        socket = FakeWebSocket(EXEC_OK)
        attempts = []
        monkeypatch.setattr(websockets, "connect",
                            lambda url, *a, **k: (attempts.append(url), socket)[1])

        agent = RemoteAgent(AGENT, keys=None, relay_url=RELAY)
        agent._endpoint_resolved = True
        agent._resolved_endpoint = None

        assert agent.call("bash", command="pwd").ok
        assert attempts == [f"{RELAY}/ws/input"]

    def test_a_relay_that_also_refuses_still_raises(self, monkeypatch):
        """Falling back is not the same as pretending it worked."""
        import websockets

        def refuse(url, *a, **k):
            raise ConnectionRefusedError(url)

        monkeypatch.setattr(websockets, "connect", refuse)

        agent = RemoteAgent(AGENT, keys=None, relay_url=RELAY)
        agent._endpoint_resolved = True
        agent._resolved_endpoint = DEAD

        with pytest.raises(Exception):
            agent.call("bash", command="pwd")
