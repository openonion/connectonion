"""ACP v1 stdio lifecycle adapter for ``co ai``.

The official ACP SDK owns JSON-RPC routing and schema validation.  This module
only adapts the lifecycle to ConnectOnion: one real coding Agent per ACP
session, an exclusive stdout protocol stream, and generation-scoped permission
requests that reuse ConnectOnion's existing approval policy.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import copy
import logging
import os
import sys
import threading
from collections import deque
from contextlib import contextmanager, redirect_stdout, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable
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
    CloseSessionResponse,
    Implementation,
    PermissionOption,
    RequestPermissionResponse,
    ResourceContentBlock,
    ResumeSessionResponse,
    SessionCapabilities,
    SessionCloseCapabilities,
    SessionResumeCapabilities,
    TextContentBlock,
    ToolCallUpdate,
)

from ..._version import __version__
from ...network.io.base import IO
from .acp_events import (
    STREAMED_AGENT_EVENT_TYPES,
    ACPTerminal,
    map_agent_event,
)
from .acp_transport import open_stdio_transport
from .agent import GLOBAL_CO_DIR
from .one_shot_sessions import (
    SessionLease,
    SessionSnapshotError,
    acquire_session_lease,
    capture_tool_state,
    load_snapshot,
    new_session_id,
    restore_tool_state,
    save_snapshot,
)

AgentFactory = Callable[..., Any]
PermissionRequester = Callable[
    [str, ToolCallUpdate, list[PermissionOption]],
    Awaitable[RequestPermissionResponse],
]
ACP_EVENT_BUFFER_SIZE = 64
logger = logging.getLogger(__name__)

_ACP_PERMISSION_OPTIONS = (
    PermissionOption(
        option_id="allow_once",
        name="Allow this call",
        kind="allow_once",
    ),
    PermissionOption(
        option_id="allow_session",
        name="Allow for this session",
        kind="allow_always",
    ),
    PermissionOption(
        option_id="reject_once",
        name="Reject and stop this turn",
        kind="reject_once",
    ),
)


class _FailClosedACPInput(IO):
    """Keep sensitive tools closed when no live ACP generation owns input."""

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

    def receive(self) -> dict[str, Any]:
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

    def receive_interruptibly(self, cancelled: threading.Event) -> dict[str, Any]:
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
    permission_future: concurrent.futures.Future[Any] | None = None


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

    def receive(self) -> dict[str, Any]:
        return self._bridge.receive_for(self._generation)

    def receive_all(self, message_type: str | None = None) -> list[Any]:
        return self._bridge.receive_all(message_type)

    def take_interrupt(self, on_interrupt: Callable[[], None] | None = None) -> bool:
        return self._bridge.take_interrupt(on_interrupt)

    def receive_interruptibly(self, cancelled: threading.Event) -> dict[str, Any]:
        return self._bridge.receive_for(self._generation, cancelled)

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

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        session_id: str,
        permission_requester: PermissionRequester,
    ) -> None:
        super().__init__()
        self._loop = loop
        self._session_id = session_id
        self._permission_requester = permission_requester
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
        if message.get("type") == "approval_needed":
            self._request_permission_for(generation, message)
            return
        self._send_for(generation, message, adapter_owned=False)

    def _request_permission_for(
        self,
        generation: _TurnGeneration,
        message: dict[str, Any],
    ) -> None:
        """Schedule one generation-owned ACP permission request."""

        tool_call_id = message.get("tool_call_id")
        tool = message.get("tool")
        arguments = message.get("arguments")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            raise ValueError("Approval request requires a tool-call ID")
        if not isinstance(tool, str) or not tool:
            raise ValueError("Approval request requires a tool name")
        if not isinstance(arguments, dict):
            raise ValueError("Approval request arguments must be a dictionary")

        tool_call = ToolCallUpdate(
            tool_call_id=tool_call_id,
            title=tool,
            status="pending",
            raw_input=copy.deepcopy(arguments),
        )
        options = [option.model_copy(deep=True) for option in _ACP_PERMISSION_OPTIONS]
        with self._outbound:
            if self._active is not generation or self.interrupted:
                raise RuntimeError("ACP prompt generation is not active")
            if generation.permission_future is not None:
                raise RuntimeError("ACP permission request is already pending")
            generation.permission_future = asyncio.run_coroutine_threadsafe(
                self._permission_requester(
                    self._session_id,
                    tool_call,
                    options,
                ),
                self._loop,
            )

    def receive_for(
        self,
        generation: _TurnGeneration,
        cancelled: threading.Event | None = None,
    ) -> dict[str, Any]:
        """Wait for one permission reply without blocking the event loop."""

        while True:
            with self._outbound:
                future = generation.permission_future
                interrupted = (
                    self._active is not generation
                    or self.interrupted
                    or (cancelled is not None and cancelled.is_set())
                )
                if interrupted:
                    generation.permission_future = None
            if interrupted:
                if future is not None:
                    future.cancel()
                return {"type": "INTERRUPT"}
            if future is None:
                return {"type": "io_closed"}

            try:
                response = future.result(timeout=0.05)
            except concurrent.futures.TimeoutError:
                continue
            except BaseException:
                with self._outbound:
                    if generation.permission_future is future:
                        generation.permission_future = None
                return {"approved": False, "mode": "reject_hard"}

            with self._outbound:
                if (
                    self._active is not generation
                    or self.interrupted
                    or (cancelled is not None and cancelled.is_set())
                ):
                    if generation.permission_future is future:
                        generation.permission_future = None
                    return {"type": "INTERRUPT"}
                if generation.permission_future is not future:
                    return {"type": "io_closed"}
                generation.permission_future = None
            return self._permission_response(response)

    @staticmethod
    def _permission_response(response: Any) -> dict[str, Any]:
        """Map only exact advertised ACP outcomes to existing approval input."""

        try:
            parsed = (
                response
                if isinstance(response, RequestPermissionResponse)
                else RequestPermissionResponse.model_validate(response)
            )
        except (TypeError, ValueError):
            return {"approved": False, "mode": "reject_hard"}

        outcome = parsed.outcome
        if outcome.outcome != "selected":
            return {"approved": False, "mode": "reject_hard"}
        if outcome.option_id == "allow_once":
            return {"approved": True, "scope": "once"}
        if outcome.option_id == "allow_session":
            return {"approved": True, "scope": "session"}
        return {"approved": False, "mode": "reject_hard"}

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
            permission_future = generation.permission_future
            generation.permission_future = None
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
        if permission_future is not None:
            permission_future.cancel()

    def retire_turn(self, generation: _TurnGeneration) -> None:
        with self._outbound:
            permission_future = generation.permission_future
            generation.permission_future = None
            if self._active is generation:
                self._active = None
            self._outbound.notify_all()
            self._signal(generation)
        if permission_future is not None:
            permission_future.cancel()

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
    session_id: str
    cwd: Path
    agent: Any
    acp_input: _ACPEventBridge
    session_lease: SessionLease
    last_good_session: dict[str, Any]
    last_good_tools: dict[str, Any]
    session_for_next_prompt: dict[str, Any] | None
    prompt_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    prompt_active: threading.Event = field(default_factory=threading.Event)
    closing: threading.Event = field(default_factory=threading.Event)
    active_operation: asyncio.Task[Any] | None = None
    close_task: asyncio.Task[None] | None = None


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
        session_co_dir: Path | None = None,
    ) -> None:
        self._model = model
        self._max_iterations = max_iterations
        self._yolo = yolo
        self._yolo_turns = yolo_turns
        self._agent_factory = agent_factory
        self._session_co_dir = Path(session_co_dir or GLOBAL_CO_DIR)
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
                session_capabilities=SessionCapabilities(
                    resume=SessionResumeCapabilities(),
                    close=SessionCloseCapabilities(),
                ),
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
        self._reject_unsupported_session_inputs(additional_directories, mcp_servers)
        project_dir = self._validate_cwd(cwd)
        session_id = new_session_id()
        acp_input = _ACPEventBridge(
            asyncio.get_running_loop(),
            session_id,
            self._request_permission,
        )
        try:
            runtime = await self._construct_runtime(
                self._open_session_runtime,
                project_dir,
                acp_input,
                session_id,
                False,
            )
        except Exception:
            logger.exception("Failed to create co ai ACP session")
            raise RequestError(
                -32603,
                "Unable to create the coding agent session",
            ) from None
        self._sessions[session_id] = runtime
        return NewSessionResponse(session_id=session_id)

    async def resume_session(
        self,
        session_id: str,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **_kwargs: Any,
    ) -> ResumeSessionResponse:
        """Resume one persisted session without replaying its transcript."""

        self._reject_unsupported_session_inputs(additional_directories, mcp_servers)
        project_dir = self._validate_cwd(cwd)
        if session_id in self._sessions:
            raise RequestError(
                -32000,
                "Session is already open",
                {"sessionId": session_id},
            )
        acp_input = _ACPEventBridge(
            asyncio.get_running_loop(),
            session_id,
            self._request_permission,
        )
        try:
            runtime = await self._construct_runtime(
                self._open_session_runtime,
                project_dir,
                acp_input,
                session_id,
                True,
            )
        except SessionSnapshotError as exc:
            raise RequestError(
                -32002,
                "Unable to resume session",
                {"details": str(exc)},
            ) from None
        except Exception:
            logger.exception("Failed to resume co ai ACP session")
            raise RequestError(
                -32603,
                "Unable to resume the coding agent session",
            ) from None
        self._sessions[session_id] = runtime
        return ResumeSessionResponse()

    async def close_session(
        self,
        session_id: str,
        **_kwargs: Any,
    ) -> CloseSessionResponse:
        """Close one live runtime and release its exclusive disk lease."""

        runtime = self._sessions.get(session_id)
        if runtime is None:
            raise RequestError(
                -32002,
                "Session not found",
                {"sessionId": session_id},
            )
        close_task = self._ensure_close_task(runtime)
        try:
            await asyncio.shield(close_task)
        except asyncio.CancelledError:
            # Closing is an ownership boundary. Repeated caller cancellation
            # must not release the request while its runtime can still mutate.
            await self._settle_owned_task(close_task)
            raise
        return CloseSessionResponse()

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
            if (
                runtime.closing.is_set()
                or self._sessions.get(session_id) is not runtime
            ):
                raise RequestError(
                    -32002,
                    "Session not found",
                    {"sessionId": session_id},
                )
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
            operation: asyncio.Task[Any] | None = worker
            commit: asyncio.Task[Any] | None = None
            runtime.active_operation = worker
            try:
                terminal, finished = await self._consume_generation(
                    runtime.acp_input,
                    generation,
                    session_id,
                )
                await asyncio.shield(worker)
                runtime.active_operation = None
                operation = None
                if finished.error is not None:
                    raise finished.error
                if terminal is None or terminal.stop_reason is None:
                    raise RuntimeError("Agent turn ended without an ACP stop reason")
                if terminal.stop_reason in {"end_turn", "max_turn_requests"}:
                    commit = asyncio.create_task(
                        asyncio.to_thread(self._commit_runtime, runtime)
                    )
                    operation = commit
                    runtime.active_operation = commit
                    await asyncio.shield(commit)
                else:
                    operation = asyncio.create_task(
                        asyncio.to_thread(self._restore_runtime, runtime)
                    )
                    runtime.active_operation = operation
                    await asyncio.shield(operation)
                runtime.active_operation = None
                operation = None
            except asyncio.CancelledError:
                runtime.acp_input.interrupt()
                runtime.acp_input.retire_turn(generation)
                if operation is not None:
                    await self._settle_owned_task(operation)
                # Atomic replacement is the commit point. If it completed,
                # _commit_runtime also advanced the detached checkpoint and a
                # cancelled waiter must not split disk from memory by rolling
                # the successful transaction back. Before that point, restore
                # the previous checkpoint.
                if commit is None or not self._task_succeeded(commit):
                    await self._restore_after_failure(runtime)
                runtime.active_operation = None
                raise
            except Exception:
                runtime.acp_input.interrupt()
                runtime.acp_input.retire_turn(generation)
                if operation is not None:
                    await self._settle_owned_task(operation)
                await self._restore_after_failure(runtime)
                runtime.active_operation = None
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

    async def _request_permission(
        self,
        session_id: str,
        tool_call: ToolCallUpdate,
        options: list[PermissionOption],
    ) -> RequestPermissionResponse:
        """Send one schema-validated permission request to the ACP client."""

        if self._client is None:
            raise RuntimeError("ACP client connection is not available")
        response = await self._client.request_permission(
            session_id=session_id,
            tool_call=tool_call,
            options=options,
        )
        return (
            response
            if isinstance(response, RequestPermissionResponse)
            else RequestPermissionResponse.model_validate(response)
        )

    def cancel_all(self) -> None:
        """Stop active turns before the stdio event loop shuts down."""

        for runtime in self._sessions.values():
            if runtime.prompt_active.is_set():
                runtime.acp_input.interrupt()

    async def close_all(self) -> None:
        """Settle every prompt before releasing persistent session leases."""

        runtimes = list(self._sessions.values())
        close_tasks = [self._ensure_close_task(runtime) for runtime in runtimes]
        # EOF cleanup is deliberately cancellation-resistant: the event loop
        # must not disappear while a runtime-owned worker or writer is alive.
        for close_task in close_tasks:
            await self._settle_owned_task(close_task)

    async def _construct_runtime(
        self,
        constructor: Callable[..., _SessionRuntime],
        *args: Any,
    ) -> _SessionRuntime:
        """Finish threaded construction even if its ACP request is cancelled."""

        construction = asyncio.create_task(asyncio.to_thread(constructor, *args))
        try:
            return await asyncio.shield(construction)
        except asyncio.CancelledError:
            await self._settle_owned_task(construction)
            if self._task_succeeded(construction):
                construction.result().session_lease.close()
            raise

    def _ensure_close_task(self, runtime: _SessionRuntime) -> asyncio.Task[None]:
        runtime.closing.set()
        runtime.acp_input.interrupt()
        if runtime.close_task is None:
            runtime.close_task = asyncio.create_task(self._finish_close(runtime))
        return runtime.close_task

    async def _finish_close(self, runtime: _SessionRuntime) -> None:
        async with runtime.prompt_lock:
            if self._sessions.get(runtime.session_id) is runtime:
                self._sessions.pop(runtime.session_id)
            runtime.session_lease.close()

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
                resumable=True,
            )
        # A missing IO currently means "skip approvals". Keep construction
        # fail-closed; live ACP sessions install their generation-bound bridge.
        agent.io = acp_input or _FailClosedACPInput()
        return agent

    def _open_session_runtime(
        self,
        project_dir: Path,
        acp_input: _ACPEventBridge,
        session_id: str,
        resume: bool,
    ) -> _SessionRuntime:
        """Acquire ownership, validate state, then construct one runtime."""

        lease = acquire_session_lease(self._session_co_dir, session_id)
        try:
            if resume:
                session, tools = load_snapshot(
                    self._session_co_dir,
                    session_id,
                    cwd=project_dir,
                )
            else:
                session, tools = None, {}

            agent = self._build_agent(project_dir, acp_input)
            if session is None:
                session = self._fresh_persistent_session(agent, session_id)
            restore_tool_state(agent, tools)
            normalized_tools = capture_tool_state(agent)
            if not resume:
                save_snapshot(
                    self._session_co_dir,
                    session,
                    normalized_tools,
                    cwd=project_dir,
                )
            return _SessionRuntime(
                session_id=session_id,
                cwd=project_dir,
                agent=agent,
                acp_input=acp_input,
                session_lease=lease,
                last_good_session=copy.deepcopy(session),
                last_good_tools=copy.deepcopy(normalized_tools),
                session_for_next_prompt=copy.deepcopy(session),
            )
        except BaseException:
            lease.close()
            raise

    def _commit_runtime(self, runtime: _SessionRuntime) -> None:
        """Prepare every checkpoint before the final atomic commit point."""

        session = copy.deepcopy(runtime.agent.current_session)
        if not isinstance(session, dict):
            raise SessionSnapshotError("Agent did not produce a session snapshot.")
        session["session_id"] = runtime.session_id
        tools = capture_tool_state(runtime.agent)
        last_good_session = copy.deepcopy(session)
        last_good_tools = copy.deepcopy(tools)
        # Assignment and checkpoint preparation happen before disk commit. If
        # any of them fails, prompt rollback can still rely on the old file.
        runtime.agent.current_session = session
        save_snapshot(
            self._session_co_dir,
            session,
            tools,
            cwd=runtime.cwd,
        )
        # os.replace inside save_snapshot is the final fallible commit step.
        # These reference assignments cannot split the durable snapshot from
        # the already-prepared in-memory checkpoint.
        runtime.last_good_session = last_good_session
        runtime.last_good_tools = last_good_tools

    @staticmethod
    def _restore_runtime(runtime: _SessionRuntime) -> None:
        """Roll Agent and supported tool state back to the last disk commit."""

        runtime.agent.current_session = copy.deepcopy(runtime.last_good_session)
        restore_tool_state(
            runtime.agent,
            copy.deepcopy(runtime.last_good_tools),
        )

    async def _restore_after_failure(self, runtime: _SessionRuntime) -> None:
        restore = asyncio.create_task(asyncio.to_thread(self._restore_runtime, runtime))
        runtime.active_operation = restore
        await self._settle_owned_task(restore)
        if not self._task_succeeded(restore):
            error = self._task_exception(restore)
            logger.error(
                "Failed to restore co ai ACP session %s",
                runtime.session_id,
                exc_info=(type(error), error, error.__traceback__) if error else None,
            )
            # Never keep serving a runtime whose in-memory state may have
            # diverged from its last atomic snapshot. The worker is settled
            # before this method runs, so a clean process may resume safely.
            runtime.closing.set()
            if self._sessions.get(runtime.session_id) is runtime:
                self._sessions.pop(runtime.session_id)
            runtime.session_lease.close()
        runtime.active_operation = None

    @staticmethod
    def _fresh_persistent_session(agent: Any, session_id: str) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "messages": [{
                "role": "system",
                "content": str(getattr(agent, "system_prompt", "")),
            }],
            "trace": [],
            "turn": 0,
        }

    @staticmethod
    def _reject_unsupported_session_inputs(
        additional_directories: list[str] | None,
        mcp_servers: list[Any] | None,
    ) -> None:
        if additional_directories:
            raise RequestError.invalid_params(
                {"details": "co ai ACP does not support additionalDirectories yet"}
            )
        if mcp_servers:
            raise RequestError.invalid_params(
                {"details": "co ai ACP does not support mcpServers yet"}
            )

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
    async def _settle_owned_task(task: asyncio.Task[Any]) -> bool:
        """Wait through repeated caller cancellation until ``task`` is done.

        Returns whether this waiter was cancelled while settling. The child is
        always shielded: cancelling an ACP request must never abandon a thread
        that still owns or mutates persistent session state.
        """

        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
            except BaseException:
                break
        with suppress(BaseException):
            task.result()
        return cancelled

    @staticmethod
    def _task_succeeded(task: asyncio.Task[Any]) -> bool:
        return task.done() and not task.cancelled() and task.exception() is None

    @staticmethod
    def _task_exception(task: asyncio.Task[Any]) -> BaseException | None:
        if not task.done() or task.cancelled():
            return None
        return task.exception()

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
            session = runtime.session_for_next_prompt
            runtime.session_for_next_prompt = None
            with self._process_context(runtime.cwd):
                if session is None:
                    return runtime.agent.input(prompt)
                return runtime.agent.input(
                    prompt,
                    session=copy.deepcopy(session),
                )
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
        # ACP Python 0.12 gates the schema-v1.19 resume/close routes behind
        # this transport flag even though their capability models are stable.
        await run_agent(
            agent,
            input_stream=transport,
            use_unstable_protocol=True,
        )
    finally:
        agent.cancel_all()
        await agent.close_all()
