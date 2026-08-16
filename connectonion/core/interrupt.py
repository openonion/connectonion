"""Run blocking agent steps while keeping the interrupt mailbox responsive."""

import copy
import threading
from typing import Any, Callable, Optional, Tuple

from .provider_events import provider_status_summary, provider_terminal_summary


class UserInterrupt(Exception):
    """Internal control flow for an interrupt consumed by a blocking gate."""


class InterruptibleIO:
    """Revocable IO view held by one agent-injected tool invocation."""

    def __init__(self, io: Any):
        self.__io = io
        self._cancelled = threading.Event()
        self._gate = threading.Lock()
        self._deferred: list[tuple[bool, Any]] = []
        # Provider events need a live presentation lane: their canonical trace
        # still waits for the transactional tool session to commit, but a coding
        # Work Room must not wait minutes to say that work has started.  Keep the
        # currently visible provider invocations so cancellation can close their
        # presentation without publishing any uncommitted session state.
        self._live_provider_invocations: dict[str, dict[str, Any]] = {}
        self._cancelled_provider_invocations: set[str] = set()

    def cancel(self) -> None:
        with self._gate:
            if self._cancelled.is_set():
                return
            for invocation in self._live_provider_invocations.values():
                self.__io.send({**invocation, "status": "cancelled"})
            self._live_provider_invocations.clear()
            self._cancelled.set()
            self._deferred.clear()

    def commit(self) -> bool:
        """Publish Agent-owned state only after its tool transaction commits."""
        with self._gate:
            if self._cancelled.is_set():
                self._deferred.clear()
                return False
            for persisted, event in self._deferred:
                if persisted:
                    sender = getattr(
                        self.__io, "_send_persisted_trace", self.__io.send
                    )
                    sender(event)
                else:
                    self.__io.send(event)
            self._deferred.clear()
            return True

    def is_cancelled(self) -> bool:
        """Let cooperative blocking tools stop their own external work."""
        return self._cancelled.is_set()

    def is_provider_cancelled(self, invocation_id: str) -> bool:
        """Consume a scoped provider stop without revoking the enclosing turn."""
        if self._cancelled.is_set() or not isinstance(invocation_id, str) or not invocation_id:
            return self._cancelled.is_set()
        with self._gate:
            if invocation_id in self._cancelled_provider_invocations:
                return True
        take_provider_interrupt = getattr(type(self.__io), "take_provider_interrupt", None)
        if take_provider_interrupt and take_provider_interrupt(self.__io, invocation_id):
            return self.cancel_provider(invocation_id)
        return False

    def cancel_provider(self, invocation_id: str) -> bool:
        """Publish one honest target terminal state and revoke that provider only."""
        with self._gate:
            invocation = self._live_provider_invocations.pop(invocation_id, None)
            if invocation is None or self._cancelled.is_set():
                return False
            self._cancelled_provider_invocations.add(invocation_id)
            self.__io.send({
                **invocation,
                "status": "cancelled",
                # Use the same finite Work Room vocabulary as the provider
                # adapter. A targeted stop must not introduce a one-off raw
                # presentation string that an independently deployed React
                # client cannot safely recognize.
                "currentSummary": provider_status_summary("cancelled"),
                "resultSummary": provider_terminal_summary("cancelled"),
            })
            return True

    def send(self, event) -> None:
        with self._gate:
            if not self._cancelled.is_set():
                if event.get("type") == "session_sync":
                    self._deferred.append((False, copy.deepcopy(event)))
                else:
                    self.__io.send(event)

    def _send_persisted_trace(self, event) -> None:
        """Defer Agent-owned provenance until the copied session commits."""
        with self._gate:
            if not self._cancelled.is_set():
                self._deferred.append((True, copy.deepcopy(event)))

    def send_live_trace(self, event: dict[str, Any]) -> bool:
        """Show one provider event now without committing its copied trace.

        ``execute_single_tool`` deliberately makes a hosted tool transactional:
        its session and canonical trace are published only after the tool
        returns.  Native coding providers are long-running, though, so their
        start and child activity events require a non-persistent presentation
        lane.  The same event (including its stable trace id) is later sent by
        ``commit()``; clients upsert it rather than creating a duplicate.
        """
        with self._gate:
            if self._cancelled.is_set():
                return False
            live = copy.deepcopy(event)
            if live.get("type") == "provider_invocation":
                invocation_id = live.get("invocationId")
                status = live.get("status")
                if isinstance(invocation_id, str) and invocation_id:
                    if status in {"completed", "failed", "cancelled"}:
                        self._live_provider_invocations.pop(invocation_id, None)
                    else:
                        self._live_provider_invocations[invocation_id] = live
            self.__io.send(live)
            return True

    def receive(self):
        response = self.__io.receive_interruptibly(self._cancelled)
        if response.get("type") == "INTERRUPT":
            raise UserInterrupt()
        return response

    def receive_all(self, msg_type=None):
        messages = self.__io.receive_all_interruptibly(self._cancelled, msg_type)
        if messages is None:
            raise UserInterrupt()
        if any(message.get("type") == "INTERRUPT" for message in messages):
            raise UserInterrupt()
        return messages

    def log(self, event_type: str, **data) -> None:
        with self._gate:
            if not self._cancelled.is_set():
                # Preserve the lease's atomic cancellation gate while reusing
                # the underlying IO boundary's wire-event normalization.
                self.__io.log(event_type, **data)

    def request_approval(self, tool: str, arguments, *, context=None) -> bool:
        event = {"type": "approval_needed", "tool": tool, "arguments": arguments}
        if isinstance(context, dict):
            for key in ("provider", "invocationId", "parentToolCallId", "activityId"):
                value = context.get(key)
                if isinstance(value, str) and value:
                    event[key] = value
            # Native providers construct this small, verified presentation
            # envelope before entering the revocable tool lease.  Preserve it
            # exactly here: without it hosted Work Rooms fail closed as an
            # unknown boundary even when Core has verified the request is
            # confined to the selected workspace.  Never copy arbitrary
            # callback fields; only the dedicated presentation object crosses
            # this boundary.
            presentation = context.get("providerApproval")
            if isinstance(presentation, dict):
                event["providerApproval"] = copy.deepcopy(presentation)
        self.send(event)
        return self.receive().get("approved", False)

    def send_image(self, image_data: str) -> None:
        self.send({"type": "agent_image", "image": image_data})


