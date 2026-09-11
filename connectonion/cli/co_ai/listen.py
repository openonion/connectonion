"""
Purpose: Answer inbox messages with the co-ai agent — the first consumer of the directory the listener writes
LLM-Note:
  Dependencies: imports from [threading, inbox/ (Inbox, provider, settings)] | imported by [cli/commands/ai_commands.py] | tested by [tests/unit/test_co_ai_listen.py]
  Data flow: Channel → Inbox.serve(handler) → channel.answers(message)? → agent.input(text, session per conversation) → provider.send(reply) → Inbox.record_sent + done
  State/Effects: one background listener per channel (auto-started), one session dict per conversation held in memory, replies sent through the provider
  Integration: this is the consumer half DD-063 left to whoever consumes the directory; the inbox package still knows nothing about Agents
  Performance: one conversation answered at a time by default — see the note on workers below
  Errors: a turn that raises leaves its message in cur/ for the hourly sweep, so a model outage costs a delay and not an unanswered question

Why one at a time: an Agent's session lives on the object, so two threads
calling input() on one Agent interleave two conversations into one history.
Answering conversations in parallel needs an Agent each, which is a cost worth
measuring before it is spent; until then the lanes still give ordering, lease
renewal and the give-up rule, and a slow turn delays the next answer rather
than corrupting it.
"""

import threading
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from ...inbox import Inbox, provider as _provider
from ...inbox.settings import Channel


def _inbox_for(name: str) -> Inbox:
    return Inbox(name)


def _provider_for(name: str):
    return _provider(name)


def conversation_of(message) -> str:
    """One session per chat, and per thread where the platform has threads:
    two threads of a group are two questions, and answering them from one
    history makes each one read as a non-sequitur to the other."""
    return f"{message.chat}:{message.thread or ''}"


def _handler(channel: Channel, inbox: Inbox, provider, agent, sessions: dict, guard: threading.Lock):
    def answer(message) -> None:
        if not channel.answers(message):
            # Finished, not left behind: it is never going to become ours, and
            # a message the sweep re-offers every hour is a message that fills
            # the log until someone deletes it by hand.
            inbox.log(f"{message.id} not addressed to us; nothing to answer")
            return

        key = conversation_of(message)
        with guard:
            # A first turn passes no session: a session dict without the
            # system prompt in `messages` would start the agent with no
            # instructions at all, which is worse than starting fresh.
            reply = agent.input(message.text, session=sessions.get(key))
            session = agent.current_session
            # Anyone who can address the bot may command it in 1.8.5. The
            # sender is written down anyway, so the allowlist in #1479 starts
            # with data rather than with a migration.
            session["requester"] = {"address": f"{inbox.provider}:{message.sender}", "level": "open"}
            sessions[key] = session

        if not (reply or "").strip():
            inbox.log(f"nothing to say for {message.id}")
            return
        try:
            sent = provider.send(message.chat, reply, reply_to=message.id)
        except Exception as exc:
            inbox.record_sent(chat=message.chat, text=reply, reply_to=message.id, error=str(exc))
            raise RuntimeError(f"reply failed: {exc}") from exc
        inbox.record_sent(chat=message.chat, text=reply, reply_to=message.id, provider_id=sent)

    return answer


def listen(channels: Sequence[Channel], agent_factory: Callable, *,
           workers: int = 1, idle_seconds: float = 600.0,
           should_stop: Optional[threading.Event] = None,
           once: bool = False) -> None:
    """Answer every channel's messages with one agent. Blocks until stopped."""
    if not channels:
        return
    agent = agent_factory()
    guard = threading.Lock()          # one Agent, one turn at a time
    sessions: dict = {}
    stop = should_stop or threading.Event()

    loops = []
    for channel in channels:
        inbox = _inbox_for(channel.provider)
        provider = _provider_for(channel.provider)
        inbox.ensure_listener()
        handler = _handler(channel, inbox, provider, agent, sessions, guard)
        loops.append(threading.Thread(
            target=inbox.serve, args=(handler,),
            kwargs={"workers": workers, "idle_seconds": idle_seconds,
                    "should_stop": stop, "once": once},
            name=f"listen-{channel.provider}", daemon=True))

    for loop in loops:
        loop.start()
    try:
        for loop in loops:
            while loop.is_alive():
                loop.join(timeout=0.2)
    except KeyboardInterrupt:
        stop.set()
        for loop in loops:
            loop.join(timeout=5)
