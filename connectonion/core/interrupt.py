"""Run blocking agent steps while keeping the interrupt mailbox responsive."""

import threading
from typing import Any, Callable, Tuple


class UserInterrupt(Exception):
    """Internal control flow for an interrupt consumed by a blocking gate."""


def _take_interrupt(io: Any) -> bool:
    """Drain a pending interrupt from an IO implementation honoring the API."""
    messages = io.receive_all("INTERRUPT")
    # IO.receive_all() is specified to return a list. Treat an unconfigured
    # test double or incompatible duck type as no signal instead of as truthy.
    return bool(messages) if isinstance(messages, list) else False


def run_interruptible(
    fn: Callable[[], Any],
    io: Any,
    poll_seconds: float = 0.2,
) -> Tuple[Any, bool]:
    """Return ``(result, False)`` or abandon ``fn`` on user interrupt.

    Python cannot safely kill arbitrary running code. In hosted mode the call
    therefore runs on a disposable daemon thread while the agent thread polls
    the selective INTERRUPT mailbox. The abandoned callable may keep running,
    but its late return value is never committed by the caller.
    """
    if io is None or not hasattr(io, "receive_all"):
        return fn(), False

    if _take_interrupt(io):
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
        if _take_interrupt(io):
            return None, True

    if "error" in box:
        raise box["error"]
    return box["result"], False
