"""
E2E tests: agent server + direct/relay/HTTP connectivity.

Starts the agent in a background thread, then tests:
  1. Direct WebSocket via SDK
  2. Relay single request via SDK
  3. Relay multi-turn conversation
  4. Raw WebSocket session_id verification
  5. HTTP POST /input with signed request
  6. Disconnect mid-task + reconnect
  7. Approval flow via WebSocket
  8. Disconnect during approval + reconnect

Usage:
  pytest tests/e2e/test_relay_e2e.py -v -s
"""

import json
import os
import tempfile
import time
import threading
import uuid
import asyncio
import urllib.request

import pytest
import websockets

from connectonion import Agent, connect, address
from connectonion.address import sign
from connectonion.network.host.server import host

RELAY_URL = os.environ.get("RELAY_URL", "wss://oo.openonion.ai")
PORT = 18923
LOCAL_WS = f"ws://127.0.0.1:{PORT}/ws"
LOCAL_HTTP = f"http://127.0.0.1:{PORT}"


def slow_task(agent, seconds: int = 5) -> str:
    """Run a task that takes several seconds. Use when user asks for a slow or long task.

    Args:
        seconds: how many seconds to work (default 5)
    """
    for i in range(seconds):
        agent.io.send({"type": "progress", "step": i + 1, "total": seconds})
        time.sleep(1)
    return f"Completed {seconds}-second task"


def confirm_action(agent, action: str) -> str:
    """Ask user to confirm before doing something. Use when user asks you to do something that needs confirmation.

    Args:
        action: description of what needs confirmation
    """
    agent.io.send({
        "type": "ask_user",
        "question": f"Confirm: {action}?",
        "options": ["yes", "no"],
    })
    response = agent.io.receive()
    answer = response.get("answer", "no")
    if answer == "yes":
        return f"User confirmed: {action}"
    return f"User declined: {action}"


def _build_connect_msg(keys, session_id=None):
    """Build a signed CONNECT message."""
    session_id = session_id or str(uuid.uuid4())
    ts = int(time.time())
    payload = {"to": keys["address"], "timestamp": ts}
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    sig = sign(keys, canonical.encode())
    return {
        "type": "CONNECT",
        "to": keys["address"],
        "session_id": session_id,
        "timestamp": ts,
        "payload": payload,
        "from": keys["address"],
        "signature": sig.hex(),
    }


async def _ws_connect_and_input(ws_url, keys, prompt, session_id=None):
    """Connect, authenticate, send INPUT, return (ws, session_id)."""
    session_id = session_id or str(uuid.uuid4())
    ws = await websockets.connect(ws_url)

    await ws.send(json.dumps(_build_connect_msg(keys, session_id)))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
        event = json.loads(raw)
        if event.get("type") == "CONNECTED":
            break
        if event.get("type") == "ERROR":
            raise RuntimeError(f"CONNECT failed: {event}")

    await ws.send(json.dumps({"type": "INPUT", "prompt": prompt}))
    return ws, session_id


