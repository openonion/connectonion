"""ACP v1 stdio lifecycle adapter for ``co ai``.

The official ACP SDK owns JSON-RPC routing and schema validation.  This module
only adapts the lifecycle to ConnectOnion: one real coding Agent per ACP
session, an exclusive stdout protocol stream, and fail-closed approvals until
the dedicated permission bridge lands.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import os
import sys
import threading
from collections import deque
from contextlib import contextmanager, redirect_stdout, suppress
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
from ...network.io.base import IO
from .acp_events import (
    STREAMED_AGENT_EVENT_TYPES,
    ACPTerminal,
    map_agent_event,
)
from .acp_transport import open_stdio_transport

AgentFactory = Callable[..., Any]
ACP_EVENT_BUFFER_SIZE = 64
logger = logging.getLogger(__name__)


class _FailClosedACPInput(IO):
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
class _TurnGeneration:
    number: int
    ready: asyncio.Event
    items: deque[Any] = field(default_factory=deque)
    next_ticket: int = 0
    serving_ticket: int = 0
    terminal_claimed: bool = False
    terminal_reason: str | None = None
    assistant_claimed: bool = False


@dataclass(frozen=True)
class _TurnFinished:
    result: Any = None
    error: BaseException | None = None


class _ACPGenerationIO(IO):
    """Agent IO lease bound to exactly one prompt generation."""

    def __init__(
        self,
        bridge: _ACPEventBridge,
        generation: _TurnGeneration,
    ) -> None:
        self._bridge = bridge
        self._generation = generation

    def send(self, message: dict[str, Any]) -> None:
        self._bridge.send_for(self._generation, message)

    def receive(self) -> dict[str, str]:
        return self._bridge.receive()

    def receive_all(self, message_type: str | None = None) -> list[Any]:
        return self._bridge.receive_all(message_type)

    def take_interrupt(self, on_interrupt: Callable[[], None] | None = None) -> bool:
        return self._bridge.take_interrupt(on_interrupt)

    def receive_interruptibly(self, cancelled: threading.Event) -> dict[str, str]:
        return self._bridge.receive_interruptibly(cancelled)

    def receive_all_interruptibly(
        self,
        cancelled: threading.Event,
        message_type: str | None = None,
    ) -> list[Any]:
        return self._bridge.receive_all_interruptibly(cancelled, message_type)

    @property
    def interrupted(self) -> bool:
        return self._bridge.interrupted


class _ACPEventBridge(_FailClosedACPInput):
    """Move immutable Agent events from worker threads to one FIFO consumer."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._loop = loop
        self._outbound = threading.Condition()
        self._next_generation = 0
        self._active: _TurnGeneration | None = None

    def interrupt(self) -> None:
        super().interrupt()
        with self._outbound:
            self._outbound.notify_all()

    def begin_turn(self) -> tuple[_TurnGeneration, _ACPGenerationIO]:
        self.start_prompt()
        with self._outbound:
            if self._active is not None:
                raise RuntimeError("ACP event generation is already active")
            self._next_generation += 1
            generation = _TurnGeneration(
                number=self._next_generation,
                ready=asyncio.Event(),
            )
            self._active = generation
        return generation, _ACPGenerationIO(self, generation)

    def send_for(
        self,
        generation: _TurnGeneration,
        message: dict[str, Any],
    ) -> None:
        self._send_for(generation, message, adapter_owned=False)

    def send_terminal_for(
        self,
        generation: _TurnGeneration,
        event: dict[str, Any],
    ) -> None:
        self._send_for(generation, event, adapter_owned=True)

    def send_assistant_for(
        self,
        generation: _TurnGeneration,
        content: str,
    ) -> None:
        self._send_for(
            generation,
            {
                "type": "assistant",
                "message_id": str(uuid4()),
                "content": content,
            },
            adapter_owned=True,
        )

    def _send_for(
        self,
        generation: _TurnGeneration,
        message: dict[str, Any],
        *,
        adapter_owned: bool,
    ) -> None:
        event_type = message.get("type")
        if event_type not in STREAMED_AGENT_EVENT_TYPES:
            return
        with self._outbound:
            if self._active is not generation:
                return
            if event_type == "assistant":
                if (
                    not adapter_owned
                    or generation.assistant_claimed
                    or generation.terminal_reason
                    not in {"natural", "max_iterations"}
                ):
                    return
                generation.assistant_claimed = True
            elif event_type == "turn_result":
                if not adapter_owned or generation.terminal_claimed:
                    return
                generation.terminal_claimed = True
                generation.terminal_reason = message.get("reason")
            completion_event = event_type in {"assistant", "turn_result"}
            if self.interrupted and not completion_event:
                return
            ticket = generation.next_ticket
            generation.next_ticket += 1

        try:
            detached = copy.deepcopy(message)
        except BaseException:
            with self._outbound:
                while (
                    self._active is generation
                    and ticket != generation.serving_ticket
                ):
                    self._outbound.wait()
                if self._active is not generation:
                    return
                generation.serving_ticket += 1
                self._outbound.notify_all()
                if self.interrupted and not completion_event:
                    return
            raise

        with self._outbound:
            while (
                self._active is generation
                and ticket != generation.serving_ticket
            ):
                self._outbound.wait()
            if self._active is not generation:
                return
            if self.interrupted and not completion_event:
                generation.serving_ticket += 1
                self._outbound.notify_all()
                return
            while (
                self._active is generation
                and not self.interrupted
                and len(generation.items) >= ACP_EVENT_BUFFER_SIZE
            ):
                self._outbound.wait()
            if self._active is not generation:
                return
            if self.interrupted and not completion_event:
                generation.serving_ticket += 1
                self._outbound.notify_all()
                return
            self._append_locked(generation, detached)
            generation.serving_ticket += 1
            self._outbound.notify_all()

    def finish_turn(
        self,
        generation: _TurnGeneration,
        *,
        result: Any = None,
        error: BaseException | None = None,
    ) -> None:
        finished = _TurnFinished(result=result, error=error)
        with self._outbound:
            if self._active is not generation:
                return
            ticket = generation.next_ticket
            generation.next_ticket += 1
            while (
                self._active is generation
                and ticket != generation.serving_ticket
            ):
                self._outbound.wait()
            if self._active is not generation:
                return
            while (
                self._active is generation
                and not self.interrupted
                and len(generation.items) >= ACP_EVENT_BUFFER_SIZE
            ):
                self._outbound.wait()
            if self._active is not generation:
                return
            self._append_locked(generation, finished)
            generation.serving_ticket += 1
            self._active = None
            self._outbound.notify_all()

    def retire_turn(self, generation: _TurnGeneration) -> None:
        with self._outbound:
            if self._active is generation:
                self._active = None
            self._outbound.notify_all()
            self._signal(generation)

    async def next_for(self, generation: _TurnGeneration) -> Any:
        while True:
            with self._outbound:
                if generation.items:
                    item = generation.items.popleft()
                    if not generation.items:
                        generation.ready.clear()
                    self._outbound.notify_all()
                    return item
                if self._active is not generation:
                    raise RuntimeError("ACP event generation was retired")
                generation.ready.clear()
            await generation.ready.wait()

    def _append_locked(self, generation: _TurnGeneration, item: Any) -> None:
        should_signal = not generation.items
        generation.items.append(item)
        if should_signal:
            self._signal(generation)

    def _signal(self, generation: _TurnGeneration) -> None:
        try:
            self._loop.call_soon_threadsafe(generation.ready.set)
        except RuntimeError:
            if self._active is generation:
                self._active = None
            self._outbound.notify_all()


