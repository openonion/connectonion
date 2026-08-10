"""ACP v1 stdio lifecycle adapter for ``co ai``.

The official ACP SDK owns JSON-RPC routing and schema validation.  This module
only adapts the lifecycle to ConnectOnion: one real coding Agent per ACP
session, an exclusive stdout protocol stream, and fail-closed approvals until
the dedicated permission bridge lands.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from acp import (
    PROTOCOL_VERSION,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    RequestError,
    run_agent,
    update_agent_message_text,
)
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    ClientCapabilities,
    Implementation,
    ResourceContentBlock,
    SessionCapabilities,
    TextContentBlock,
)

from ..._version import __version__
from .acp_transport import open_stdio_transport

AgentFactory = Callable[..., Any]
logger = logging.getLogger(__name__)


class _FailClosedACPInput:
    """Keep sensitive tools closed until ACP approval bridging ships in #475."""

    def __init__(self) -> None:
        self._interrupted = threading.Event()

    def start_prompt(self) -> None:
        self._interrupted.clear()

    def interrupt(self) -> None:
        self._interrupted.set()

    @property
    def interrupted(self) -> bool:
        return self._interrupted.is_set()

    def send(self, _message: dict[str, Any]) -> None:
        pass

    def receive(self) -> dict[str, str]:
        if self.interrupted:
            return {"type": "INTERRUPT"}
        return {"type": "io_closed"}

    def receive_all(self, _message_type: str | None = None) -> list[Any]:
        if self.interrupted and _message_type in (None, "INTERRUPT"):
            return [{"type": "INTERRUPT"}]
        return []

    def take_interrupt(self, on_interrupt: Callable[[], None] | None = None) -> bool:
        if not self.interrupted:
            return False
        if on_interrupt:
            on_interrupt()
        return True

    def receive_interruptibly(self, cancelled: threading.Event) -> dict[str, str]:
        if self.interrupted or cancelled.is_set():
            return {"type": "INTERRUPT"}
        return {"type": "io_closed"}

    def receive_all_interruptibly(
        self,
        cancelled: threading.Event,
        message_type: str | None = None,
    ) -> list[Any]:
        if (self.interrupted or cancelled.is_set()) and message_type in (
            None,
            "INTERRUPT",
        ):
            return [{"type": "INTERRUPT"}]
        return []


@dataclass
class _SessionRuntime:
    cwd: Path
    agent: Any
    acp_input: _FailClosedACPInput
    prompt_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    prompt_active: threading.Event = field(default_factory=threading.Event)


