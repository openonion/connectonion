"""
Purpose: Hand inbox messages to a handler — one lane per conversation, ordered inside a lane, parallel across lanes
LLM-Note:
  Dependencies: imports from [threading, queue, time, inbox/store.py] | imported by [inbox/store.py via Inbox.serve, cli/commands/listen_commands.py, network/host/inbox.py] | tested by [tests/unit/test_inbox_consumer.py]
  Data flow: Inbox.receive() → lane_key(message) → that lane's queue → worker thread → handler(message) → done() on return, left in cur/ on exception
  State/Effects: threads only; every durable effect goes through the Inbox (done.jsonl, the queue files, log) | renews the lease on cur/<file> while a handler runs
  Integration: knows nothing about Agents, providers or replies — the handler owns those, so the same loop serves `co feishu serve -- CMD`, `co ai --listen` and the Host lifespan
  Performance: one thread per active conversation, capped by `workers` for the part that costs money (the handler); an idle lane exits after idle_seconds
  Errors: a handler that raises leaves its message taken, so the hourly sweep offers it again | a message already handed out max_attempts times is completed with a "gave up" line instead of being handed out again

Why a lane and not a thread pool: a pool answers two messages from the same
person at the same time and replies to them out of order. A lane per
conversation is Kafka's partition-by-key and Erlang's process-per-session:
strict order where a human would notice, and no waiting where they would not.
"""

import queue
import threading
import time
from typing import Callable, Optional

# What a conversation is, when the caller does not say. Two threads of one
# group are two conversations: they are two questions, and the people asking
# them are not waiting on each other.
def default_lane(message) -> str:
    return f"{message.chat}:{message.thread or ''}"


# Put in a lane's queue to tell it there is no more work coming.
_CLOSED = object()


class _Lane:
    """One conversation. Its thread takes messages one at a time, in order."""

    def __init__(self, name: str, loop: "_Loop"):
        self.name = name
        self.loop = loop
        self.queue: "queue.Queue" = queue.Queue()
        self.thread = threading.Thread(target=self._run, name=f"inbox-{name}", daemon=True)

    def _run(self) -> None:
        while True:
            try:
                message = self.queue.get(timeout=self.loop.idle_seconds)
            except queue.Empty:
                # Nothing for a while. Retire, after telling the loop, so a
                # machine that talks to a thousand people over a week holds a
                # thousand threads for none of it.
                if self.loop.retire(self):
                    return
                continue
            if message is _CLOSED:
                # The loop is finishing. Asked for by name rather than by
                # watching a flag, so a lane waiting out a ten-minute idle
                # timeout stops now instead of at the end of it.
                return
            self.loop.handle(message)


class _Loop:
    def __init__(self, inbox, handler, *, lane_key, workers, lease_seconds,
                 max_attempts, idle_seconds, should_stop):
        self.inbox = inbox
        self.handler = handler
        self.lane_key = lane_key
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.idle_seconds = idle_seconds
        self.should_stop = should_stop or threading.Event()
        # The cap is on handlers, not on lanes: a lane costs a sleeping thread,
        # a handler costs a model call.
        self.slots = threading.Semaphore(workers)
        self.lanes: dict = {}
        self.guard = threading.Lock()

    def stopped(self) -> bool:
        return self.should_stop.is_set()

    def retire(self, lane: "_Lane") -> bool:
        """Remove an idle lane, unless a message arrived while we decided to."""
        with self.guard:
            if not lane.queue.empty():
                return False
            if self.lanes.get(lane.name) is lane:
                del self.lanes[lane.name]
            return True

    def dispatch(self, message) -> None:
        name = self.lane_key(message)
        with self.guard:
            lane = self.lanes.get(name)
            if lane is None or not lane.thread.is_alive():
                lane = _Lane(name, self)
                self.lanes[name] = lane
                lane.thread.start()
            lane.queue.put(message)

    def handle(self, message) -> None:
        self.slots.acquire()
        keep_alive = threading.Event()
        lease = threading.Thread(
            target=self._renew, args=(message.id, keep_alive), daemon=True)
        lease.start()
        try:
            self.handler(message)
        except Exception as error:
            # The message stays in cur/. An hour from now the sweep offers it
            # to whoever is running then, which is the promise the directory
            # makes; completing it here would turn every transient failure
            # into an unanswered question.
            self.inbox.log(f"{message.id} not finished: {type(error).__name__}: {error}")
        else:
            self.inbox.done(message.id)
        finally:
            keep_alive.set()
            lease.join(timeout=1)
            self.slots.release()

    def _renew(self, message_id: str, keep_alive: threading.Event) -> None:
        """Say the handler is still alive, for as long as it is.

        Without this the stale window is a guess about how long an answer
        takes, and a handler slower than the guess has its message taken away
        mid-sentence and answered twice. With it the window only has to be
        longer than a renewal, and the sweep reclaims from processes that
        really died.
        """
        while not keep_alive.wait(self.lease_seconds):
            try:
                self.inbox.renew(message_id)
            except Exception as error:  # a renewal is never worth killing a turn
                self.inbox.log(f"lease renewal failed for {message_id}: {error}")
                return

    def run(self, *, once: bool) -> None:
        while not self.stopped():
            message = self.inbox.receive(timeout=0.25)
            if message is None:
                continue
            attempts = self.inbox.attempts(message.id)
            if self.max_attempts and attempts > self.max_attempts:
                # It has been handed out, and come back, more times than a
                # working message ever does. Something about this one breaks
                # whoever takes it; handing it out again just breaks the next
                # consumer too, every hour, forever.
                self.inbox.log(
                    f"gave up on {message.id} after {attempts - 1} attempts")
                self.inbox.done(message.id)
                continue
            self.dispatch(message)
            if once:
                break
        self.drain()

    def drain(self) -> None:
        """Let the lanes finish what they took; they own messages we cannot.

        Each is told by name that nothing more is coming, so a lane idling on
        a ten-minute timeout leaves now. What a lane is already handling still
        runs to its end: the alternative is a message taken, half answered,
        and left looking answered.
        """
        with self.guard:
            lanes = list(self.lanes.values())
        for lane in lanes:
            lane.queue.put(_CLOSED)
        for lane in lanes:
            lane.thread.join(timeout=30)


def serve(inbox, handler: Callable, *, lane_key: Optional[Callable] = None,
          workers: int = 4, lease_seconds: float = 300.0, max_attempts: int = 3,
          idle_seconds: float = 600.0, once: bool = False,
          should_stop: Optional[threading.Event] = None) -> None:
    """Take messages from `inbox` and give them to `handler`, forever.

    `handler(message)` owns the outcome. Returning means the message is
    finished, however it was finished: an answer sent, or a decision to stay
    silent. Raising means it is not finished, and the message waits in cur/
    for the sweep. That is the whole contract, which is why the same loop can
    drive a subprocess, an Agent, or a Host.

    Blocks until `should_stop` is set.
    """
    loop = _Loop(inbox, handler, lane_key=lane_key or default_lane, workers=workers,
                 lease_seconds=lease_seconds, max_attempts=max_attempts,
                 idle_seconds=idle_seconds, should_stop=should_stop)
    loop.run(once=once)
