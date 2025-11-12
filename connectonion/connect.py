"""
Purpose: Client interface for connecting to remote agents via relay network using INPUT/OUTPUT protocol
LLM-Note:
  Dependencies: imports from [asyncio, json, uuid, websockets] | imported by [__init__.py, tests/test_connect.py, examples/] | tested by [tests/test_connect.py, tests/integration/manual/network_connect_manual.py]
  Data flow: user calls connect(address, relay_url) → creates RemoteAgent instance → user calls .input(prompt) → _send_task() creates WebSocket to relay /ws/input → sends INPUT message with {type, input_id, to, prompt} → waits for OUTPUT response from relay → returns result string OR raises ConnectionError
  State/Effects: establishes temporary WebSocket connection per task (no persistent connection) | sends INPUT messages to relay | receives OUTPUT/ERROR messages | no file I/O or global state | asyncio.run() blocks on .input(), await on .input_async()
  Integration: exposes connect(address, relay_url), RemoteAgent class with .input(prompt, timeout), .input_async(prompt, timeout) | default relay_url="wss://oo.openonion.ai/ws/announce" | address format: 0x + 64 hex chars (Ed25519 public key) | complements Agent.serve() which listens for INPUT on relay | Protocol: INPUT type with to/prompt fields → OUTPUT type with input_id/result fields
  Performance: creates new WebSocket connection per input() call (no connection pooling) | default timeout=30s | async under the hood (asyncio.run wraps for sync API) | no caching or retry logic
  Errors: raises ImportError if websockets not installed | raises ConnectionError for ERROR responses from relay | raises ConnectionError for unexpected response types | asyncio.TimeoutError if no response within timeout | WebSocket connection errors bubble up

Connect to remote agents on the network.

Simple function-based API for using remote agents.
"""

import asyncio
import json
import uuid


class RemoteAgent:
    """
    Interface to a remote agent.

    Minimal MVP: Just input() method.
    """

    def __init__(self, address: str, relay_url: str):
        self.address = address
        self._relay_url = relay_url

    def input(self, prompt: str, timeout: float = 30.0) -> str:
        """
        Send task to remote agent and get response (sync version).

        Use this in normal synchronous code.
        For async code, use input_async() instead.

        Args:
            prompt: Task/prompt to send
            timeout: Seconds to wait for response (default 30)

        Returns:
            Agent's response string

        Example:
            >>> translator = connect("0x3d40...")
            >>> result = translator.input("Translate 'hello' to Spanish")
        """
        return asyncio.run(self._send_task(prompt, timeout))

    async def input_async(self, prompt: str, timeout: float = 30.0) -> str:
        """
        Send task to remote agent and get response (async version).

        Use this when calling from async code.

        Args:
            prompt: Task/prompt to send
            timeout: Seconds to wait for response (default 30)

        Returns:
            Agent's response string

        Example:
            >>> remote = connect("0x3d40...")
            >>> result = await remote.input_async("Translate 'hello' to Spanish")
        """
        return await self._send_task(prompt, timeout)

    async def _send_task(self, prompt: str, timeout: float) -> str:
        """
        Send input via relay and wait for output.

        MVP: Uses relay to route INPUT/OUTPUT messages between agents.
        """
        import websockets

        input_id = str(uuid.uuid4())

        # Connect to relay input endpoint
        relay_input_url = self._relay_url.replace("/ws/announce", "/ws/input")

        async with websockets.connect(relay_input_url) as ws:
            # Send INPUT message
            input_message = {
                "type": "INPUT",
                "input_id": input_id,
                "to": self.address,
                "prompt": prompt
            }

            await ws.send(json.dumps(input_message))

            # Wait for OUTPUT
            response_data = await asyncio.wait_for(ws.recv(), timeout=timeout)
            response = json.loads(response_data)

            # Return result
            if response.get("type") == "OUTPUT" and response.get("input_id") == input_id:
                return response.get("result", "")
            elif response.get("type") == "ERROR":
                raise ConnectionError(f"Agent error: {response.get('error')}")
            else:
                raise ConnectionError(f"Unexpected response: {response}")

    def __repr__(self):
        short = self.address[:12] + "..." if len(self.address) > 12 else self.address
        return f"RemoteAgent({short})"


def connect(address: str, relay_url: str = "wss://oo.openonion.ai/ws/announce") -> RemoteAgent:
    """
    Connect to a remote agent.

    Args:
        address: Agent's public key address (0x...)
        relay_url: Relay server URL (default: production)

    Returns:
        RemoteAgent interface

    Example:
        >>> from connectonion import connect
        >>> translator = connect("0x3d4017c3...")
        >>> result = translator.input("Translate 'hello' to Spanish")
    """
    return RemoteAgent(address, relay_url)