@pytest.fixture(scope="module")
def agent_server():
    """Start agent server in background, yield (address, keys), tear down."""
    keys = address.generate()
    co_dir = tempfile.mkdtemp()
    from pathlib import Path
    co_path = Path(co_dir) / ".co"
    co_path.mkdir()
    address.save(keys, co_path)

    def create_agent():
        return Agent(
            "e2e-relay-test",
            system_prompt="You are a test agent. Keep answers very short. Use slow_task when asked for slow/long tasks. Use confirm_action when asked to do something that needs confirmation.",
            model="co/gemini-2.5-flash",
            tools=[slow_task, confirm_action],
            quiet=True,
            log=False,
        )

    thread = threading.Thread(
        target=host,
        kwargs=dict(
            create_agent=create_agent,
            port=PORT,
            trust="open",
            relay_url=RELAY_URL,
            co_dir=co_path,
        ),
        daemon=True,
    )
    thread.start()

    # Poll /health until server is up
    for _ in range(30):
        try:
            urllib.request.urlopen(f"{LOCAL_HTTP}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        pytest.fail("Agent server did not start within 15s")

    # Extra time for relay registration
    time.sleep(3)

    yield keys

    # daemon thread dies with process


@pytest.mark.e2e
@pytest.mark.network
class TestRelayE2E:

    def test_direct_websocket(self, agent_server):
        """Direct WebSocket connection via SDK."""
        keys = agent_server
        agent = connect(keys["address"], keys=keys)
        agent._resolved_endpoint = LOCAL_WS
        agent._endpoint_resolved = True

        response = agent.input("Say exactly: hello direct", timeout=30)
        assert response.text
        assert response.done

    def test_relay_single_request(self, agent_server):
        """Single request through relay via SDK."""
        keys = agent_server
        agent = connect(keys["address"], keys=keys, relay_url=RELAY_URL)
        agent._resolved_endpoint = None
        agent._endpoint_resolved = True

        response = agent.input("Say exactly: hello relay", timeout=60)
        assert response.text
        assert response.done

    def test_relay_multiturn(self, agent_server):
        """Multi-turn conversation through relay preserves session."""
        keys = agent_server
        agent = connect(keys["address"], keys=keys, relay_url=RELAY_URL)
        agent._resolved_endpoint = None
        agent._endpoint_resolved = True

        r1 = agent.input("Remember this number: 7742. Just confirm.", timeout=60)
        assert r1.done

        r2 = agent.input("What number did I ask you to remember?", timeout=60)
        assert r2.done
        assert "7742" in r2.text

    def test_raw_websocket_session_id(self, agent_server):
        """Every WebSocket event must carry session_id."""
        keys = agent_server
        session_id = str(uuid.uuid4())
        ts = int(time.time())

        payload = {"to": keys["address"], "timestamp": ts}
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        sig = sign(keys, canonical.encode())

        connect_msg = {
            "type": "CONNECT",
            "to": keys["address"],
            "session_id": session_id,
            "timestamp": ts,
            "payload": payload,
            "from": keys["address"],
            "signature": sig.hex(),
        }

        async def run():
            ws_url = f"{RELAY_URL}/ws/input"
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps(connect_msg))

                # Wait for CONNECTED
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                    event = json.loads(raw)
                    if event.get("type") == "CONNECTED":
                        assert event.get("session_id")
                        break
                    elif event.get("type") == "ERROR":
                        pytest.fail(f"Got ERROR: {event}")

                # Send INPUT
                await ws.send(json.dumps({
                    "type": "INPUT",
                    "input_id": str(uuid.uuid4()),
                    "prompt": "What is 2+2? Answer with just the number.",
                }))

                # Check every event has session_id
                missing = []
                while True:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    event = json.loads(raw)
                    if not event.get("session_id"):
                        missing.append(event.get("type"))
                    if event.get("type") == "OUTPUT":
                        break

                assert not missing, f"Events missing session_id: {missing}"

        asyncio.run(run())

    def test_http_post_input(self, agent_server):
        """HTTP POST /input with signed request."""
        keys = agent_server
        ts = int(time.time())
        prompt = "What is 1+1? Answer with just the number."

        payload = {"prompt": prompt, "timestamp": ts}
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        sig = sign(keys, canonical.encode())

        body = {
            "payload": payload,
            "from": keys["address"],
            "signature": sig.hex(),
        }

        req = urllib.request.Request(
            f"{LOCAL_HTTP}/input",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())

        assert result["status"] == "done"
        assert result["session_id"]
        assert result["result"]

    def test_disconnect_reconnect(self, agent_server):
        """Disconnect during slow task, reconnect to same session, get OUTPUT."""
        keys = agent_server

        async def run():
            session_id = str(uuid.uuid4())
            ws, session_id = await _ws_connect_and_input(
                LOCAL_WS, keys, "Run slow_task for 5 seconds", session_id
            )

            # Wait for at least one progress event
            got_progress = False
            for _ in range(20):
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                event = json.loads(raw)
                if event.get("type") == "progress":
                    got_progress = True
                    break

            assert got_progress, "No progress event received"

            # Disconnect mid-task
            await ws.close()
            await asyncio.sleep(1)

            # Reconnect to same session
            ws2 = await websockets.connect(LOCAL_WS)
            await ws2.send(json.dumps(_build_connect_msg(keys, session_id)))

            while True:
                raw = await asyncio.wait_for(ws2.recv(), timeout=15)
                event = json.loads(raw)
                if event.get("type") == "CONNECTED":
                    assert event["status"] == "executing", f"Expected executing, got {event['status']}"
                    break

            # Wait for OUTPUT
            got_output = False
            for _ in range(30):
                raw = await asyncio.wait_for(ws2.recv(), timeout=10)
                event = json.loads(raw)
                if event.get("type") == "OUTPUT":
                    got_output = True
                    break

            await ws2.close()
            assert got_output, "Never received OUTPUT after reconnect"

        asyncio.run(run())

    def test_approval_flow(self, agent_server):
        """Agent asks for confirmation, client approves via WebSocket."""
        keys = agent_server

        async def run():
            ws, session_id = await _ws_connect_and_input(
                LOCAL_WS, keys, "Please confirm the action: delete temp files"
            )

            # Wait for ask_user event
            ask_event = None
            for _ in range(30):
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                event = json.loads(raw)
                if event.get("type") == "ask_user":
                    ask_event = event
                    break

            assert ask_event, "No ask_user event received"

            # Send approval
            await ws.send(json.dumps({"answer": "yes"}))

            # Wait for OUTPUT
            got_output = False
            for _ in range(30):
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                event = json.loads(raw)
                if event.get("type") == "OUTPUT":
                    got_output = True
                    break

            await ws.close()
            assert got_output, "Never received OUTPUT after approval"

        asyncio.run(run())

    def test_disconnect_during_approval(self, agent_server):
        """Disconnect while agent waits for approval, reconnect and approve."""
        keys = agent_server

        async def run():
            session_id = str(uuid.uuid4())
            ws, session_id = await _ws_connect_and_input(
                LOCAL_WS, keys, "Please confirm the action: restart server", session_id
            )

            # Wait for ask_user event
            got_ask = False
            for _ in range(30):
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                event = json.loads(raw)
                if event.get("type") == "ask_user":
                    got_ask = True
                    break

            assert got_ask, "No ask_user event received"

            # Disconnect WITHOUT answering
            await ws.close()
            await asyncio.sleep(1)

            # Reconnect to same session
            ws2 = await websockets.connect(LOCAL_WS)
            await ws2.send(json.dumps(_build_connect_msg(keys, session_id)))

            while True:
                raw = await asyncio.wait_for(ws2.recv(), timeout=15)
                event = json.loads(raw)
                if event.get("type") == "CONNECTED":
                    assert event["status"] == "executing", f"Expected executing, got {event['status']}"
                    break

            # Send approval on reconnected session
            await ws2.send(json.dumps({"answer": "yes"}))

            # Wait for OUTPUT
            got_output = False
            for _ in range(30):
                raw = await asyncio.wait_for(ws2.recv(), timeout=10)
                event = json.loads(raw)
                if event.get("type") == "OUTPUT":
                    got_output = True
                    break

            await ws2.close()
            assert got_output, "Never received OUTPUT after reconnect + approval"

        asyncio.run(run())
