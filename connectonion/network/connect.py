"""
Purpose: Client interface for connecting to remote agents with real-time UI updates

Lifecycle (Client Side):
  1. connect(address) creates RemoteAgent instance
  2. agent.input(prompt) opens WebSocket to relay /ws/input endpoint
  3. Sends INPUT message: {type: "INPUT", input_id, to, prompt, session?}
  4. Receives streaming events: tool_call, tool_result, thinking, assistant
  5. Receives final OUTPUT: {type: "OUTPUT", result, session} or ask_user
  6. Returns Response(text, done) - done=False means agent asked a question

Message Flow:
  Client → /ws/input → Relay → forwards to Agent's /ws/announce connection
  Agent processes → sends OUTPUT → Relay resolves pending_outputs future
  Relay → forwards OUTPUT → Client receives response

Related Files:
  - oo-api/relay/routes.py: Relay server WebSocket endpoints
  - connectonion/network/relay.py: Agent-side relay connection (serve_loop)
  - connectonion-ts/src/connect.ts: TypeScript equivalent of this file

LLM-Note:
  Dependencies: imports from [asyncio, json, uuid, time, websockets, address, dataclasses]
  Data flow: connect(address) → RemoteAgent → input() → WebSocket /ws/input → events → Response
  State/Effects: current_session synced from server | ui transforms server events
  Integration: exposes connect(), RemoteAgent with .input(), .input_async(), .ui, .status
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .. import address as addr


@dataclass
class Response:
    """Response from remote agent."""
    text: str       # Agent's response or question
    done: bool      # True = complete, False = needs more input (agent asked a question)


class RemoteAgent:
    """
    Interface to a remote agent with real-time UI updates.

    Supports:
    - WebSocket streaming for real-time events
    - Session state synced from server
    - UI events transformed for rendering
    - Multi-turn conversations

    Usage:
        agent = connect("0x...")
        response = agent.input("Book a flight")
        print(response.text)   # "Which date?"
        print(response.done)   # False (agent asked a question)
        print(agent.ui)        # All events for rendering
    """

    def __init__(
        self,
        agent_address: str,
        *,
        keys: Optional[Dict[str, Any]] = None,
        relay_url: str = "wss://oo.openonion.ai"
    ):
        self.address = agent_address
        self._keys = keys
        self._relay_url = relay_url.rstrip("/")
        self._status = "idle"
        self._current_session: Optional[Dict[str, Any]] = None
        self._ui_events: List[Dict[str, Any]] = []

    @property
    def status(self) -> str:
        """Current status: 'idle' | 'working' | 'waiting'"""
        return self._status

    @property
    def current_session(self) -> Optional[Dict[str, Any]]:
        """Session state synced from server (read-only)."""
        return self._current_session

    @property
    def ui(self) -> List[Dict[str, Any]]:
        """UI events for rendering. One type = one component.

        Server events are transformed:
        - tool_call + tool_result merged into single UI item
        - user_input → type: 'user'
        - assistant → type: 'agent'
        """
        return self._ui_events

    def input(self, prompt: str, timeout: float = 60.0) -> Response:
        """
        Send prompt to remote agent and get response.

        Returns Response(text, done) where:
        - done=True: Task complete
        - done=False: Agent asked a question, send another input to answer

        Args:
            prompt: Task/prompt to send
            timeout: Seconds to wait for response (default 60)

        Returns:
            Response with text and done flag

        Example:
            >>> response = agent.input("Book a flight to Tokyo")
            >>> if not response.done:
            ...     response = agent.input("March 15")  # Answer the question
        """
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "input() cannot be used inside async context. "
                "Use 'await agent.input_async()' instead."
            )
        except RuntimeError as e:
            if "input() cannot be used" in str(e):
                raise
        return asyncio.run(self._stream_input(prompt, timeout))

    async def input_async(self, prompt: str, timeout: float = 60.0) -> Response:
        """Async version of input()."""
        return await self._stream_input(prompt, timeout)

    def reset(self) -> None:
        """Clear conversation and start fresh."""
        self._current_session = None
        self._ui_events = []
        self._status = "idle"

    async def _stream_input(self, prompt: str, timeout: float) -> Response:
        """Send prompt via WebSocket and stream events."""
        import websockets

        self._status = "working"

        # Add user event to UI
        self._add_ui_event({
            "type": "user",
            "content": prompt
        })

        # Connect to relay's input endpoint
        ws_url = f"{self._relay_url}/ws/input"

        # Generate input_id for routing/response matching
        import uuid
        input_id = str(uuid.uuid4())

        # Build the INPUT message
        input_msg = {
            "type": "INPUT",
            "input_id": input_id,
            "prompt": prompt,
            "to": self.address,
            "timestamp": int(time.time())
        }

        # Add session for conversation continuation
        if self._current_session:
            input_msg["session"] = self._current_session

        # Sign if keys provided
        if self._keys:
            payload = {"prompt": prompt, "to": self.address, "timestamp": input_msg["timestamp"]}
            canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
            signature = addr.sign(self._keys, canonical.encode())
            input_msg["payload"] = payload
            input_msg["from"] = self._keys["address"]
            input_msg["signature"] = signature.hex()

        try:
            async with websockets.connect(ws_url) as ws:
                await ws.send(json.dumps(input_msg))

                # Stream events until OUTPUT or timeout
                result_text = ""
                done = True

                while True:
                    # Wrap recv in timeout to prevent hanging indefinitely
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    event = json.loads(msg)
                    event_type = event.get("type")

                    if event_type == "OUTPUT":
                        # Final result
                        result_text = event.get("result", "")
                        self._current_session = event.get("session")
                        self._status = "idle"

                        # Add agent response to UI
                        self._add_ui_event({
                            "type": "agent",
                            "content": result_text
                        })
                        break

                    elif event_type == "ERROR":
                        self._status = "idle"
                        raise ConnectionError(f"Agent error: {event.get('message', event.get('error'))}")

                    elif event_type == "ask_user":
                        # Agent is asking a question - return done=False so caller sends another input()
                        self._status = "waiting"
                        done = False
                        result_text = event.get("text", "")

                        # Add ask_user event to UI
                        self._add_ui_event({
                            "type": "ask_user",
                            "text": event.get("text"),
                            "options": event.get("options")
                        })
                        break

                    else:
                        # Stream event (tool_call, tool_result, thinking, etc.)
                        self._handle_stream_event(event)

                return Response(text=result_text, done=done)

        except asyncio.TimeoutError:
            self._status = "idle"
            raise TimeoutError(f"Request timed out after {timeout}s")

    def _handle_stream_event(self, event: Dict[str, Any]) -> None:
        """Handle streaming event and update UI."""
        event_type = event.get("type")

        if event_type == "tool_call":
            # Add new tool_call UI event with running status
            self._add_ui_event({
                "type": "tool_call",
                "id": event.get("id"),
                "name": event.get("name"),
                "args": event.get("args"),
                "status": "running"
            })

        elif event_type == "tool_result":
            # Find and update existing tool_call by id
            tool_id = event.get("id")
            for ui_event in self._ui_events:
                if ui_event.get("type") == "tool_call" and ui_event.get("id") == tool_id:
                    ui_event["status"] = "done" if event.get("status") == "success" else "error"
                    ui_event["result"] = event.get("result")
                    break

        elif event_type == "thinking":
            self._add_ui_event({"type": "thinking"})

        elif event_type == "user_input":
            # Already added when input() called, skip
            pass

        elif event_type == "assistant":
            self._add_ui_event({
                "type": "agent",
                "content": event.get("content")
            })

        elif event_type == "llm_call":
            # Internal event, add thinking indicator if not already present
            if not any(e.get("type") == "thinking" for e in self._ui_events[-3:]):
                self._add_ui_event({"type": "thinking"})

    def _add_ui_event(self, event: Dict[str, Any]) -> None:
        """Add event to UI with auto-generated id."""
        if "id" not in event:
            event["id"] = str(len(self._ui_events) + 1)
        self._ui_events.append(event)

    def __repr__(self):
        short = self.address[:12] + "..." if len(self.address) > 12 else self.address
        return f"RemoteAgent({short})"


def connect(
    address: str,
    *,
    keys: Optional[Dict[str, Any]] = None,
    relay_url: str = "wss://oo.openonion.ai"
) -> RemoteAgent:
    """
    Connect to a remote agent.

    Args:
        address: Agent's public key address (0x...)
        keys: Signing keys from address.load() - required for strict trust agents
        relay_url: Relay server base URL (default: production)

    Returns:
        RemoteAgent interface with real-time UI updates

    Example:
        >>> from connectonion import connect
        >>>
        >>> agent = connect("0x3d4017c3...")
        >>> response = agent.input("Book a flight")
        >>> print(response.text)   # "Which date?"
        >>> print(response.done)   # False
        >>> print(agent.ui)        # All events for rendering
        >>> print(agent.status)    # 'waiting'
        >>>
        >>> response = agent.input("March 15")
        >>> print(response.text)   # "Booked! Confirmation #ABC123"
        >>> print(response.done)   # True
    """
    return RemoteAgent(address, keys=keys, relay_url=relay_url)
