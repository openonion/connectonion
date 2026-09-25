"""`connect(addr).input(..., timeout=60)` hung for 519 seconds.

A tester hosted the co-ai template on 1.8.8b7 and asked it, from Python, to
`cat` a file outside the project. The agent sent `approval_needed` and waited
for an answer. The Python client had no branch for that event, so it went on
reading; and `timeout` was applied to each `recv()`, so every stream frame and
every keepalive PING started the 60 seconds again. Nothing on either side was
ever going to end the call.

Three things were missing, and each is pinned here against a fake socket:

1. `timeout` is a deadline for the whole call. It ends in a TimeoutError that
   names the session, so the caller can stop or resume the turn.
2. A request the agent is waiting on reaches the caller: `on_approval=` and
   `on_ask=` answer it in the same call, with the `request_id` a Host from
   #1692 on requires; without a callback an approval fails fast, saying what is
   pending and how to answer it (`respond_to_approval`), and a question returns
   `done=False` so the next `input()` is sent as its answer.
3. `stop()` interrupts the running turn, and a connection that closes
   mid-turn is reopened on the same session: the turn is picked up if the Host
   still has it, and otherwise the error names the session instead of
   surfacing a bare `ConnectionClosedError 1012`.
"""

import asyncio
import json
import sys
import time
from unittest.mock import patch

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from connectonion.network.connect import (
    ApprovalPendingError,
    RemoteAgent,
    TurnLostError,
    TurnTimeoutError,
)

ADDRESS = "0x" + "a" * 64


class FakeSocket:
    """One WebSocket: replies to CONNECT, then plays a script after INPUT.

    Script items are JSON-able dicts, an exception to raise from recv(), or
    ("every", seconds, frame) to repeat a frame forever — a stream that never
    ends, which is what a turn waiting on an approval looks like on the wire.
    Frames the client sends are kept in `sent`, and a reply to one of them can
    be scripted with `on_send`.
    """

    def __init__(self, connected_status="new", script=(), on_send=None):
        self.sent = []
        self._queue = asyncio.Queue()
        self._connected_status = connected_status
        self._script = list(script)
        self._on_send = on_send or {}
        self._repeat = None

    def __await__(self):
        async def _self():
            return self
        return _self().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def close(self):
        pass

    async def send(self, raw):
        frame = json.loads(raw)
        self.sent.append(frame)
        kind = frame.get("type")
        if kind == "CONNECT":
            await self._queue.put({
                "type": "CONNECTED", "session_id": "s1",
                "status": self._connected_status,
            })
            if self._connected_status == "running":
                self._play()
        elif kind == "INPUT":
            self._play()
        for item in self._on_send.pop(kind, []):
            await self._queue.put(item)

    def _play(self):
        for item in self._script:
            if isinstance(item, tuple) and item[0] == "every":
                self._repeat = item[1:]
            else:
                self._queue.put_nowait(item)

    async def recv(self):
        if self._queue.empty() and self._repeat:
            await asyncio.sleep(self._repeat[0])
            return json.dumps(self._repeat[1])
        item = await self._queue.get()
        if isinstance(item, BaseException):
            raise item
        return json.dumps(item)

    def types(self):
        return [frame.get("type") for frame in self.sent]


def _agent():
    agent = RemoteAgent(ADDRESS, keys=False, relay_url="ws://relay.test")
    agent._endpoint_resolved = True  # no /info probe: this test has no network
    return agent


def _closed_1012():
    return ConnectionClosedError(Close(1012, "service restart"), None)


APPROVAL = {
    "type": "approval_needed", "id": "req-7", "tool": "bash",
    "arguments": {"command": "cat /outside/file"},
}
ASK = {"type": "ask_user", "id": "ask-3", "question": "Which date?",
       "options": ["Mon", "Tue"]}
OUTPUT = {"type": "OUTPUT", "result": "done", "session": {"session_id": "s1"}}


