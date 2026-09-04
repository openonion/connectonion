"""
Purpose: The verbs of a mailbox provider — `co feishu listen | receive | send | reply | done | check | ls | log | serve`
LLM-Note:
  Dependencies: imports from [json, os, subprocess, sys, threading, time, typing, rich.console, listen/] | imported by [cli/main.py via _mailbox_group()] | tested by [tests/unit/test_listen_commands.py]
  Data flow: handle_listen → provider.run(mailbox) until Ctrl-C | handle_receive → mailbox.receive() → one JSON line on stdout | handle_send/handle_reply → stdin or argument → provider.send() → outbox.jsonl → the new message id on stdout | handle_serve → receive → subprocess(stdin=message) → reply(stdout)
  State/Effects: everything durable lives in the mailbox directory | listen holds listen.lock and returns stale cur/ files every minute | receive and serve start a background listener when none runs
  Integration: one set of handlers for every provider name in listen.PROVIDERS; main.py registers the same nine commands under each group | exit codes: 0 ok, 1 failure, 2 usage (Typer), 3 configuration missing, 124 receive timed out (as timeout(1))
  Errors: a missing credential prints the item and the next action and exits 3 | a provider refusal prints its own words and exits 1 | nothing is printed on the success path of listen (Rule of Silence); the log has it
"""

import json
import os
import subprocess
import sys
import threading
import time
from typing import List, Optional

from rich.console import Console

from ...listen import Mailbox, provider

console = Console()
errors = Console(stderr=True)

EXIT_CONFIG = 3
EXIT_TIMEOUT = 124


def _configured(name: str):
    """The provider, or exit 3 with what is missing. Every verb that talks
    to the platform starts here so the message is the same everywhere."""
    p = provider(name)
    problems = p.missing()
    if problems:
        for problem in problems:
            errors.print(problem, style="red")
        sys.exit(EXIT_CONFIG)
    return p


def _text_from(argument: Optional[str]) -> str:
    """The argument if given, else stdin, like mail(1)."""
    if argument is not None:
        return argument
    if sys.stdin.isatty():
        errors.print("nothing to send: pass the text as an argument or on stdin", style="red")
        sys.exit(2)
    return sys.stdin.read().rstrip("\n")


def _listener_or_exit(mailbox: Mailbox) -> None:
    """Make sure a listener is running, or say why one could not start."""
    if mailbox.ensure_listener() is None:
        errors.print(f"the listener exited at once; the reason is at the end of {mailbox.logfile}", style="red")
        sys.exit(1)


def handle_done(name: str, message_id: str) -> None:
    """Forget a taken message without replying, so it does not come back."""
    Mailbox(name).done(message_id)


def handle_listen(name: str, raw: bool = False) -> None:
    """Hold the connection and write every message to the mailbox."""
    p = _configured(name)
    mailbox = Mailbox(name)
    if not mailbox.hold_lock():
        errors.print(f"already listening (pid {mailbox.listener_pid()}); one listener per directory", style="yellow")
        sys.exit(1)

    stop = threading.Event()

    def sweep():
        while not stop.wait(60):
            try:
                released = mailbox.release_stale()
            except OSError as exc:  # the sweep must outlive one bad file
                mailbox.log(f"stale sweep failed: {exc}")
                continue
            if released:
                mailbox.log(f"returned {released} stale message(s) to new/")

    threading.Thread(target=sweep, daemon=True).start()
    errors.print(f"listening · {mailbox.root}", style="dim")
    try:
        p.run(mailbox, raw=raw)
    except KeyboardInterrupt:
        mailbox.log("stopped by Ctrl-C")
    finally:
        stop.set()
        mailbox.log("listener stopped")
        mailbox.release_lock()


# While waiting with no deadline, look at the listener this often so a
# listener that died an hour into the wait is restarted, not waited for.
WATCH_SECONDS = 60


def _receive(mailbox: Mailbox, timeout: Optional[float], watch: bool):
    if not watch or timeout is not None:
        return mailbox.receive(timeout)
    while True:
        message = mailbox.receive(WATCH_SECONDS)
        if message is not None:
            return message
        _listener_or_exit(mailbox)


def handle_receive(name: str, timeout: Optional[float] = None, start: bool = True) -> None:
    """Print the next message as one JSON line. Exit 124 if none arrived."""
    mailbox = Mailbox(name)
    if start:
        _configured(name)
        _listener_or_exit(mailbox)
    message = _receive(mailbox, timeout, watch=start)
    if message is None:
        sys.exit(EXIT_TIMEOUT)
    print(message.to_json())


