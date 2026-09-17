"""
Purpose: The verbs of an inbox provider — `co feishu listen | receive | send | reply | done | check | ls | log | consume`
LLM-Note:
  Dependencies: imports from [json, os, subprocess, sys, threading, time, typing, rich.console, inbox/] | imported by [cli/main.py via _inbox_group()] | tested by [tests/unit/test_listen_commands.py]
  Data flow: handle_listen → provider.run(inbox) until Ctrl-C | handle_receive → inbox.receive() → one JSON line on stdout | handle_send/handle_reply → stdin or argument → provider.send() → sent.jsonl → the new message id on stdout | handle_consume → Inbox.serve(handler) → subprocess(stdin=message) → reply(stdout)
  State/Effects: everything durable lives in the inbox directory | listen holds listen.lock and returns stale cur/ files every minute | receive and serve start a background listener when none runs
  Integration: one set of handlers for every provider name in inbox.PROVIDERS; main.py registers the same nine commands under each group | exit codes: 0 ok, 1 failure, 2 usage (Typer), 3 configuration missing, 124 receive timed out (as timeout(1))
  Errors: a missing credential prints the item and the next action and exits 3 | a provider refusal prints its own words and exits 1 | nothing is printed on the success path of listen (Rule of Silence); the log has it
"""

import re
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import List, Optional

from rich.console import Console

from ...inbox import ANSWERING, Inbox, provider, reactions_enabled
from .command_tips import print_tip

console = Console()
errors = Console(stderr=True)

EXIT_CONFIG = 3
EXIT_TIMEOUT = 124


# What the platform says when a bot token lacks a permission, e.g.
# "Lark error 230027: Lack of necessary permissions, ext=need scope: im:message.group_msg"
_NEEDS_SCOPE = re.compile(r"need scope:\s*([A-Za-z0-9_.:]+)")


def _missing_scope(text: str):
    """The one scope the platform asked for, or None for any other failure."""
    found = _NEEDS_SCOPE.search(text or "")
    return found.group(1) if found else None


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


def _listener_or_exit(inbox: Inbox) -> None:
    """Make sure a listener is running, or say why one could not start."""
    if inbox.ensure_listener() is None:
        errors.print("the listener exited at once:", style="red")
        # The reason is the child's last few lines; an agent that reads
        # stderr should not have to go and open the log to learn "pip
        # install lark-oapi".
        for line in inbox.last_log_lines():
            # Unwrapped: a pip command split across two lines cannot be copied.
            errors.print(f"  {line}", style="red", soft_wrap=True, markup=False, highlight=False)
        errors.print(f"full log: {inbox.logfile}", style="dim")
        sys.exit(1)


def handle_done(name: str, message_id: str) -> None:
    """Forget a taken message without replying, so it does not come back."""
    Inbox(name).done(message_id, by="done")


def handle_listen(name: str, raw: bool = False) -> None:
    """Hold the connection and write every message to the inbox."""
    p = _configured(name)
    inbox = Inbox(name)
    # The SDK is needed by listen alone; asking here, before the lock, means
    # the answer is exit 3 with the pip command on stderr, the same shape as
    # a missing credential, and not "the listener exited at once".
    needed = getattr(p, "listen_requirements", list)()
    if needed:
        for problem in needed:
            errors.print(problem, style="red")
        sys.exit(EXIT_CONFIG)
    if not inbox.hold_lock():
        errors.print(f"already listening (pid {inbox.listener_pid()}); one listener per directory", style="yellow")
        sys.exit(1)

    stop = threading.Event()

    def sweep():
        while not stop.wait(60):
            try:
                released = inbox.release_stale()
            except OSError as exc:  # the sweep must outlive one bad file
                inbox.log(f"stale sweep failed: {exc}")
                continue
            if released:
                inbox.log(f"returned {released} stale message(s) to new/")

    threading.Thread(target=sweep, daemon=True).start()
    errors.print(f"listening · {inbox.root}", style="dim")
    try:
        p.run(inbox, raw=raw)
    except KeyboardInterrupt:
        inbox.log("stopped by Ctrl-C")
    except Exception as exc:
        # The platform's own sentence ("app_id is invalid"), once, and exit 1.
        # A forty-line traceback through Typer told the operator nothing the
        # sentence does not, and `receive` reads this log to say why its
        # background listener died.
        inbox.log(f"listen failed: {exc}")
        errors.print(str(exc), style="red")
        errors.print(f"details: {inbox.logfile}", style="dim")
        sys.exit(1)
    finally:
        stop.set()
        inbox.log("listener stopped")
        inbox.release_lock()


# While waiting with no deadline, look at the listener this often so a
# listener that died an hour into the wait is restarted, not waited for.
WATCH_SECONDS = 60


def _receive(inbox: Inbox, timeout: Optional[float], watch: bool):
    if not watch or timeout is not None:
        return inbox.receive(timeout)
    while True:
        message = inbox.receive(WATCH_SECONDS)
        if message is not None:
            return message
        _listener_or_exit(inbox)


