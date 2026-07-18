"""Run blocking agent steps without making user interrupts wait for them."""

import threading
from typing import Any, Callable, TypeVar


T = TypeVar("T")


class AgentInterrupted(Exception):
    """Raised when a blocking interaction consumes a user INTERRUPT frame."""


def run_interruptible(
    fn: Callable[[], T],
    io: Any,
    poll_seconds: float = 0.2,
) -> tuple[T | None, bool]:
    """Return ``(result, False)`` or abandon the daemon worker on interrupt."""
    receive_all = getattr(io, "receive_all", None) if io is not None else None
    restore = getattr(io, "send_to_agent", None) if io is not None else None
    declared_receive_all = getattr(type(io), "receive_all", None) if io is not None else None
    if (
        not callable(receive_all)
        or not callable(declared_receive_all)
        or not callable(restore)
    ):
        return fn(), False

    if receive_all("INTERRUPT"):
        return None, True

    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = fn()
        except BaseException as exc:
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    while worker.is_alive():
        worker.join(timeout=poll_seconds)
        if not worker.is_alive():
            break
        interrupts = receive_all("INTERRUPT")
        if interrupts and not worker.is_alive():
            for message in interrupts:
                restore(message)
            break
        if interrupts:
            return None, True

    if "error" in box:
        raise box["error"]
    return box.get("result"), False