class ConnectOnionACPAgent:
    """Expose the real ``co ai`` Agent through the stable ACP v1 lifecycle."""

    def __init__(
        self,
        *,
        model: str,
        max_iterations: int,
        yolo: bool,
        yolo_turns: int,
        agent_factory: AgentFactory | None = None,
    ) -> None:
        self._model = model
        self._max_iterations = max_iterations
        self._yolo = yolo
        self._yolo_turns = yolo_turns
        self._agent_factory = agent_factory
        self._client: Client | None = None
        self._sessions: dict[str, _SessionRuntime] = {}
        # cwd and redirect_stdout are process-global.  ACP request handlers stay
        # asynchronous, while this lock makes those short global scopes explicit.
        self._process_context_lock = threading.RLock()

    def on_connect(self, client: Client) -> None:
        self._client = client

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **_kwargs: Any,
    ) -> InitializeResponse:
        del client_capabilities, client_info
        # ACP asks an agent to return its latest supported version when it does
        # not support the client's version. The client then decides whether it
        # can continue (v1 initialization, "Version Negotiation").
        selected_version = PROTOCOL_VERSION
        return InitializeResponse(
            protocol_version=selected_version,
            agent_capabilities=AgentCapabilities(
                load_session=False,
                session_capabilities=SessionCapabilities(),
            ),
            agent_info=Implementation(
                name="connectonion",
                title="ConnectOnion co ai",
                version=__version__,
            ),
            auth_methods=[],
        )

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **_kwargs: Any,
    ) -> NewSessionResponse:
        if additional_directories:
            raise RequestError.invalid_params(
                {"details": "co ai ACP does not support additionalDirectories yet"}
            )
        if mcp_servers:
            raise RequestError.invalid_params(
                {"details": "co ai ACP does not support mcpServers yet"}
            )

        project_dir = self._validate_cwd(cwd)
        try:
            agent = await asyncio.to_thread(self._build_agent, project_dir)
        except Exception:
            logger.exception("Failed to create co ai ACP session")
            raise RequestError(
                -32603,
                "Unable to create the coding agent session",
            ) from None
        session_id = uuid4().hex
        self._sessions[session_id] = _SessionRuntime(
            cwd=project_dir,
            agent=agent,
            acp_input=agent.io,
        )
        return NewSessionResponse(session_id=session_id)

    async def prompt(
        self,
        session_id: str,
        prompt: list[Any],
        **_kwargs: Any,
    ) -> PromptResponse:
        runtime = self._sessions.get(session_id)
        if runtime is None:
            raise RequestError(
                -32002,
                "Session not found",
                {"sessionId": session_id},
            )
        if runtime.prompt_lock.locked():
            raise RequestError(
                -32000,
                "Session is busy",
                {"sessionId": session_id},
            )

        prompt_text = self._prompt_text(prompt)
        async with runtime.prompt_lock:
            runtime.acp_input.start_prompt()
            runtime.prompt_active.set()
            try:
                result = await asyncio.to_thread(
                    self._run_prompt,
                    runtime,
                    prompt_text,
                )
            except Exception:
                logger.exception("co ai ACP prompt failed for session %s", session_id)
                raise RequestError(
                    -32603,
                    "co ai prompt failed",
                ) from None

            if runtime.acp_input.interrupted:
                return PromptResponse(stop_reason="cancelled")

            if self._client is None:
                raise RequestError.internal_error(
                    {"details": "ACP client connection is not available"}
                )
            await self._client.session_update(
                session_id=session_id,
                update=update_agent_message_text(str(result)),
            )
        return PromptResponse(stop_reason="end_turn")

    async def cancel(self, session_id: str, **_kwargs: Any) -> None:
        """Cooperatively stop the active turn for an ACP session."""

        runtime = self._sessions.get(session_id)
        if runtime is not None and runtime.prompt_active.is_set():
            runtime.acp_input.interrupt()

    def cancel_all(self) -> None:
        """Stop active turns before the stdio event loop shuts down."""

        for runtime in self._sessions.values():
            if runtime.prompt_active.is_set():
                runtime.acp_input.interrupt()

    def _build_agent(self, project_dir: Path) -> Any:
        factory = self._agent_factory
        if factory is None:
            from ..commands.ai_commands import _create_agent

            factory = _create_agent

        with self._process_context(project_dir):
            agent = factory(
                model=self._model,
                max_iterations=self._max_iterations,
                yolo=self._yolo,
                yolo_turns=self._yolo_turns,
            )
        # A missing io currently means "skip approvals".  ACP must instead
        # remain safe until request_permission is mapped in #475.
        agent.io = _FailClosedACPInput()
        return agent

    def _run_prompt(self, runtime: _SessionRuntime, prompt: str) -> Any:
        try:
            with self._process_context(runtime.cwd):
                return runtime.agent.input(prompt)
        finally:
            runtime.prompt_active.clear()

    @contextmanager
    def _process_context(self, cwd: Path):
        with self._process_context_lock:
            previous_cwd = Path.cwd()
            try:
                os.chdir(cwd)
                with redirect_stdout(sys.stderr):
                    yield
            finally:
                os.chdir(previous_cwd)

    @staticmethod
    def _validate_cwd(cwd: str) -> Path:
        path = Path(cwd)
        if not path.is_absolute():
            raise RequestError.invalid_params(
                {"details": "cwd must be an absolute path"}
            )
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            raise RequestError.invalid_params(
                {"details": "cwd does not exist"}
            ) from None
        if not resolved.is_dir():
            raise RequestError.invalid_params(
                {"details": "cwd must be a directory"}
            )
        return resolved

    @staticmethod
    def _prompt_text(prompt: list[Any]) -> str:
        parts: list[str] = []
        for block in prompt:
            if isinstance(block, TextContentBlock):
                parts.append(block.text)
                continue
            if isinstance(block, ResourceContentBlock):
                label = block.title or block.name
                parts.append(f"Referenced resource: {label} ({block.uri})")
                continue
            raise RequestError.invalid_params(
                {"details": f"Unsupported ACP content block: {type(block).__name__}"}
            )
        return "\n\n".join(parts)


async def serve_acp(
    *,
    model: str,
    max_iterations: int,
    yolo: bool,
    yolo_turns: int,
) -> None:
    """Serve ``co ai`` as an ACP v1 Agent until the client closes stdin."""

    transport = await open_stdio_transport()
    agent = ConnectOnionACPAgent(
        model=model,
        max_iterations=max_iterations,
        yolo=yolo,
        yolo_turns=yolo_turns,
    )
    try:
        await run_agent(agent, input_stream=transport)
    finally:
        agent.cancel_all()