class TestTimeoutIsADeadline:

    def test_frames_that_keep_arriving_do_not_extend_the_call(self):
        """The 519-second hang: a PING and a stream event every 50 ms."""
        ws = FakeSocket(script=[("every", 0.05, {"type": "PING"})])
        agent = _agent()

        started = time.monotonic()
        with patch("websockets.connect", return_value=ws):
            with pytest.raises(TimeoutError) as caught:
                asyncio.run(agent.input_async("run cat /outside/file", timeout=0.4))

        assert time.monotonic() - started < 2
        assert isinstance(caught.value, TurnTimeoutError)
        assert caught.value.session_id == "s1"
        assert "s1" in str(caught.value) and "stop()" in str(caught.value)

    def test_the_keepalive_is_answered(self):
        ws = FakeSocket(script=[{"type": "PING"}, OUTPUT])
        with patch("websockets.connect", return_value=ws):
            asyncio.run(_agent().input_async("hi", timeout=5))

        assert "PONG" in ws.types()


class TestAnApprovalReachesTheCaller:

    def test_on_approval_answers_with_the_request_id(self):
        ws = FakeSocket(script=[APPROVAL], on_send={"APPROVAL_RESPONSE": [OUTPUT]})
        seen = []

        def approve(event):
            seen.append(event)
            return True

        with patch("websockets.connect", return_value=ws):
            response = asyncio.run(
                _agent().input_async("go", timeout=5, on_approval=approve)
            )

        assert response.text == "done"
        assert seen[0]["tool"] == "bash"
        answer = next(f for f in ws.sent if f["type"] == "APPROVAL_RESPONSE")
        assert answer["request_id"] == "req-7"
        assert answer["approved"] is True
        assert answer["scope"] == "once"

    def test_a_dict_answer_carries_its_scope(self):
        ws = FakeSocket(script=[APPROVAL], on_send={"APPROVAL_RESPONSE": [OUTPUT]})
        with patch("websockets.connect", return_value=ws):
            asyncio.run(_agent().input_async(
                "go", timeout=5,
                on_approval=lambda e: {"approved": False, "scope": "session"},
            ))

        answer = next(f for f in ws.sent if f["type"] == "APPROVAL_RESPONSE")
        assert (answer["approved"], answer["scope"]) == (False, "session")

    def test_without_a_callback_it_fails_fast_and_says_how_to_answer(self):
        # The Host keeps pinging while it waits; the client must not wait too.
        ws = FakeSocket(script=[APPROVAL, ("every", 0.05, {"type": "PING"})])
        agent = _agent()

        started = time.monotonic()
        with patch("websockets.connect", return_value=ws):
            with pytest.raises(ApprovalPendingError) as caught:
                asyncio.run(agent.input_async("go", timeout=30))

        assert time.monotonic() - started < 2
        message = str(caught.value)
        assert "bash" in message and "s1" in message
        assert "respond_to_approval" in message and "on_approval" in message
        assert caught.value.request["id"] == "req-7"
        assert agent.status == "waiting"

    def test_respond_to_approval_reattaches_and_finishes_the_turn(self):
        first = FakeSocket(script=[APPROVAL])
        second = FakeSocket(
            connected_status="running",
            on_send={"APPROVAL_RESPONSE": [OUTPUT]},
        )
        agent = _agent()
        with patch("websockets.connect", side_effect=[first, second]):
            with pytest.raises(ApprovalPendingError):
                asyncio.run(agent.input_async("go", timeout=5))
            response = asyncio.run(agent.respond_to_approval_async(True, timeout=5))

        assert response.text == "done"
        connect = second.sent[0]
        assert connect["type"] == "CONNECT" and connect["session_id"] == "s1"
        assert "INPUT" not in second.types()
        answer = next(f for f in second.sent if f["type"] == "APPROVAL_RESPONSE")
        assert answer["request_id"] == "req-7" and answer["approved"] is True

    def test_respond_to_approval_with_nothing_pending_is_an_error(self):
        with pytest.raises(RuntimeError, match="no approval"):
            asyncio.run(_agent().respond_to_approval_async(True))