def handle_receive(name: str, timeout: Optional[float] = None, start: bool = True) -> None:
    """Print the next message as one JSON line. Exit 124 if none arrived."""
    inbox = Inbox(name)
    if start:
        _configured(name)
        _listener_or_exit(inbox)
    message = _receive(inbox, timeout, watch=start)
    if message is None:
        # 124 is the contract, borrowed from timeout(1). Saying so costs one
        # line on stderr and saves a caller from reading an empty stdout as
        # "something went wrong" — or worse, as "no messages, ever".
        errors.print(f"no message within the timeout (exit {EXIT_TIMEOUT}). "
                     f"Next: co {name} ls", style="dim")
        sys.exit(EXIT_TIMEOUT)
    print(message.to_json())


def handle_send(name: str, chat: str, text: Optional[str] = None, reply_to: Optional[str] = None) -> None:
    """Send text to a chat. Prints the new message id."""
    p = _configured(name)
    inbox = Inbox(name)
    body = _text_from(text)
    try:
        sent = p.send(chat, body, reply_to=reply_to)
    except Exception as exc:
        inbox.record_sent(chat=chat, text=body, reply_to=reply_to, error=str(exc), by="send")
        errors.print(str(exc), style="red")
        sys.exit(1)
    inbox.record_sent(chat=chat, text=body, reply_to=reply_to, provider_id=sent, by="send")
    print(sent)


def _mark_answering(p, inbox, message) -> None:
    """Change the queued message's mark from "seen" to "being answered".

    The last thing before the answer goes out, so it reports work that is
    actually starting rather than work that was planned. The listener put the
    first mark on as the message was queued; platforms replace a sender's
    previous reaction rather than stacking them, so this reads as one status
    changing.

    Never fatal. A mark that did not go out costs a receipt; a reply that did
    not go out because a receipt failed costs the answer.
    """
    react = getattr(p, "react", None)
    if react is None or not reactions_enabled() or not getattr(message, "mentioned", False):
        return
    try:
        sent = react(message.chat, message.id, ANSWERING, sender=message.sender)
    except Exception as exc:
        inbox.log(f"{ANSWERING} on {message.id} not sent: {exc}")
        return
    inbox.log(f"{ANSWERING} on {message.id} sent as {sent or 'no id'}")


def handle_reply(name: str, message_id: str, text: Optional[str] = None, again: bool = False) -> None:
    """Reply to a received message where it was asked. Prints the new id."""
    p = _configured(name)
    inbox = Inbox(name)
    original = inbox.lookup(message_id)
    if original is None:
        errors.print(f"no message {message_id} in {inbox.received}", style="red")
        sys.exit(1)
    if inbox.already_replied(message_id) and not again:
        errors.print(f"already replied to {message_id}; pass --again to reply once more", style="yellow")
        sys.exit(1)
    body = _text_from(text)
    _mark_answering(p, inbox, original)
    try:
        sent = p.send(original.chat, body, reply_to=message_id, fresh=again)
    except Exception as exc:
        inbox.record_sent(chat=original.chat, text=body, reply_to=message_id,
                          error=str(exc), by="reply")
        errors.print(str(exc), style="red")
        sys.exit(1)
    inbox.record_sent(chat=original.chat, text=body, reply_to=message_id, provider_id=sent,
                      by="reply")
    inbox.done(message_id, by="reply")
    print(sent)


def handle_check(name: str) -> None:
    """Credentials, connectivity, listener, unread. Exit 3 on any problem."""
    p = provider(name)
    problems = p.check()
    for problem in problems:
        console.print(f"[red]✗[/red] {problem}")
    if problems:
        sys.exit(EXIT_CONFIG)
    inbox = Inbox(name)
    recovery_error = inbox.root / "recovery-error.txt"
    if recovery_error.exists():
        # The reason, not a category. "Check bot history permissions and
        # network" named no command and covered two unrelated causes, so a
        # reader could not tell a missing scope from a dropped connection
        # without opening the file themselves. The file's first line is the
        # platform's own sentence — print it.
        reason = recovery_error.read_text(encoding="utf-8").strip()
        first = reason.splitlines()[0] if reason else "no reason recorded"
        errors.print(f"History recovery is incomplete: {first}", style="red")

        # A missing scope is one click away, so say which click. The platform
        # names the scope it wanted in its own error; turning that into the
        # scan-to-enable link is the difference between "your bot lacks a
        # permission" and a thing the reader can do. Anything else — a dropped
        # connection, a revoked app — has no link, and gets the log instead.
        missing = _missing_scope(reason)
        if missing:
            from .feishu_auth import scan_to_enable_url

            app_id = p.app_id
            errors.print("The bot is missing a permission. This is a sensitive scope: it lets "
                         f"the app read every message in the groups it is in.", style="red")
            print(f"Open this, approve it, and the listener picks it up on its next retry:")
            print(scan_to_enable_url(name, app_id, tenant=[missing]))
            print_tip(f"Next: co {name} check")
        else:
            errors.print(f"The listener retains its checkpoint and retries. Details: {recovery_error}",
                         style="red")
            print_tip(f"Next: co {name} log")
        sys.exit(1)
    pid = inbox.listener_pid()
    listener = f"listener pid {pid}" if pid else "no listener running (receive starts one)"
    console.print(f"[green]✓[/green] {name} reachable · {listener} · {len(inbox.unread())} unread · {inbox.root}")