def handle_send(name: str, chat: str, text: Optional[str] = None, reply_to: Optional[str] = None) -> None:
    """Send text to a chat. Prints the new message id."""
    p = _configured(name)
    mailbox = Mailbox(name)
    body = _text_from(text)
    try:
        sent = p.send(chat, body, reply_to=reply_to)
    except Exception as exc:
        mailbox.record_sent(chat=chat, text=body, reply_to=reply_to, error=str(exc))
        errors.print(str(exc), style="red")
        sys.exit(1)
    mailbox.record_sent(chat=chat, text=body, reply_to=reply_to, provider_id=sent)
    print(sent)


def handle_reply(name: str, message_id: str, text: Optional[str] = None, again: bool = False) -> None:
    """Reply to a received message where it was asked. Prints the new id."""
    p = _configured(name)
    mailbox = Mailbox(name)
    original = mailbox.lookup(message_id)
    if original is None:
        errors.print(f"no message {message_id} in {mailbox.inbox}", style="red")
        sys.exit(1)
    if mailbox.already_replied(message_id) and not again:
        errors.print(f"already replied to {message_id}; pass --again to reply once more", style="yellow")
        sys.exit(1)
    body = _text_from(text)
    try:
        sent = p.send(original.chat, body, reply_to=message_id)
    except Exception as exc:
        mailbox.record_sent(chat=original.chat, text=body, reply_to=message_id, error=str(exc))
        errors.print(str(exc), style="red")
        sys.exit(1)
    mailbox.record_sent(chat=original.chat, text=body, reply_to=message_id, provider_id=sent)
    mailbox.done(message_id)
    print(sent)


def handle_check(name: str) -> None:
    """Credentials, connectivity, listener, unread. Exit 3 on any problem."""
    p = provider(name)
    problems = p.check()
    for problem in problems:
        console.print(f"[red]✗[/red] {problem}")
    if problems:
        sys.exit(EXIT_CONFIG)
    mailbox = Mailbox(name)
    pid = mailbox.listener_pid()
    listener = f"listener pid {pid}" if pid else "no listener running (receive starts one)"
    console.print(f"[green]✓[/green] {name} reachable · {listener} · {len(mailbox.unread())} unread · {mailbox.root}")


def handle_ls(name: str) -> None:
    """Unread messages, one per line: id, chat, sender, text."""
    mailbox = Mailbox(name)
    for path in mailbox.unread():
        record = json.loads(path.read_text(encoding="utf-8"))
        text = " ".join(str(record.get("text", "")).split())
        print(f"{record['id']}\t{record['chat']}\t{record.get('sender', '')}\t{text}")


def handle_log(name: str, follow: bool = False) -> None:
    """Every message ever received; -f keeps printing new ones."""
    mailbox = Mailbox(name)
    mailbox.inbox.touch()
    with mailbox.inbox.open("r", encoding="utf-8") as handle:
        while True:
            line = handle.readline()
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                continue
            if not follow:
                return
            time.sleep(0.5)


def handle_serve(name: str, command: List[str], once: bool = False) -> None:
    """For each message: run COMMAND with the message on stdin, send its
    stdout back as the reply. Empty stdout or a non-zero exit sends nothing."""
    p = _configured(name)
    mailbox = Mailbox(name)
    _listener_or_exit(mailbox)
    try:
        while True:
            message = _receive(mailbox, None, watch=True)
            env = dict(
                os.environ,
                CO_PROVIDER=name,
                CO_CHAT=message.chat,
                CO_THREAD=message.thread or "",
                CO_SENDER=message.sender,
                CO_MSG_ID=message.id,
                CO_CHAT_DIR=str(mailbox.root / "chats" / message.chat),
            )
            os.makedirs(env["CO_CHAT_DIR"], exist_ok=True)
            run = subprocess.run(command, input=message.to_json() + "\n", capture_output=True, text=True, env=env)
            if run.returncode != 0:
                mailbox.log(f"serve: command exited {run.returncode} for {message.id}: {run.stderr.strip()[:500]}")
            elif run.stdout.strip():
                reply = run.stdout.rstrip("\n")
                try:
                    sent = p.send(message.chat, reply, reply_to=message.id)
                    mailbox.record_sent(chat=message.chat, text=reply, reply_to=message.id, provider_id=sent)
                except Exception as exc:
                    mailbox.record_sent(chat=message.chat, text=reply, reply_to=message.id, error=str(exc))
                    mailbox.log(f"serve: reply to {message.id} failed: {exc}")
            mailbox.done(message.id)
            if once:
                return
    except KeyboardInterrupt:
        return