def _take_interrupt(io: Any, on_interrupt: Optional[Callable[[], None]] = None) -> bool:
    """Drain a pending interrupt from an IO implementation honoring the API."""
    # Look on the class so dynamic test doubles do not fabricate support for
    # the optional atomic protocol via __getattr__.
    take_interrupt = getattr(type(io), "take_interrupt", None)
    if take_interrupt:
        return take_interrupt(io, on_interrupt)
    messages = io.receive_all("INTERRUPT")
    # IO.receive_all() is specified to return a list. Treat an unconfigured
    # test double or incompatible duck type as no signal instead of as truthy.
    interrupted = bool(messages) if isinstance(messages, list) else False
    if interrupted and on_interrupt:
        on_interrupt()
    return interrupted


def run_interruptible(
    fn: Callable[[], Any],
    io: Any,
    poll_seconds: float = 0.2,
    on_interrupt: Optional[Callable[[], None]] = None,
) -> Tuple[Any, bool]:
    """Return ``(result, False)`` or abandon ``fn`` on user interrupt.

    Python cannot safely kill arbitrary running code. In hosted mode the call
    therefore runs on a disposable daemon thread while the agent thread polls
    the selective INTERRUPT mailbox. The abandoned callable may keep running,
    but its late return value is never committed by the caller.
    """
    if io is None or not hasattr(io, "receive_all"):
        return fn(), False

    if _take_interrupt(io, on_interrupt):
        return None, True

    box = {}

    def run() -> None:
        try:
            box["result"] = fn()
        except BaseException as error:
            box["error"] = error

    worker = threading.Thread(
        target=run,
        name="connectonion-interruptible-step",
        daemon=True,
    )
    worker.start()

    while worker.is_alive():
        worker.join(timeout=poll_seconds)
        # Completed work wins the race. Leave a simultaneous interrupt queued
        # for the next step or the existing iteration-boundary backstop.
        if not worker.is_alive():
            break
        if _take_interrupt(io, on_interrupt):
            return None, True

    if "error" in box:
        raise box["error"]
    return box["result"], False
