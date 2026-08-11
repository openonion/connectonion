"""Run blocking agent steps while keeping the interrupt mailbox responsive."""

import threading
from typing import Any, Callable, Optional, Tuple


class UserInterrupt(Exception):
    """Internal control flow for an interrupt consumed by a blocking gate."""


class InterruptibleIO:
    """Revocable IO view held by one agent-injected tool invocation."""

    def __init__(self, io: Any):
        self.__io = io
        self._cancelled = threading.Event()
        self._gate = threading.Lock()

    def cancel(self) -> None:
        with self._gate:
            self._cancelled.set()

    def is_cancelled(self) -> bool:
        """Let cooperative blocking tools stop their own external work."""
        return self._cancelled.is_set()

    def send(self, event) -> None:
        with self._gate:
            if not self._cancelled.is_set():
                self.__io.send(event)

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

    def request_approval(self, tool: str, arguments) -> bool:
        self.send({"type": "approval_needed", "tool": tool, "arguments": arguments})
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