def handle_ls(name: str) -> None:
    """Unread messages, one per line: id, chat, sender, text."""
    inbox = Inbox(name)
    for message in inbox.list_messages():
        record = message.to_dict()
        text = " ".join(str(record.get("text", "")).split())
        print(f"{record['id']}\t{record['chat']}\t{record.get('sender', '')}\t{text}")


def _handled_lines(inbox: Inbox) -> List[str]:
    """Who handled the last few messages, for `log`. Descriptive only: a
    record from before `by` existed shows `-`, and a malformed value never
    crashes the display."""
    lines = []
    for record in inbox.recent_records(inbox.sent, 5):
        lines.append(f"sent to {record.get('chat') or '-'}"
                     f" reply_to {record.get('reply_to') or '-'}"
                     f" by {record.get('by') or '-'}")
    for record in inbox.recent_records(inbox.completed, 5):
        lines.append(f"done {record.get('id') or '-'} by {record.get('by') or '-'}")
    return lines


def handle_log(name: str, follow: bool = False) -> None:
    """Every message ever received; -f keeps printing new ones."""
    inbox = Inbox(name)
    for line in _handled_lines(inbox):
        print(line)
    inbox.received.touch()
    with inbox.received.open("r", encoding="utf-8") as handle:
        while True:
            line = handle.readline()
            if line:
                sys.stdout.write(line)
                sys.stdout.flush()
                continue
            if not follow:
                return
            time.sleep(0.5)


def handle_consume(name: str, command: List[str], once: bool = False, workers: int = 1) -> None:
    """For each message: run COMMAND with the message on stdin, send its
    stdout back as the reply. Empty stdout or a non-zero exit sends nothing."""
    p = _configured(name)
    inbox = Inbox(name)
    if not command or shutil.which(command[0]) is None:
        # Found out now, before a message is taken. A typo used to claim the
        # message into cur/ and then traceback, one stranded message per
        # restart.
        errors.print(f"cannot run {command[0] if command else '(no command)'}: not found or not executable", style="red")
        sys.exit(2)
    _listener_or_exit(inbox)
    consumer = f"consume:{os.path.basename(command[0])}"

    def answer(message) -> None:
        env = dict(
            os.environ,
            CO_PROVIDER=name,
            CO_CHAT=message.chat,
            CO_THREAD=message.thread or "",
            CO_SENDER=message.sender,
            CO_MSG_ID=message.id,
            CO_CHAT_DIR=str(inbox.root / "chats" / message.chat),
        )
        os.makedirs(env["CO_CHAT_DIR"], exist_ok=True)
        # Before the command, not before the send. Here the command *is* the
        # answering — a model can think for minutes — and that interval is the
        # one the chat cannot currently distinguish from the bot being down.
        # Marking after it would light up for the millisecond before the reply
        # lands, which is the same as not marking at all.
        _mark_answering(p, inbox, message)
        run = subprocess.run(command, input=message.to_json() + "\n",
                             capture_output=True, text=True, env=env)
        # Returning finishes the message; raising leaves it in cur/ for the
        # sweep to offer again in an hour. So a command that failed, or a
        # reply the platform refused, raises: completing it here turned every
        # transient failure into an unanswered question. A command that exited
        # 0 with nothing to say returns, because silence is an answer.
        if run.returncode != 0:
            raise RuntimeError(
                f"command exited {run.returncode}: {run.stderr.strip()[:500]}")
        if not run.stdout.strip():
            inbox.log(f"consume: nothing to say for {message.id}")
            return
        reply = run.stdout.rstrip("\n")
        try:
            sent = p.send(message.chat, reply, reply_to=message.id)
        except Exception as exc:
            inbox.record_sent(chat=message.chat, text=reply, reply_to=message.id,
                              error=str(exc), by=consumer)
            raise RuntimeError(f"reply failed: {exc}") from exc
        inbox.record_sent(chat=message.chat, text=reply, reply_to=message.id,
                          provider_id=sent, by=consumer)

    try:
        # workers=1: a shell command written for this has always run one at a
        # time, and some of them are not safe to run twice at once. The lanes
        # still give it ordering, lease renewal and the give-up rule; anyone
        # who wants the parallelism asks for it with --workers.
        inbox.serve(answer, workers=workers, once=once, by=consumer)
    except KeyboardInterrupt:
        return
