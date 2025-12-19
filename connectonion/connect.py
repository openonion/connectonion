"""
Purpose: Client interface for connecting to remote agents via HTTP or relay network
LLM-Note:
  Dependencies: imports from [asyncio, json, uuid, time, aiohttp, websockets, address] | imported by [__init__.py, tests/test_connect.py, examples/] | tested by [tests/test_connect.py]
  Data flow: connect(address, keys) → RemoteAgent → input() → discover endpoints → try HTTP first → fallback to relay → return result
  State/Effects: caches discovered endpoint for reuse | optional signing with keys parameter
  Integration: exposes connect(address, keys, relay_url), RemoteAgent class with .input(), .input_async()
  Performance: discovery cached per RemoteAgent instance | HTTPS tried first (direct), relay as fallback

Connect to remote agents on the network.

Smart discovery: tries HTTP endpoints first, falls back to relay.
Always signs requests when keys are provided.
"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from . import address as addr


class RemoteAgent:
    """
    Interface to a remote agent.

    Supports:
    - Discovery via relay API
    - Direct HTTP POST to agent /input endpoint
    - WebSocket relay fallback
    - Signed requests when keys provided
    - Multi-turn conversations via session management

    Usage:
        # Standard Python scripts
        agent = connect("0x...")
        result = agent.input("Hello")

        # Jupyter notebooks or async code
        agent = connect("0x...")
        result = await agent.input_async("Hello")
    """

    def __init__(
        self,
        agent_address: str,
        *,
        keys: Optional[Dict[str, Any]] = None,
        relay_url: str = "wss://oo.openonion.ai/ws/announce"
    ):
        self.address = agent_address
        self._keys = keys
        self._relay_url = relay_url
        self._cached_endpoint: Optional[str] = None
        self._session: Optional[Dict[str, Any]] = None  # Multi-turn conversation state

    def input(self, prompt: str, timeout: float = 30.0) -> str:
        """
        Send task to remote agent and get response (sync version).

        Automatically maintains conversation context across calls.

        Note:
            This method cannot be used inside an async context (e.g., Jupyter notebooks,
            async functions). Use input_async() instead in those environments.

        Args:
            prompt: Task/prompt to send
            timeout: Seconds to wait for response (default 30)

        Returns:
            Agent's response string

        Raises:
            RuntimeError: If called from within a running event loop

        Example:
            >>> translator = connect("0x3d40...")
            >>> result = translator.input("Translate 'hello' to Spanish")
            >>> # Continue conversation
            >>> result2 = translator.input("Now translate it to French")
        """
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "input() cannot be used inside async context (e.g., Jupyter notebooks). "
                "Use 'await agent.input_async()' instead."
            )
        except RuntimeError as e:
            if "input() cannot be used" in str(e):
                raise
            # No running loop - safe to proceed
        return asyncio.run(self._send_task(prompt, timeout))

    async def input_async(self, prompt: str, timeout: float = 30.0) -> str:
        """
        Send task to remote agent and get response (async version).

        Automatically maintains conversation context across calls.

        Args:
            prompt: Task/prompt to send
            timeout: Seconds to wait for response (default 30)

        Returns:
            Agent's response string
        """
        return await self._send_task(prompt, timeout)

    def reset_conversation(self):
        """Clear conversation history and start fresh."""
        self._session = None

    def _sign_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sign a payload if keys are available."""
        if not self._keys:
            return {"prompt": payload.get("prompt", "")}

        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        signature = addr.sign(self._keys, canonical.encode())
        return {
            "payload": payload,
            "from": self._keys["address"],
            "signature": signature.hex()
        }

    async def _discover_endpoints(self) -> List[str]:
        """Query relay API for agent endpoints."""
        import aiohttp

        # Convert wss://oo.openonion.ai/ws/announce to https://oo.openonion.ai
        base_url = self._relay_url.replace("wss://", "https://").replace("ws://", "http://")
        base_url = base_url.replace("/ws/announce", "")

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/api/relay/agents/{self.address}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("online"):
                        return data.get("endpoints", [])
        return []

    def _create_signed_body(self, prompt: str) -> Dict[str, Any]:
        """Create signed request body for agent /input endpoint."""
        payload = {"prompt": prompt, "to": self.address, "timestamp": int(time.time())}
        body = self._sign_payload(payload)
        if self._session:
            body["session"] = self._session
        return body

    async def _send_http(self, endpoint: str, prompt: str, timeout: float) -> str:
        """Send request via direct HTTP POST to agent /input endpoint."""
        import aiohttp

        body = self._create_signed_body(prompt)

        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                f"{endpoint}/input",
                json=body,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                data = await resp.json()
                if not resp.ok:
                    raise ConnectionError(data.get("error", f"HTTP {resp.status}"))
                # Save session for conversation continuation
                if "session" in data:
                    self._session = data["session"]
                return data.get("result", "")

    async def _send_relay(self, prompt: str, timeout: float) -> str:
        """Send request via WebSocket relay."""
        import websockets

        input_id = str(uuid.uuid4())
        relay_input_url = self._relay_url.replace("/ws/announce", "/ws/input")

        async with websockets.connect(relay_input_url) as ws:
            payload = {"prompt": prompt, "to": self.address, "timestamp": int(time.time())}
            signed = self._sign_payload(payload)

            input_message = {
                "type": "INPUT",
                "input_id": input_id,
                "to": self.address,
                **signed
            }

            await ws.send(json.dumps(input_message))

            response_data = await asyncio.wait_for(ws.recv(), timeout=timeout)
            response = json.loads(response_data)

            if response.get("type") == "OUTPUT" and response.get("input_id") == input_id:
                return response.get("result", "")
            elif response.get("type") == "ERROR":
                raise ConnectionError(f"Agent error: {response.get('error')}")
            else:
                raise ConnectionError(f"Unexpected response: {response}")

    async def _send_task(self, prompt: str, timeout: float) -> str:
        """
        Send task using best available connection method.

        Priority:
        1. Cached endpoint (if previously successful)
        2. Discovered HTTPS endpoints
        3. Discovered HTTP endpoints
        4. Relay fallback
        """
        # Try cached endpoint first
        if self._cached_endpoint:
            try:
                return await self._send_http(self._cached_endpoint, prompt, timeout)
            except Exception:
                self._cached_endpoint = None  # Clear failed cache

        # Discover endpoints
        endpoints = await self._discover_endpoints()

        # Sort: HTTPS first, then HTTP
        endpoints.sort(key=lambda e: (0 if e.startswith("https://") else 1))

        # Try each endpoint
        for endpoint in endpoints:
            try:
                result = await self._send_http(endpoint, prompt, timeout)
                self._cached_endpoint = endpoint  # Cache successful endpoint
                return result
            except Exception:
                continue

        # Fallback to relay
        return await self._send_relay(prompt, timeout)

    def __repr__(self):
        short = self.address[:12] + "..." if len(self.address) > 12 else self.address
        return f"RemoteAgent({short})"


def connect(
    address: str,
    *,
    keys: Optional[Dict[str, Any]] = None,
    relay_url: str = "wss://oo.openonion.ai/ws/announce"
) -> RemoteAgent:
    """
    Connect to a remote agent.

    Args:
        address: Agent's public key address (0x...)
        keys: Signing keys from address.load() - required for strict trust agents
        relay_url: Relay server URL (default: production)

    Returns:
        RemoteAgent interface

    Example:
        >>> from connectonion import connect, address
        >>>
        >>> # Simple (unsigned)
        >>> agent = connect("0x3d4017c3...")
        >>> result = agent.input("Hello")
        >>>
        >>> # With signing (for strict trust agents)
        >>> keys = address.load(Path(".co"))
        >>> agent = connect("0x3d4017c3...", keys=keys)
        >>> result = agent.input("Hello")
    """
    return RemoteAgent(address, keys=keys, relay_url=relay_url)
