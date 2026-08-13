"""ACP v1 stdio lifecycle adapter for ``co ai``.

The official ACP SDK owns JSON-RPC routing and schema validation.  This module
only adapts the lifecycle to ConnectOnion: one real coding Agent per ACP
session, an exclusive stdout protocol stream, and generation-scoped permission
requests that reuse ConnectOnion's existing approval policy.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import concurrent.futures
import copy
import logging
import math
import os
import re
import stat
import sys
import threading
import unicodedata
from collections import deque
from contextlib import contextmanager, redirect_stdout, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import unquote_to_bytes, urlsplit
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
    BlobResourceContents,
    ClientCapabilities,
    CloseSessionResponse,
    CurrentModeUpdate,
    EmbeddedResourceContentBlock,
    ImageContentBlock,
    Implementation,
    PermissionOption,
    PromptCapabilities,
    RequestPermissionResponse,
    ResourceContentBlock,
    ResumeSessionResponse,
    SessionCapabilities,
    SessionCloseCapabilities,
    SessionMode,
    SessionModeState,
    SessionResumeCapabilities,
    SetSessionModeResponse,
    TextContentBlock,
    TextResourceContents,
    ToolCallUpdate,
)

from ..._version import __version__
from ...core.approval_modes import (
    DANGER_FULL_ACCESS_PERMISSION_PROFILE,
    PERMISSION_PROFILE_IDS,
    READ_ONLY_PERMISSION_PROFILE,
    WORKSPACE_PERMISSION_PROFILE,
    legacy_permission_profile_id,
    migrate_legacy_full_access_fields,
)
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
    SnapshotStorageLimits,
    acquire_bounded_new_session_lease,
    acquire_session_lease,
    capture_tool_state,
    discard_unpublished_session,
    load_snapshot,
    new_session_id,
    restore_tool_state,
    save_snapshot,
)

AgentFactory = Callable[..., Any]
MCPConnector = Callable[..., Awaitable[Any]]
PermissionRequester = Callable[
    [str, ToolCallUpdate, list[PermissionOption]],
    Awaitable[RequestPermissionResponse],
]
ACP_EVENT_BUFFER_SIZE = 64
ACP_SESSION_CONFLICT_ERROR_CODE = -32001
logger = logging.getLogger(__name__)

_UPLOAD_URI_SCHEME = "connectonion-upload"
_MIME_TYPE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
)
_IMAGE_MIME_TYPES = frozenset(
    {"image/gif", "image/jpeg", "image/png", "image/webp"}
)
_UNSAFE_FILENAME_CHARACTER = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
_WINDOWS_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CLOCK$"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)

# cwd and redirect_stdout are process-global, so every ACP adapter in this
# process must share one lock rather than protecting only itself.
_PROCESS_CONTEXT_LOCK = threading.RLock()


@dataclass(frozen=True)
class _PromptInput:
    text: str
    images: tuple[str, ...] = ()
    files: tuple[dict[str, str], ...] = ()
    file_bytes: int = 0


class _UploadQuotaReservation:
    """Cross-process file lock held through one upload transaction."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        handle.close()


class _BoundNetworkWorkspace:
    """The exact directory object that existed when the network Host started."""

    def __init__(self, path: Path, descriptor: int | None) -> None:
        self.path = path
        self._descriptor = descriptor
        self._closed = False
        stat_result = os.fstat(descriptor) if descriptor is not None else path.stat()
        if stat_result.st_ino == 0:
            raise RuntimeError("Network ACP requires a stable workspace identity")
        self._identity = (stat_result.st_dev, stat_result.st_ino)

    @property
    def namespace_key(self) -> str:
        """Private namespace input; the caller stores only its digest."""

        return f"{self.path}\0{self._identity[0]}:{self._identity[1]}"

    @contextmanager
    def enter(self):
        if self._closed:
            raise RuntimeError("Network ACP workspace is closed")
        if self._descriptor is not None and hasattr(os, "fchdir"):
            flags = os.O_RDONLY
            if hasattr(os, "O_DIRECTORY"):
                flags |= os.O_DIRECTORY
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            previous = os.open(".", flags)
            try:
                os.fchdir(self._descriptor)
                yield
            finally:
                os.fchdir(previous)
                os.close(previous)
            return

        self._verify_path_identity()
        previous_path = Path.cwd()
        try:
            os.chdir(self.path)
            current = os.stat(".")
            if (current.st_dev, current.st_ino) != self._identity:
                raise RuntimeError("Network ACP workspace changed after Host startup")
            yield
        finally:
            os.chdir(previous_path)

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        """Release the pinned directory handle once the Host has stopped."""

        if self._closed:
            return
        self._closed = True
        descriptor = self._descriptor
        self._descriptor = None
        if descriptor is not None:
            os.close(descriptor)

    def _verify_path_identity(self) -> None:
        try:
            current = self.path.stat()
        except OSError:
            raise RuntimeError("Network ACP workspace is no longer available") from None
        if (current.st_dev, current.st_ino) != self._identity:
            raise RuntimeError("Network ACP workspace changed after Host startup")


def capture_network_workspace(path: Path) -> _BoundNetworkWorkspace:
    """Bind the network workspace to a directory object, not a reusable path."""

    resolved = Path(path).resolve(strict=True)
    if not resolved.is_dir():
        raise NotADirectoryError(resolved)
    if not hasattr(os, "fchdir"):
        return _BoundNetworkWorkspace(resolved, None)

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(resolved, flags)
    try:
        before = resolved.stat()
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise RuntimeError("Network ACP workspace changed during Host startup")
        return _BoundNetworkWorkspace(resolved, descriptor)
    except BaseException:
        os.close(descriptor)
        raise

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

