"""Deterministic model-free Agent behind the production ACP stdio adapter."""

from __future__ import annotations

import asyncio
import os
import socket
import time
from unittest.mock import patch

from connectonion.cli.co_ai.acp_server import serve_acp
from connectonion.cli.commands import ai_commands


class ACPTestAgent:
    system_prompt = "system"

    def __init__(self) -> None:
        self.io = None
        self.current_session = {"trace": [], "turn": 0}

    def _finish(self, reason: str) -> None:
        event = {
            "type": "turn_result",
            "turn": self.current_session["turn"],
            "reason": reason,
            "usage": None,
        }
        self.current_session["trace"].append(event)
        self.io.send(event)

    def input(self, prompt: str, session=None) -> str:
        if session is not None:
            self.current_session = dict(session)
            self.current_session["messages"] = list(session["messages"])
            self.current_session["trace"] = list(session["trace"])
        print(f"fake agent received: {prompt}", flush=True)
        self.current_session["turn"] += 1
        if prompt == "large":
            result = "x" * 5_000_000
            self._finish("natural")
            return result
        if prompt == "environment":
            result = f"secret inherited: {'ACP_TEST_SECRET' in os.environ}"
            self._finish("natural")
            return result
        if prompt == "approval":
            self.io.send({
                "type": "approval_needed",
                "tool_call_id": "sdk-permission",
                "tool": "write",
                "arguments": {"content": "value"},
            })
            decision = self.io.receive()
            result = f"permission approved: {decision.get('approved') is True}"
            self._finish("natural")
            return result
        if prompt != "block":
            result = f"answer: {prompt}"
            self._finish("natural")
            return result
        while not self.io.receive_all("INTERRUPT"):
            time.sleep(0.01)
        self._finish("interrupted")
        return "late cancelled answer"


def main() -> None:
    ai_commands._create_agent = lambda **_kwargs: ACPTestAgent()
    network_error = RuntimeError("ACP test fixture network access is disabled")
    with (
        patch.object(socket.socket, "connect", side_effect=network_error),
        patch.object(socket.socket, "connect_ex", side_effect=network_error),
        patch.object(socket, "create_connection", side_effect=network_error),
    ):
        asyncio.run(
            serve_acp(
                model="test",
                max_iterations=2,
                yolo=False,
                yolo_turns=2,
            )
        )


if __name__ == "__main__":
    main()