class TestAQuestionReachesTheCaller:

    def test_on_ask_answers_with_the_request_id(self):
        ws = FakeSocket(script=[ASK], on_send={"ASK_USER_RESPONSE": [OUTPUT]})
        with patch("websockets.connect", return_value=ws):
            response = asyncio.run(_agent().input_async(
                "book", timeout=5, on_ask=lambda e: "Mon",
            ))

        assert response.done is True
        answer = next(f for f in ws.sent if f["type"] == "ASK_USER_RESPONSE")
        assert answer == {**answer, "request_id": "ask-3", "answer": "Mon"}

    def test_without_a_callback_the_next_input_is_the_answer(self):
        first = FakeSocket(script=[ASK])
        second = FakeSocket(
            connected_status="running",
            on_send={"ASK_USER_RESPONSE": [OUTPUT]},
        )
        agent = _agent()
        with patch("websockets.connect", side_effect=[first, second]):
            asked = asyncio.run(agent.input_async("book", timeout=5))
            answered = asyncio.run(agent.input_async("Tue", timeout=5))

        assert (asked.done, asked.text) == (False, "Which date?")
        assert answered.text == "done"
        assert second.sent[0]["session_id"] == "s1"
        assert "INPUT" not in second.types()
        answer = next(f for f in second.sent if f["type"] == "ASK_USER_RESPONSE")
        assert (answer["request_id"], answer["answer"]) == ("ask-3", "Tue")


class TestStop:

    def test_stop_interrupts_the_turn_in_flight(self):
        ws = FakeSocket(
            script=[{"type": "thinking", "id": "e1"}],
            on_send={"INTERRUPT": [{**OUTPUT, "result": "stopped"}]},
        )
        agent = _agent()

        async def run():
            turn = asyncio.create_task(agent.input_async("count to 400", timeout=5))
            while "INPUT" not in ws.types():
                await asyncio.sleep(0.01)
            assert await agent.stop_async() is True
            return await turn

        with patch("websockets.connect", return_value=ws):
            response = asyncio.run(run())

        assert response.text == "stopped"
        assert ws.types().count("INTERRUPT") == 1

    def test_stop_reaches_a_turn_left_running_by_a_timeout(self):
        running = FakeSocket(script=[("every", 0.05, {"type": "PING"})])
        stopper = FakeSocket(
            connected_status="running",
            on_send={"INTERRUPT": [{**OUTPUT, "result": "stopped"}]},
        )
        agent = _agent()
        with patch("websockets.connect", side_effect=[running, stopper]):
            with pytest.raises(TurnTimeoutError):
                asyncio.run(agent.input_async("go", timeout=0.3))
            assert agent.stop() is True

        assert stopper.sent[0]["session_id"] == "s1"
        assert stopper.types()[-1] == "INTERRUPT"

    def test_stop_with_nothing_running_says_so(self):
        agent = _agent()
        assert agent.stop() is False  # never connected: no session to stop

        agent._session_id = "s1"
        idle = FakeSocket(connected_status="connected")
        with patch("websockets.connect", return_value=idle):
            assert agent.stop() is False
        assert "INTERRUPT" not in idle.types()


class TestAConnectionThatClosesMidTurn:

    def test_the_turn_is_picked_up_on_the_same_session(self):
        first = FakeSocket(script=[{"type": "thinking", "id": "e1"}, _closed_1012()])
        second = FakeSocket(connected_status="running", script=[OUTPUT])
        agent = _agent()
        with patch("websockets.connect", side_effect=[first, second]):
            response = asyncio.run(agent.input_async("count", timeout=5))

        assert response.text == "done"
        connect = second.sent[0]
        assert connect["session_id"] == "s1"
        assert connect["last_msg_id"] == "e1"  # no replay of what was seen
        assert "INPUT" not in second.types()   # the prompt is never run twice

    def test_a_host_that_lost_the_turn_names_the_session(self):
        first = FakeSocket(script=[_closed_1012()])
        restarted = FakeSocket(connected_status="new")
        agent = _agent()
        with patch("websockets.connect", side_effect=[first, restarted]):
            with pytest.raises(ConnectionError) as caught:
                asyncio.run(agent.input_async("count", timeout=5))

        assert isinstance(caught.value, TurnLostError)
        assert caught.value.session_id == "s1"
        assert "s1" in str(caught.value) and "1012" in str(caught.value)
        assert "INPUT" not in restarted.types()

    def test_a_host_that_stays_down_ends_in_a_named_error(self):
        first = FakeSocket(script=[_closed_1012()])
        agent = _agent()
        with patch("websockets.connect", side_effect=[first] + [OSError("refused")] * 5):
            # The module object, not its dotted name: connectonion.network re-exports
            # the connect() function under the module's own name.
            with patch.object(sys.modules["connectonion.network.connect"], "_RECONNECT_DELAYS", (0, 0, 0)):
                with pytest.raises(TurnLostError) as caught:
                    asyncio.run(agent.input_async("count", timeout=5))

        assert "s1" in str(caught.value) and "refused" in str(caught.value)
