"""
E2E test: Two agents communicate via relay only.

Tests the full relay path: Agent B hosts on relay, Agent A connects
to Agent B via relay and exchanges messages.

Requirements:
  - Relay server running (default: wss://oo.openonion.ai)
  - No direct network access between agents (relay-only)

Usage:
  pytest tests/e2e/test_relay_e2e.py -v -s

Set RELAY_URL to override the relay server:
  RELAY_URL=ws://localhost:8080 pytest tests/e2e/test_relay_e2e.py -v -s
"""

import os
import time
import threading
import pytest

from connectonion import Agent, connect
from connectonion.network.host.server import host
from connectonion.network import address

RELAY_URL = os.environ.get("RELAY_URL", "wss://oo.openonion.ai")

# Generate ephemeral keys for test agents
AGENT_B_KEYS = address.generate()
AGENT_B_ADDRESS = AGENT_B_KEYS["address"]


def _create_agent_b():
    """Factory for Agent B — a simple echo agent."""
    return Agent(
        "test-relay-echo",
        system_prompt="You are a test echo agent. Repeat back exactly what the user says, prefixed with 'ECHO: '.",
        model="co/gemini-2.0-flash",
        quiet=True,
        log=False,
    )


def _start_agent_b(port: int, ready_event: threading.Event):
    """Start Agent B in a background thread."""
    # Save agent B keys to a temp .co dir
    import tempfile
    from pathlib import Path

    co_dir = Path(tempfile.mkdtemp()) / ".co"
    co_dir.mkdir()
    address.save(AGENT_B_KEYS, co_dir)

    # Signal ready after brief delay (host() blocks, so signal before)
    def signal_ready():
        time.sleep(3)  # Wait for server + relay registration
        ready_event.set()

    threading.Thread(target=signal_ready, daemon=True).start()

    host(
        _create_agent_b,
        port=port,
        trust="open",
        relay_url=RELAY_URL,
        co_dir=co_dir,
    )


@pytest.mark.e2e
@pytest.mark.network
class TestRelayE2E:
    """E2E tests for relay-mediated agent communication."""

    @pytest.fixture(autouse=True)
    def start_agent_b(self):
        """Start Agent B as a background server."""
        ready = threading.Event()
        port = 18923  # Use uncommon port to avoid conflicts

        thread = threading.Thread(
            target=_start_agent_b,
            args=(port, ready),
            daemon=True,
        )
        thread.start()

        # Wait for agent to be ready (registered on relay)
        assert ready.wait(timeout=15), "Agent B failed to start within 15s"
        # Extra time for relay registration
        time.sleep(2)

        yield

    def test_connect_and_input_via_relay(self):
        """Agent A connects to Agent B via relay and gets a response."""
        agent_b = connect(AGENT_B_ADDRESS, relay_url=RELAY_URL)

        # Force relay path (no direct connection)
        agent_b._resolved_endpoint = None
        agent_b._endpoint_resolved = True

        response = agent_b.input("hello world", timeout=60)
        assert response.text, "Expected non-empty response"
        assert response.done, "Expected response to be done"
        print(f"  Response: {response.text[:100]}")

    def test_multiturn_via_relay(self):
        """Multi-turn conversation through relay preserves session."""
        agent_b = connect(AGENT_B_ADDRESS, relay_url=RELAY_URL)
        agent_b._resolved_endpoint = None
        agent_b._endpoint_resolved = True

        # Turn 1: Ask agent to remember something
        r1 = agent_b.input("Remember the number 7742.", timeout=60)
        assert r1.done
        print(f"  Turn 1: {r1.text[:80]}")

        # Turn 2: Ask what was remembered
        r2 = agent_b.input("What number did I ask you to remember?", timeout=60)
        assert r2.done
        print(f"  Turn 2: {r2.text[:80]}")

        # Agent should recall the number
        assert "7742" in r2.text, f"Expected '7742' in response, got: {r2.text[:200]}"

    def test_two_independent_clients_via_relay(self):
        """Two clients connect to same agent independently via relay."""
        client_1 = connect(AGENT_B_ADDRESS, relay_url=RELAY_URL)
        client_1._resolved_endpoint = None
        client_1._endpoint_resolved = True

        client_2 = connect(AGENT_B_ADDRESS, relay_url=RELAY_URL)
        client_2._resolved_endpoint = None
        client_2._endpoint_resolved = True

        # Each client gets independent responses
        r1 = client_1.input("Say exactly: CLIENT_ONE", timeout=60)
        r2 = client_2.input("Say exactly: CLIENT_TWO", timeout=60)

        assert r1.done and r2.done
        print(f"  Client 1: {r1.text[:80]}")
        print(f"  Client 2: {r2.text[:80]}")