_ACP_SESSION_MODES = (
    SessionMode(
        id=READ_ONLY_PERMISSION_PROFILE,
        name="Read only",
        description="Read freely; ask before edits, commands, or broader access.",
    ),
    SessionMode(
        id=WORKSPACE_PERMISSION_PROFILE,
        name="Auto",
        description="Edit the workspace automatically; broader actions still ask.",
    ),
    SessionMode(
        id=DANGER_FULL_ACCESS_PERMISSION_PROFILE,
        name="Full access",
        description="Run autonomously within the launch-time turn budget.",
    ),
)
_ACP_MODE_IDS = PERMISSION_PROFILE_IDS
_FULL_ACCESS_STATE_KEYS = (
    "skip_tool_approval",
    "full_access_turns",
    "full_access_turns_used",
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
class _SessionOwnership:
    lease: SessionLease
    session: dict[str, Any] | None
    tools: dict[str, Any]


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
    mcp_pool: Any | None = None
    prompt_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    prompt_active: threading.Event = field(default_factory=threading.Event)
    prompt_cancelled: threading.Event = field(default_factory=threading.Event)
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
        network_workspace: _BoundNetworkWorkspace | None = None,
        input_limits: Mapping[str, int | float] | None = None,
        allow_mcp: bool = False,
        mcp_connector: MCPConnector | None = None,
    ) -> None:
        self._model = model
        self._max_iterations = max_iterations
        self._yolo = yolo
        self._yolo_turns = yolo_turns
        self._agent_factory = agent_factory
        self._session_co_dir = Path(session_co_dir or GLOBAL_CO_DIR)
        self._network_workspace = network_workspace
        from ...network.host.config import DEFAULT_FILE_LIMITS

        limits = dict(DEFAULT_FILE_LIMITS)
        if input_limits is not None:
            limits.update(input_limits)
        max_size_mb = limits.get("max_file_size")
        max_count = limits.get("max_files_per_request")
        max_storage_mb = limits.get("max_acp_upload_storage")
        max_stored_files = limits.get("max_acp_upload_files")
        max_sessions = limits.get("max_acp_sessions")
        max_session_storage_mb = limits.get("max_acp_session_storage")
        max_snapshot_mb = limits.get("max_acp_snapshot_size")
        if (
            isinstance(max_size_mb, bool)
            or not isinstance(max_size_mb, (int, float))
            or not math.isfinite(max_size_mb)
            or max_size_mb <= 0
            or isinstance(max_count, bool)
            or not isinstance(max_count, int)
            or max_count <= 0
            or isinstance(max_storage_mb, bool)
            or not isinstance(max_storage_mb, (int, float))
            or not math.isfinite(max_storage_mb)
            or max_storage_mb <= 0
            or isinstance(max_stored_files, bool)
            or not isinstance(max_stored_files, int)
            or max_stored_files <= 0
            or isinstance(max_sessions, bool)
            or not isinstance(max_sessions, int)
            or max_sessions <= 0
            or isinstance(max_session_storage_mb, bool)
            or not isinstance(max_session_storage_mb, (int, float))
            or not math.isfinite(max_session_storage_mb)
            or max_session_storage_mb <= 0
            or isinstance(max_snapshot_mb, bool)
            or not isinstance(max_snapshot_mb, (int, float))
            or not math.isfinite(max_snapshot_mb)
            or max_snapshot_mb <= 0
        ):
            raise ValueError("ACP storage and attachment limits must be positive numbers")
        max_attachment_bytes = max_size_mb * 1024 * 1024
        if not math.isfinite(max_attachment_bytes) or max_attachment_bytes < 1:
            raise ValueError("ACP attachment size limit must be at least one byte")
        self._max_attachment_bytes = int(max_attachment_bytes)
        self._max_attachments = max_count
        max_upload_storage_bytes = max_storage_mb * 1024 * 1024
        if (
            not math.isfinite(max_upload_storage_bytes)
            or max_upload_storage_bytes < 1
        ):
            raise ValueError("ACP upload storage limit must be at least one byte")
        self._max_upload_storage_bytes = int(max_upload_storage_bytes)
        self._max_upload_files = max_stored_files
        max_session_storage_bytes = max_session_storage_mb * 1024 * 1024
        max_snapshot_bytes = max_snapshot_mb * 1024 * 1024
        if (
            not math.isfinite(max_session_storage_bytes)
            or max_session_storage_bytes < 1
            or not math.isfinite(max_snapshot_bytes)
            or max_snapshot_bytes < 1
            or max_snapshot_bytes > max_session_storage_bytes
        ):
            raise ValueError(
                "ACP session storage limits must be at least one byte and consistent"
            )
        self._snapshot_storage_limits = (
            SnapshotStorageLimits(
                max_sessions=max_sessions,
                max_total_bytes=int(max_session_storage_bytes),
                max_snapshot_bytes=int(max_snapshot_bytes),
            )
            if network_workspace is not None
            else None
        )
        self._allow_mcp = allow_mcp
        self._mcp_connector = mcp_connector
        self._client: Client | None = None
        self._sessions: dict[str, _SessionRuntime] = {}
        self._initialized = False

    def on_connect(self, client: Client) -> None:
        self._client = client

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise RequestError.invalid_request(
                {"details": "Connection is not initialized"}
            )

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **_kwargs: Any,
    ) -> InitializeResponse:
        del client_capabilities, client_info
        if self._initialized:
            raise RequestError.invalid_request(
                {"details": "Connection is already initialized"}
            )
        # ACP asks an agent to return its latest supported version when it does
        # not support the client's version. The client then decides whether it
        # can continue (v1 initialization, "Version Negotiation").
        selected_version = PROTOCOL_VERSION
        response = InitializeResponse(
            protocol_version=selected_version,
            agent_capabilities=AgentCapabilities(
                load_session=False,
                prompt_capabilities=PromptCapabilities(
                    image=True,
                    embedded_context=True,
                ),
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
        self._initialized = True
        return response

    async def new_session(
        self,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **_kwargs: Any,
    ) -> NewSessionResponse:
        self._require_initialized()
        self._validate_session_inputs(additional_directories, mcp_servers)
        project_dir = self._session_cwd(cwd)
        session_id = new_session_id()
        acp_input = _ACPEventBridge(
            asyncio.get_running_loop(),
            session_id,
            self._request_permission,
        )
        try:
            runtime = await self._construct_session_runtime(
                project_dir,
                acp_input,
                session_id,
                False,
                mcp_servers or [],
            )
        except Exception:
            logger.exception("Failed to create co ai ACP session")
            raise RequestError(
                -32603,
                "Unable to create the coding agent session",
            ) from None
        self._sessions[session_id] = runtime
        return NewSessionResponse(
            session_id=session_id,
            modes=self._session_mode_state(runtime),
        )

    async def resume_session(
        self,
        session_id: str,
        cwd: str,
        additional_directories: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
        **_kwargs: Any,
    ) -> ResumeSessionResponse:
        """Resume one persisted session without replaying its transcript."""

        self._require_initialized()
        self._validate_session_inputs(additional_directories, mcp_servers)
        project_dir = self._session_cwd(cwd)
        if session_id in self._sessions:
            raise RequestError(
                ACP_SESSION_CONFLICT_ERROR_CODE,
                "Session is already open",
                {"sessionId": session_id},
            )
        acp_input = _ACPEventBridge(
            asyncio.get_running_loop(),
            session_id,
            self._request_permission,
        )
        try:
            runtime = await self._construct_session_runtime(
                project_dir,
                acp_input,
                session_id,
                True,
                mcp_servers or [],
            )
        except SessionSnapshotError as exc:
            details = None if self._network_workspace is not None else str(exc)
            raise RequestError(
                -32002,
                "Unable to resume session",
                {"details": details} if details is not None else None,
            ) from None
        except Exception:
            logger.exception("Failed to resume co ai ACP session")
            raise RequestError(
                -32603,
                "Unable to resume the coding agent session",
            ) from None
        self._sessions[session_id] = runtime
        return ResumeSessionResponse(modes=self._session_mode_state(runtime))

    async def set_session_mode(
        self,
        session_id: str,
        mode_id: str,
        **_kwargs: Any,
    ) -> SetSessionModeResponse:
        """Persist one idle mode change without exceeding launch authority."""

        self._require_initialized()
        runtime = self._sessions.get(session_id)
        if runtime is None:
            raise RequestError(
                -32002,
                "Session not found",
                {"sessionId": session_id},
            )
        try:
            mode_id = legacy_permission_profile_id(mode_id)
        except ValueError:
            raise RequestError.invalid_params(
                {"details": "Unsupported session mode"}
            ) from None
        if mode_id == DANGER_FULL_ACCESS_PERMISSION_PROFILE and not self._yolo:
            raise RequestError.invalid_params(
                {"details": "Full access mode was not authorized when ACP started"}
            )
        if runtime.prompt_lock.locked() or runtime.prompt_active.is_set():
            raise RequestError(
                ACP_SESSION_CONFLICT_ERROR_CODE,
                "Session is busy",
                {"sessionId": session_id},
            )

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
            operation = asyncio.create_task(
                asyncio.to_thread(self._commit_mode, runtime, mode_id)
            )
            runtime.active_operation = operation
            try:
                await asyncio.shield(operation)
            except asyncio.CancelledError:
                await self._settle_owned_task(operation)
                raise
            except Exception:
                logger.exception(
                    "Failed to change co ai ACP mode for session %s",
                    session_id,
                )
                raise RequestError(
                    -32603,
                    "Unable to change session mode",
                ) from None
            finally:
                runtime.active_operation = None
        return SetSessionModeResponse()

    async def close_session(
        self,
        session_id: str,
        **_kwargs: Any,
    ) -> CloseSessionResponse:
        """Close one live runtime and release its exclusive disk lease."""

        self._require_initialized()
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
        self._require_initialized()
        runtime = self._sessions.get(session_id)
        if runtime is None:
            raise RequestError(
                -32002,
                "Session not found",
                {"sessionId": session_id},
            )
        if runtime.prompt_lock.locked() or runtime.prompt_active.is_set():
            raise RequestError(
                ACP_SESSION_CONFLICT_ERROR_CODE,
                "Session is busy",
                {"sessionId": session_id},
            )

        prompt_input = self._parse_prompt(prompt)
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
            runtime.prompt_cancelled.clear()
            runtime.prompt_active.set()
            try:
                upload_reservation = await self._acquire_network_upload_reservation(
                    prompt_input
                )
            except BaseException:
                runtime.prompt_active.clear()
                raise
            if runtime.prompt_cancelled.is_set() or runtime.closing.is_set():
                if upload_reservation is not None:
                    upload_reservation.release()
                runtime.prompt_active.clear()
                return PromptResponse(stop_reason="cancelled")
            generation: _TurnGeneration | None = None
            try:
                trace_start = self._trace_length(runtime.agent)
                generation, generation_io = runtime.acp_input.begin_turn()
                if runtime.prompt_cancelled.is_set() or runtime.closing.is_set():
                    runtime.acp_input.retire_turn(generation)
                    if upload_reservation is not None:
                        upload_reservation.release()
                    runtime.prompt_active.clear()
                    return PromptResponse(stop_reason="cancelled")
                runtime.agent.io = generation_io
                worker = asyncio.create_task(
                    asyncio.to_thread(
                        self._run_prompt_generation,
                        runtime,
                        generation,
                        prompt_input,
                        trace_start,
                        upload_reservation,
                    )
                )
            except BaseException:
                if generation is not None:
                    runtime.acp_input.retire_turn(generation)
                runtime.prompt_active.clear()
                if upload_reservation is not None:
                    upload_reservation.release()
                raise
            operation: asyncio.Task[Any] | None = worker
            commit: asyncio.Task[Any] | None = None
            runtime.active_operation = worker
            try:
                terminal, finished, current_mode_update = await self._consume_generation(
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
                    if current_mode_update is not None and (
                        not isinstance(runtime.agent.current_session, dict)
                        or runtime.agent.current_session.get("mode")
                        != current_mode_update.current_mode_id
                    ):
                        raise RuntimeError(
                            "Agent mode event does not match session state"
                        )
                    commit = asyncio.create_task(
                        asyncio.to_thread(self._commit_runtime, runtime)
                    )
                    operation = commit
                    runtime.active_operation = commit
                    await asyncio.shield(commit)
                    if current_mode_update is not None:
                        await self._publish_committed_mode(
                            runtime,
                            current_mode_update,
                        )
                else:
                    self._remove_failed_turn_uploads(runtime.agent, trace_start)
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
                    self._remove_failed_turn_uploads(runtime.agent, trace_start)
                    await self._restore_after_failure(runtime)
                runtime.active_operation = None
                raise
            except Exception:
                runtime.acp_input.interrupt()
                runtime.acp_input.retire_turn(generation)
                if operation is not None:
                    await self._settle_owned_task(operation)
                if commit is None or not self._task_succeeded(commit):
                    self._remove_failed_turn_uploads(runtime.agent, trace_start)
                await self._restore_after_failure(runtime)
                runtime.active_operation = None
                logger.exception("co ai ACP prompt failed for session %s", session_id)
                raise RequestError(
                    -32603,
                    "co ai prompt failed",
                ) from None
            finally:
                if upload_reservation is not None:
                    upload_reservation.release()
            return PromptResponse(
                stop_reason=terminal.stop_reason,
                usage=terminal.usage,
            )

    async def cancel(self, session_id: str, **_kwargs: Any) -> None:
        """Cooperatively stop the active turn for an ACP session."""

        if not self._initialized:
            return
        runtime = self._sessions.get(session_id)
        if runtime is not None and runtime.prompt_active.is_set():
            runtime.prompt_cancelled.set()
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

    async def _construct_session_runtime(
        self,
        project_dir: Path,
        acp_input: _ACPEventBridge,
        session_id: str,
        resume: bool,
        mcp_servers: list[Any],
    ) -> _SessionRuntime:
        """Own and validate the session before launching external processes."""

        ownership = await self._acquire_session_ownership(
            project_dir,
            session_id,
            resume,
        )
        mcp_pool = None
        try:
            mcp_pool = await self._connect_mcp_servers(mcp_servers, project_dir)
            construction = asyncio.create_task(
                asyncio.to_thread(
                    self._open_session_runtime,
                    project_dir,
                    acp_input,
                    session_id,
                    list(mcp_pool.tools) if mcp_pool is not None else [],
                    ownership,
                )
            )
            try:
                runtime = await asyncio.shield(construction)
            except asyncio.CancelledError:
                await self._settle_owned_task(construction)
                raise
        except BaseException:
            try:
                if mcp_pool is not None:
                    await mcp_pool.close()
            finally:
                if not resume and self._snapshot_storage_limits is not None:
                    await self._settle_unpublished_session_cleanup(
                        session_id,
                        ownership.lease,
                    )
                else:
                    ownership.lease.close()
            raise
        runtime.mcp_pool = mcp_pool
        return runtime

    async def _acquire_session_ownership(
        self,
        project_dir: Path,
        session_id: str,
        resume: bool,
    ) -> _SessionOwnership:
        """Acquire a lease and load resume state with cancellation-safe cleanup."""

        acquisition = asyncio.create_task(
            asyncio.to_thread(
                self._load_owned_session,
                project_dir,
                session_id,
                resume,
            )
        )
        try:
            return await asyncio.shield(acquisition)
        except asyncio.CancelledError:
            await self._settle_owned_task(acquisition)
            if self._task_succeeded(acquisition):
                ownership = acquisition.result()
                if not resume and self._snapshot_storage_limits is not None:
                    await self._settle_unpublished_session_cleanup(
                        session_id,
                        ownership.lease,
                    )
                else:
                    ownership.lease.close()
            raise

    def _load_owned_session(
        self,
        project_dir: Path,
        session_id: str,
        resume: bool,
    ) -> _SessionOwnership:
        # A remote caller can supply arbitrary resume IDs. Confirm a bounded,
        # existing snapshot before creating its per-session lease file, then
        # reload after acquiring ownership so a live writer cannot race resume.
        # New network sessions reserve their lease under the principal quota
        # lock so simultaneous admissions cannot make every contender fail.
        if resume and self._snapshot_storage_limits is not None:
            load_snapshot(
                self._session_co_dir,
                session_id,
                **self._snapshot_location(project_dir),
                storage_limits=self._snapshot_storage_limits,
            )
        if not resume and self._snapshot_storage_limits is not None:
            lease = acquire_bounded_new_session_lease(
                self._session_co_dir,
                session_id,
                self._snapshot_storage_limits,
            )
        else:
            lease = acquire_session_lease(self._session_co_dir, session_id)
        try:
            if resume:
                session, tools = load_snapshot(
                    self._session_co_dir,
                    session_id,
                    **self._snapshot_location(project_dir),
                    storage_limits=self._snapshot_storage_limits,
                )
            else:
                session, tools = None, {}
            return _SessionOwnership(lease, session, tools)
        except BaseException:
            if not resume and self._snapshot_storage_limits is not None:
                try:
                    discard_unpublished_session(
                        self._session_co_dir,
                        session_id,
                        lease,
                    )
                except Exception:
                    logger.warning(
                        "Unable to remove failed ACP session admission",
                        exc_info=True,
                    )
            else:
                lease.close()
            raise

    async def _connect_mcp_servers(
        self,
        mcp_servers: list[Any],
        project_dir: Path,
    ) -> Any | None:
        if not mcp_servers:
            return None
        connector = self._mcp_connector
        if connector is None:
            from .acp_mcp import connect_mcp_servers

            connector = connect_mcp_servers
        return await connector(
            mcp_servers,
            cwd=project_dir,
            loop=asyncio.get_running_loop(),
        )

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
            try:
                if runtime.mcp_pool is not None:
                    await runtime.mcp_pool.close()
            finally:
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
        if self._network_workspace is not None:
            # Keep files from one authenticated network principal in the same
            # private namespace as that principal's durable ACP sessions.
            private_upload_dir = self._session_co_dir / "uploads"
            private_upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            if os.name != "nt":
                os.chmod(private_upload_dir, 0o700)
            agent._upload_dir = private_upload_dir
        # A missing IO currently means "skip approvals". Keep construction
        # fail-closed; live ACP sessions install their generation-bound bridge.
        agent.io = acp_input or _FailClosedACPInput()
        return agent

    def _open_session_runtime(
        self,
        project_dir: Path,
        acp_input: _ACPEventBridge,
        session_id: str,
        extra_tools: list[Any],
        ownership: _SessionOwnership,
    ) -> _SessionRuntime:
        """Construct one runtime after ownership and external tools are ready."""

        lease = ownership.lease
        try:
            session = ownership.session
            tools = ownership.tools
            is_new = session is None
            agent = self._build_agent(project_dir, acp_input)
            for tool in extra_tools:
                agent.add_tool(tool)
            if session is None:
                session = self._fresh_persistent_session(agent, session_id)
            else:
                session = self._normalized_session_mode(session)
            if hasattr(agent, "_yolo_turns"):
                # In ACP, --yolo is an authority ceiling rather than a request
                # to re-arm Full access before every input. The persisted session below
                # already carries the exact current mode and bounded budget.
                agent._yolo_turns = None
            if hasattr(agent, "_yolo_needs_activation"):
                agent._yolo_needs_activation = False
            restore_tool_state(agent, tools)
            normalized_tools = capture_tool_state(agent)
            if is_new:
                save_snapshot(
                    self._session_co_dir,
                    session,
                    normalized_tools,
                    **self._snapshot_location(project_dir),
                    storage_limits=self._snapshot_storage_limits,
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

        live_session = copy.deepcopy(runtime.agent.current_session)
        if not isinstance(live_session, dict):
            raise SessionSnapshotError("Agent did not produce a session snapshot.")
        live_session["session_id"] = runtime.session_id
        live_session = self._normalized_session_mode(live_session)
        persistent_session = self._without_ephemeral_mcp_grants(
            runtime,
            live_session,
        )
        tools = capture_tool_state(runtime.agent)
        last_good_session = copy.deepcopy(persistent_session)
        last_good_tools = copy.deepcopy(tools)
        # Assignment and checkpoint preparation happen before disk commit. If
        # any of them fails, prompt rollback can still rely on the old file.
        runtime.agent.current_session = live_session
        save_snapshot(
            self._session_co_dir,
            persistent_session,
            tools,
            **self._snapshot_location(runtime.cwd),
            storage_limits=self._snapshot_storage_limits,
        )
        # os.replace inside save_snapshot is the final fallible commit step.
        # These reference assignments cannot split the durable snapshot from
        # the already-prepared in-memory checkpoint.
        runtime.last_good_session = last_good_session
        runtime.last_good_tools = last_good_tools

    @staticmethod
    def _without_ephemeral_mcp_grants(
        runtime: _SessionRuntime,
        session: dict[str, Any],
    ) -> dict[str, Any]:
        """Keep MCP approvals live only while this exact process pool exists."""

        if runtime.mcp_pool is None:
            return session
        persistent = copy.deepcopy(session)
        permissions = persistent.get("permissions")
        if not isinstance(permissions, dict):
            return persistent
        ephemeral_names = {
            tool.name
            for tool in runtime.mcp_pool.tools
            if isinstance(getattr(tool, "name", None), str)
        }
        persistent_permissions = {
            name: permission
            for name, permission in permissions.items()
            if not (
                name in ephemeral_names
                and isinstance(permission, dict)
                and permission.get("source") == "user"
            )
        }
        if persistent_permissions:
            persistent["permissions"] = persistent_permissions
        else:
            persistent.pop("permissions", None)
        return persistent

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
            await self._quarantine_runtime(runtime)
        runtime.active_operation = None

    def _fresh_persistent_session(
        self,
        agent: Any,
        session_id: str,
    ) -> dict[str, Any]:
        session = {
            "session_id": session_id,
            "messages": [{
                "role": "system",
                "content": str(getattr(agent, "system_prompt", "")),
            }],
            "trace": [],
            "turn": 0,
            "mode": READ_ONLY_PERMISSION_PROFILE,
            "plan": [],
        }
        if self._yolo:
            self._apply_mode(session, DANGER_FULL_ACCESS_PERMISSION_PROFILE)
        return self._normalized_session_mode(session)

    def _session_mode_state(self, runtime: _SessionRuntime) -> SessionModeState:
        modes = _ACP_SESSION_MODES if self._yolo else _ACP_SESSION_MODES[:2]
        return SessionModeState(
            current_mode_id=runtime.last_good_session["mode"],
            available_modes=[mode.model_copy(deep=True) for mode in modes],
        )

    def _normalized_session_mode(
        self,
        session: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate persisted authority-bearing mode state fail closed."""

        normalized = copy.deepcopy(session)
        migrate_legacy_full_access_fields(normalized)
        try:
            mode = legacy_permission_profile_id(
                normalized.get("mode", READ_ONLY_PERMISSION_PROFILE)
            )
        except ValueError:
            raise SessionSnapshotError("Session has an unsupported mode.")
        if mode == DANGER_FULL_ACCESS_PERMISSION_PROFILE:
            if not self._yolo:
                raise SessionSnapshotError(
                    "Session requires Full access launch authority."
                )
            turns = normalized.get("full_access_turns")
            turns_used = normalized.get("full_access_turns_used")
            if (
                isinstance(turns, bool)
                or not isinstance(turns, int)
                or turns <= 0
                or isinstance(turns_used, bool)
                or not isinstance(turns_used, int)
                or turns_used < 0
                or turns_used >= turns
                or isinstance(self._yolo_turns, bool)
                or not isinstance(self._yolo_turns, int)
                or self._yolo_turns <= 0
                or turns - turns_used > self._yolo_turns
                or normalized.get("skip_tool_approval") is not True
            ):
                raise SessionSnapshotError("Session has invalid Full access state.")
        elif any(key in normalized for key in _FULL_ACCESS_STATE_KEYS):
            raise SessionSnapshotError(
                "Session has Full access authority outside Full access mode."
            )
        normalized["mode"] = mode
        return normalized

    def _apply_mode(self, session: dict[str, Any], mode: str) -> None:
        for key in _FULL_ACCESS_STATE_KEYS:
            session.pop(key, None)
        session["mode"] = mode
        if mode == DANGER_FULL_ACCESS_PERMISSION_PROFILE:
            session["full_access_turns"] = self._yolo_turns
            session["full_access_turns_used"] = 0
            session["skip_tool_approval"] = True

    def _commit_mode(self, runtime: _SessionRuntime, mode: str) -> None:
        """Write the detached mode checkpoint before exposing it in memory."""

        session = copy.deepcopy(runtime.last_good_session)
        if session.get("mode") == mode:
            return
        self._apply_mode(session, mode)
        session = self._normalized_session_mode(session)
        tools = copy.deepcopy(runtime.last_good_tools)
        agent_session = copy.deepcopy(session)
        last_good_session = copy.deepcopy(session)
        next_prompt_session = (
            copy.deepcopy(session)
            if runtime.session_for_next_prompt is not None
            else None
        )
        save_snapshot(
            self._session_co_dir,
            session,
            tools,
            **self._snapshot_location(runtime.cwd),
            storage_limits=self._snapshot_storage_limits,
        )
        runtime.agent.current_session = agent_session
        runtime.last_good_session = last_good_session
        if next_prompt_session is not None:
            runtime.session_for_next_prompt = next_prompt_session
        if hasattr(runtime.agent, "_yolo_turns"):
            runtime.agent._yolo_turns = None
        if hasattr(runtime.agent, "_yolo_needs_activation"):
            runtime.agent._yolo_needs_activation = False

    def _validate_session_inputs(
        self,
        additional_directories: list[str] | None,
        mcp_servers: list[Any] | None,
    ) -> None:
        if additional_directories:
            raise RequestError.invalid_params(
                {"details": "co ai ACP does not support additionalDirectories yet"}
            )
        if mcp_servers and not self._allow_mcp:
            raise RequestError.invalid_params(
                {"details": "mcpServers require co ai --acp --acp-mcp"}
            )
        if mcp_servers:
            from .acp_mcp import MCPConfigError, validate_stdio_servers

            try:
                validate_stdio_servers(mcp_servers)
            except MCPConfigError as exc:
                raise RequestError.invalid_params(
                    {"details": str(exc)}
                ) from None

    def _run_prompt_generation(
        self,
        runtime: _SessionRuntime,
        generation: _TurnGeneration,
        prompt: _PromptInput,
        trace_start: int,
        upload_reservation: _UploadQuotaReservation | None,
    ) -> None:
        result = None
        error = None
        try:
            result = self._run_prompt(runtime, prompt, upload_reservation)
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
    ) -> tuple[ACPTerminal | None, _TurnFinished, CurrentModeUpdate | None]:
        terminal = None
        current_mode_update = None
        while True:
            item = await bridge.next_for(generation)
            if isinstance(item, _TurnFinished):
                return terminal, item, current_mode_update
            mapped = map_agent_event(item)
            if mapped.terminal is not None:
                if terminal is not None:
                    raise RuntimeError("Agent turn emitted more than one terminal event")
                terminal = mapped.terminal
            for update in mapped.updates:
                if isinstance(update, CurrentModeUpdate):
                    current_mode_update = update
                    continue
                await self._client.session_update(
                    session_id=session_id,
                    update=update,
                )

    async def _publish_committed_mode(
        self,
        runtime: _SessionRuntime,
        update: CurrentModeUpdate,
    ) -> None:
        """Announce internal mode only after its snapshot is durable."""

        try:
            await self._client.session_update(
                session_id=runtime.session_id,
                update=update,
            )
        except asyncio.CancelledError:
            await self._quarantine_runtime(runtime)
            raise
        except Exception:
            # The disk commit is already authoritative. Rolling memory back
            # here would split it from disk. The client may still display a
            # less privileged mode, so quarantine this runtime before it can
            # execute another prompt. Reconnect/resume re-advertises the exact
            # durable mode while the released lease keeps that path available.
            logger.warning(
                "Unable to publish committed ACP mode for session %s",
                runtime.session_id,
                exc_info=True,
            )
            await self._quarantine_runtime(runtime)

    async def _quarantine_runtime(self, runtime: _SessionRuntime) -> None:
        """Retire a divergent runtime and all resources before releasing it."""

        runtime.closing.set()
        runtime.acp_input.interrupt()
        if self._sessions.get(runtime.session_id) is runtime:
            self._sessions.pop(runtime.session_id)
        try:
            if runtime.mcp_pool is not None:
                await runtime.mcp_pool.close()
        finally:
            runtime.session_lease.close()

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

    async def _settle_unpublished_session_cleanup(
        self,
        session_id: str,
        lease: SessionLease,
    ) -> None:
        """Finish blocking unpublished-state cleanup without stalling the loop."""

        cleanup = asyncio.create_task(
            asyncio.to_thread(
                discard_unpublished_session,
                self._session_co_dir,
                session_id,
                lease,
            )
        )
        await self._settle_owned_task(cleanup)
        if cleanup.cancelled() or cleanup.exception() is None:
            return
        error = cleanup.exception()
        assert error is not None
        # Preserve the request's original failure or cancellation. An orphaned
        # canonical lease ID still consumes quota and therefore fails closed.
        logger.warning(
            "Unable to remove unpublished ACP session state",
            exc_info=(type(error), error, error.__traceback__),
        )

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

    def _run_prompt(
        self,
        runtime: _SessionRuntime,
        prompt: _PromptInput,
        upload_reservation: _UploadQuotaReservation | None,
    ) -> Any:
        try:
            session = runtime.session_for_next_prompt
            runtime.session_for_next_prompt = None
            attachments: dict[str, Any] = {}
            if prompt.images:
                attachments["images"] = list(prompt.images)
            if prompt.files:
                attachments["files"] = [dict(file) for file in prompt.files]
            if upload_reservation is not None:
                attachments["_upload_reservation"] = upload_reservation
            with self._process_context(runtime.cwd):
                if session is None:
                    return runtime.agent.input(prompt.text, **attachments)
                return runtime.agent.input(
                    prompt.text,
                    session=copy.deepcopy(session),
                    **attachments,
                )
        finally:
            runtime.prompt_active.clear()

    @staticmethod
    def _remove_failed_turn_uploads(agent: Any, trace_start: int) -> None:
        """Remove files written by an ACP turn that will be rolled back."""

        session = getattr(agent, "current_session", None)
        trace = session.get("trace") if isinstance(session, dict) else None
        agent_logger = getattr(agent, "logger", None)
        logger_co_dir = getattr(agent_logger, "co_dir", None)
        upload_dir_value = getattr(agent, "_upload_dir", None)
        if upload_dir_value is None and logger_co_dir is not None:
            upload_dir_value = Path(logger_co_dir) / "uploads"
        if not isinstance(trace, list) or upload_dir_value is None:
            return
        upload_dir = Path(upload_dir_value).resolve()
        for event in trace[trace_start:]:
            if not isinstance(event, dict) or event.get("type") != "files_received":
                continue
            for item in event.get("files", []):
                path_value = item.get("path") if isinstance(item, dict) else None
                if not isinstance(path_value, str):
                    continue
                path = Path(path_value)
                try:
                    if path.parent.resolve() == upload_dir:
                        path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Unable to remove rolled-back ACP upload %s",
                        path.name,
                    )

    def _reserve_network_uploads(
        self,
        prompt: _PromptInput,
    ) -> _UploadQuotaReservation | None:
        """Atomically bound retained files across this principal's sessions."""

        if self._network_workspace is None or not prompt.files:
            return None
        upload_dir = self._session_co_dir / "uploads"
        flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        lock_path = self._session_co_dir / "uploads.lock"
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError:
            raise RequestError.internal_error(
                {"details": "ACP upload storage is unavailable"}
            ) from None
        try:
            handle = os.fdopen(descriptor, "a+b")
            descriptor = -1
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise OSError("ACP upload lock is not a regular file")
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), 0o600)
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX)
            stored_bytes = 0
            stored_files = 0
            for entry in os.scandir(upload_dir):
                try:
                    entry_stat = entry.stat(follow_symlinks=False)
                except FileNotFoundError:
                    # Failed-turn rollback can only reduce quota usage. If it
                    # removes an entry returned by scandir, skip that stale view.
                    continue
                if not stat.S_ISREG(entry_stat.st_mode):
                    raise OSError("unexpected ACP upload entry")
                stored_bytes += entry_stat.st_size
                stored_files += 1
            requested_files = len(prompt.files)
            if (
                stored_bytes + prompt.file_bytes > self._max_upload_storage_bytes
                or stored_files + requested_files > self._max_upload_files
            ):
                raise RequestError.invalid_params(
                    {"details": "ACP upload storage quota exceeded"}
                )
            return _UploadQuotaReservation(handle)
        except BaseException as exc:
            if descriptor >= 0:
                os.close(descriptor)
            else:
                handle.close()
            if isinstance(exc, OSError):
                raise RequestError.internal_error(
                    {"details": "ACP upload storage is unavailable"}
                ) from None
            raise

    async def _acquire_network_upload_reservation(
        self,
        prompt: _PromptInput,
    ) -> _UploadQuotaReservation | None:
        """Wait for the cross-process quota lock without blocking the event loop."""

        acquisition = asyncio.create_task(
            asyncio.to_thread(self._reserve_network_uploads, prompt)
        )
        try:
            return await asyncio.shield(acquisition)
        except asyncio.CancelledError:
            await self._settle_owned_task(acquisition)
            if self._task_succeeded(acquisition):
                reservation = acquisition.result()
                if reservation is not None:
                    reservation.release()
            raise

    @contextmanager
    def _process_context(self, cwd: Path):
        with _PROCESS_CONTEXT_LOCK:
            if self._network_workspace is not None:
                with self._network_workspace.enter():
                    with redirect_stdout(sys.stderr):
                        yield
                return
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

    def _session_cwd(self, cwd: str) -> Path:
        """Resolve local stdio paths or the network-only virtual root."""

        if self._network_workspace is None:
            return self._validate_cwd(cwd)
        if cwd != "/":
            raise RequestError.invalid_params(
                {"details": "network ACP cwd must be the virtual workspace root /"}
            )
        return self._network_workspace.path

    def _snapshot_location(self, cwd: Path) -> dict[str, Path | str]:
        """Keep network persistence on an opaque virtual path."""

        if self._network_workspace is not None:
            return {"virtual_cwd": "/"}
        return {"cwd": cwd}

    def _parse_prompt(self, prompt: list[Any]) -> _PromptInput:
        parts: list[str] = []
        images: list[str] = []
        files: list[dict[str, str]] = []
        file_bytes = 0
        for block in prompt:
            if isinstance(block, TextContentBlock):
                parts.append(block.text)
                continue
            if isinstance(block, ImageContentBlock):
                self._check_attachment_count(len(images) + len(files) + 1)
                mime_type = self._image_mime_type(block.mime_type)
                data, _decoded_size = self._decode_attachment(block.data, "image")
                images.append(f"data:{mime_type};base64,{data}")
                continue
            if isinstance(block, EmbeddedResourceContentBlock):
                self._check_attachment_count(len(images) + len(files) + 1)
                resource = block.resource
                name = self._upload_name(resource.uri)
                mime_type = self._resource_mime_type(resource.mime_type)
                if isinstance(resource, TextResourceContents):
                    raw_data = resource.text.encode("utf-8")
                    self._check_attachment_size(len(raw_data), "file")
                    encoded = base64.b64encode(raw_data).decode("ascii")
                    decoded_size = len(raw_data)
                elif isinstance(resource, BlobResourceContents):
                    encoded, decoded_size = self._decode_attachment(
                        resource.blob,
                        "file",
                    )
                else:  # The official discriminated model should make this unreachable.
                    raise RequestError.invalid_params(
                        {"details": "Unsupported ACP embedded resource"}
                    )
                files.append(
                    {
                        "name": name,
                        "data": f"data:{mime_type};base64,{encoded}",
                    }
                )
                file_bytes += decoded_size
                continue
            if isinstance(block, ResourceContentBlock):
                label = block.title or block.name
                parts.append(f"Referenced resource: {label} ({block.uri})")
                continue
            raise RequestError.invalid_params(
                {"details": f"Unsupported ACP content block: {type(block).__name__}"}
            )
        return _PromptInput(
            text="\n\n".join(parts),
            images=tuple(images),
            files=tuple(files),
            file_bytes=file_bytes,
        )

    def _check_attachment_count(self, count: int) -> None:
        if count > self._max_attachments:
            raise RequestError.invalid_params(
                {"details": "Too many ACP prompt attachments"}
            )

    def _decode_attachment(self, value: str, kind: str) -> tuple[str, int]:
        encoded_limit = ((self._max_attachment_bytes + 2) // 3) * 4
        if len(value) > encoded_limit:
            raise RequestError.invalid_params(
                {"details": f"ACP {kind} exceeds the configured size limit"}
            )
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise RequestError.invalid_params(
                {"details": f"ACP {kind} is not valid base64"}
            ) from None
        self._check_attachment_size(len(decoded), kind)
        return value, len(decoded)

    def _check_attachment_size(self, size: int, kind: str) -> None:
        if size > self._max_attachment_bytes:
            raise RequestError.invalid_params(
                {"details": f"ACP {kind} exceeds the configured size limit"}
            )

    @staticmethod
    def _image_mime_type(value: str) -> str:
        mime_type = value.lower()
        if mime_type not in _IMAGE_MIME_TYPES:
            raise RequestError.invalid_params(
                {"details": "Unsupported ACP image MIME type"}
            )
        return mime_type

    @staticmethod
    def _resource_mime_type(value: str | None) -> str:
        mime_type = (value or "application/octet-stream").lower()
        if len(mime_type) > 127 or _MIME_TYPE.fullmatch(mime_type) is None:
            raise RequestError.invalid_params(
                {"details": "Unsupported ACP file MIME type"}
            )
        return mime_type

    @staticmethod
    def _upload_name(uri: str) -> str:
        parsed = urlsplit(uri)
        if (
            parsed.scheme != _UPLOAD_URI_SCHEME
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
            or parsed.path == "/"
        ):
            raise RequestError.invalid_params(
                {"details": "ACP file must use a connectonion-upload URI"}
            )
        encoded_name = parsed.path[1:]
        if re.search(r"%(?![0-9A-Fa-f]{2})", encoded_name):
            raise RequestError.invalid_params(
                {"details": "ACP upload filename is malformed"}
            )
        try:
            name = unquote_to_bytes(encoded_name).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise RequestError.invalid_params(
                {"details": "ACP upload filename is not valid UTF-8"}
            ) from None
        if (
            not name
            or name in {".", ".."}
            or name[-1] in {" ", "."}
            or _UNSAFE_FILENAME_CHARACTER.search(name) is not None
            or any(
                unicodedata.category(character) in {"Cc", "Cf", "Cs"}
                for character in name
            )
            or name.split(".", 1)[0].upper() in _WINDOWS_DEVICE_NAMES
            or len(name.encode("utf-8")) > 255
        ):
            raise RequestError.invalid_params(
                {"details": "ACP upload filename is unsafe"}
            )
        return name


def create_acp_agent(
    *,
    model: str,
    max_iterations: int,
    yolo: bool,
    yolo_turns: int,
    agent_factory: AgentFactory | None = None,
    session_co_dir: Path | None = None,
    network_workspace: _BoundNetworkWorkspace | None = None,
    input_limits: Mapping[str, int | float] | None = None,
    allow_mcp: bool = False,
) -> ConnectOnionACPAgent:
    """Build the shared ACP lifecycle adapter for stdio or network transport."""

    return ConnectOnionACPAgent(
        model=model,
        max_iterations=max_iterations,
        yolo=yolo,
        yolo_turns=yolo_turns,
        agent_factory=agent_factory,
        session_co_dir=session_co_dir,
        network_workspace=network_workspace,
        input_limits=input_limits,
        allow_mcp=allow_mcp,
    )


async def serve_acp(
    *,
    model: str,
    max_iterations: int,
    yolo: bool,
    yolo_turns: int,
    allow_mcp: bool = False,
    state_dir: Path | None = None,
) -> None:
    """Serve ``co ai`` as an ACP v1 Agent until the client closes stdin."""

    agent_factory = None
    if state_dir is not None:
        from ..commands.ai_commands import _create_agent

        def agent_factory(**kwargs: Any) -> Any:
            return _create_agent(**kwargs, state_dir=state_dir)

    transport = await open_stdio_transport()
    agent = create_acp_agent(
        model=model,
        max_iterations=max_iterations,
        yolo=yolo,
        yolo_turns=yolo_turns,
        agent_factory=agent_factory,
        session_co_dir=state_dir,
        allow_mcp=allow_mcp,
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