@dataclass
class _SessionRuntime:
    cwd: Path
    agent: Any
    acp_input: _ACPEventBridge
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
        acp_input = _ACPEventBridge(asyncio.get_running_loop())
        try:
            agent = await asyncio.to_thread(
                self._build_agent,
                project_dir,
                acp_input,
            )
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
            acp_input=acp_input,
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
        if runtime.prompt_lock.locked() or runtime.prompt_active.is_set():
            raise RequestError(
                -32000,
                "Session is busy",
                {"sessionId": session_id},
            )

        prompt_text = self._prompt_text(prompt)
        async with runtime.prompt_lock:
            if self._client is None:
                raise RequestError.internal_error(
                    {"details": "ACP client connection is not available"}
                )
            generation, generation_io = runtime.acp_input.begin_turn()
            runtime.agent.io = generation_io
            runtime.prompt_active.set()
            worker = asyncio.create_task(
                asyncio.to_thread(
                    self._run_prompt_generation,
                    runtime,
                    generation,
                    prompt_text,
                )
            )
            try:
                terminal, finished = await self._consume_generation(
                    runtime.acp_input,
                    generation,
                    session_id,
                )
                await worker
                if finished.error is not None:
                    raise finished.error
                if terminal is None or terminal.stop_reason is None:
                    raise RuntimeError("Agent turn ended without an ACP stop reason")
            except asyncio.CancelledError:
                runtime.acp_input.interrupt()
                runtime.acp_input.retire_turn(generation)
                await self._settle_failed_worker(worker)
                raise
            except Exception:
                runtime.acp_input.interrupt()
                runtime.acp_input.retire_turn(generation)
                await self._settle_failed_worker(worker)
                logger.exception("co ai ACP prompt failed for session %s", session_id)
                raise RequestError(
                    -32603,
                    "co ai prompt failed",
                ) from None
            return PromptResponse(
                stop_reason=terminal.stop_reason,
                usage=terminal.usage,
            )

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

    def _build_agent(
        self,
        project_dir: Path,
        acp_input: _FailClosedACPInput | None = None,
    ) -> Any:
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
        agent.io = acp_input or _FailClosedACPInput()
        return agent

    def _run_prompt_generation(
        self,
        runtime: _SessionRuntime,
        generation: _TurnGeneration,
        prompt: str,
    ) -> None:
        result = None
        error = None
        trace_start = self._trace_length(runtime.agent)
        try:
            result = self._run_prompt(runtime, prompt)
        except BaseException as exc:
            error = exc
        finally:
            terminal_event = self._latest_turn_result(
                runtime.agent,
                trace_start,
            )
            if terminal_event is not None:
                runtime.acp_input.send_terminal_for(
                    generation,
                    terminal_event,
                )
                if (
                    error is None
                    and terminal_event.get("reason")
                    in {"natural", "max_iterations"}
                ):
                    runtime.acp_input.send_assistant_for(
                        generation,
                        str(result),
                    )
            runtime.acp_input.finish_turn(
                generation,
                result=result,
                error=error,
            )

    async def _consume_generation(
        self,
        bridge: _ACPEventBridge,
        generation: _TurnGeneration,
        session_id: str,
    ) -> tuple[ACPTerminal | None, _TurnFinished]:
        terminal = None
        while True:
            item = await bridge.next_for(generation)
            if isinstance(item, _TurnFinished):
                return terminal, item
            mapped = map_agent_event(item)
            if mapped.terminal is not None:
                if terminal is not None:
                    raise RuntimeError("Agent turn emitted more than one terminal event")
                terminal = mapped.terminal
            for update in mapped.updates:
                await self._client.session_update(
                    session_id=session_id,
                    update=update,
                )

    @staticmethod
    async def _settle_failed_worker(worker: asyncio.Task[Any]) -> None:
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(worker), timeout=1.0)

    @staticmethod
    def _trace_length(agent: Any) -> int:
        session = getattr(agent, "current_session", None)
        if not isinstance(session, dict):
            return 0
        trace = session.get("trace")
        return len(trace) if isinstance(trace, list) else 0

    @staticmethod
    def _latest_turn_result(
        agent: Any,
        trace_start: int,
    ) -> dict[str, Any] | None:
        session = getattr(agent, "current_session", None)
        if not isinstance(session, dict):
            return None
        trace = session.get("trace")
        if not isinstance(trace, list):
            return None
        current_turn = session.get("turn")
        for entry in reversed(trace[trace_start:]):
            if (
                isinstance(entry, dict)
                and entry.get("type") == "turn_result"
                and entry.get("turn") == current_turn
            ):
                return entry
        return None

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
