"""
Purpose: The Host answers inbox messages, the way it answers a socket or a clock — one more ingress, one existing turn
LLM-Note:
  Dependencies: imports from [threading, uuid, pathlib, inbox/ (Inbox, provider, settings), host/http_router.py] | imported by [network/host/server.py via create_inbox_lifespan()] | tested by [tests/unit/test_host_inbox.py]
  Data flow: Inbox.serve(handler) → channel.answers(message)? → input_handler(create_agent, storage, text, session=uuid5(provider:chat:thread)) → provider.send(reply) → Inbox.record_sent + done
  State/Effects: one background listener process per channel, one consumer thread per channel, turns recorded in .co/session_results.jsonl with via and requester | sends replies through the provider
  Integration: exposes create_inbox_lifespan(), returning the (on_startup, on_shutdown) pair server.py already composes for the relay and the schedule
  Performance: a turn runs in the consumer's own thread, so the event loop and the heartbeat are untouched by a four-minute answer
  Errors: a turn that raises leaves its message in cur/ for the hourly sweep | a channel that cannot start is one line on the console and does not stop the Host

Why the listener is still a separate process, when this is not: DD-063 rejected
putting the SDK connection, the dedup and the staging inside the Host, and that
still holds for two reasons a socket does not have. Feishu waits about three
seconds and does not hold the connection for the reply, so a queue has to sit
between receipt and processing — and the Host has none, refusing a second INPUT
on a running session. And receipt has to survive a Host restart, so the two have
different lifetimes. This is the split Postfix has between smtpd and qmgr.

What DD-063 did not reject is the Host reading the directory. Its own list of
consumers says the tool knows none of them; the Host is one. Arriving through
input_handler is what puts a message from a group in session_results.jsonl
beside the interactive ones, under the same session rules, visible to anything
that reads them.
"""

import threading
import uuid
from pathlib import Path

# One session per conversation, stable across restarts: the same chat and
# thread must name the same session tomorrow, or every reconnect starts the
# conversation over.
SESSION_NAMESPACE = uuid.UUID("9a1f4c6d-3e52-4f8b-9d27-5c0e1b73a8f4")


def session_id_for(provider: str, message) -> str:
    return str(uuid.uuid5(SESSION_NAMESPACE, f"{provider}:{message.chat}:{message.thread or ''}"))


def create_inbox_lifespan(co_dir: Path, create_agent, storage, result_ttl: int,
                          console=None, channels=None):
    """Start and stop the channel consumers alongside the ASGI app.

    Returns (on_startup, on_shutdown), the same pair shape the relay and the
    schedule use, so server.py can compose them.
    """
    from ...inbox import Inbox
    from ...inbox import provider as provider_for
    from ...inbox.settings import configured_channels

    stop = threading.Event()
    threads: list = []

    def _say(message: str) -> None:
        if console:
            console.print(f"[dim][inbox][/dim] {message}")

    def _handler(channel, inbox, provider):
        def answer(message) -> None:
            if not channel.answers(message):
                inbox.log(f"{message.id} not addressed to us; nothing to answer")
                return

            from .http_router import input_handler

            session_id = session_id_for(channel.provider, message)
            result = input_handler(
                create_agent, storage, message.text, result_ttl,
                session={
                    "session_id": session_id,
                    # Recorded, not checked: 1.8.5 answers anyone who can
                    # address the bot, and the allowlist in #1479 wants this
                    # field to already exist when it arrives.
                    "requester": {"address": f"{channel.provider}:{message.sender}", "level": "open"},
                    "via": channel.provider,
                },
            )
            reply = (result.get("result") or "").strip()
            if not reply:
                inbox.log(f"nothing to say for {message.id}")
                return
            try:
                sent = provider.send(message.chat, reply, reply_to=message.id)
            except Exception as exc:
                inbox.record_sent(chat=message.chat, text=reply, reply_to=message.id,
                                  error=str(exc), by="host")
                raise RuntimeError(f"reply failed: {exc}") from exc
            inbox.record_sent(chat=message.chat, text=reply, reply_to=message.id,
                              provider_id=sent, by="host")

        return answer

    async def on_startup() -> None:
        try:
            wanted = channels if channels is not None else configured_channels(co_dir)
        except ValueError as error:
            # The Host keeps serving: a channel misconfiguration must not take
            # down an agent that is also reachable over OIP. It is said once,
            # loudly, because silence here reads as "no channels configured".
            _say(f"[red]{error}[/red]")
            return
        for channel in wanted:
            inbox = Inbox(channel.provider)
            try:
                provider = provider_for(channel.provider)
                if inbox.ensure_listener() is None:
                    _say(f"[yellow]{channel.provider}: listener did not start; "
                         f"see {inbox.logfile}[/yellow]")
                    continue
            except Exception as error:
                _say(f"[yellow]{channel.provider}: {error}[/yellow]")
                continue
            thread = threading.Thread(
                target=inbox.serve, args=(_handler(channel, inbox, provider),),
                kwargs={"workers": 1, "should_stop": stop, "by": "host"},
                name=f"inbox-{channel.provider}", daemon=True)
            thread.start()
            threads.append(thread)
            _say(f"answering {channel.provider}")

    async def on_shutdown() -> None:
        stop.set()
        for thread in threads:
            thread.join(timeout=5)

    return on_startup, on_shutdown
