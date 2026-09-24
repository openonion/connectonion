"""
Purpose: The verbs of an inbox provider — `co feishu listen | receive | send | reply | done | check | ls | log | consume`
LLM-Note:
  Dependencies: imports from [json, os, subprocess, sys, threading, time, typing, rich.console, inbox/] | imported by [cli/main.py via _inbox_group()] | tested by [tests/unit/test_listen_commands.py]
  Data flow: handle_listen → provider.run(inbox) until Ctrl-C | handle_receive → inbox.receive() → one JSON line on stdout | handle_send/handle_reply → stdin or argument → provider.send() → sent.jsonl → the new message id on stdout | handle_consume → Inbox.serve(handler) → subprocess(stdin=message) → reply(stdout)
  State/Effects: everything durable lives in the inbox directory | listen holds listen.lock and returns stale cur/ files every minute | receive and serve start a background listener when none runs
  Integration: one set of handlers for every provider name in inbox.PROVIDERS; main.py registers the same nine commands under each group | exit codes: 0 ok, 1 failure, 2 usage (Typer), 3 configuration missing, 124 receive timed out (as timeout(1))
  Errors: a missing credential prints the item and the next action and exits 3 | a provider refusal prints its own words and exits 1 | nothing is printed on the success path of listen (Rule of Silence); the log has it
"""

import json
import re
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import List, Optional

from rich.console import Console

from ...inbox import ANSWERING, Inbox, ListenerStopped, provider, reactions_enabled
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
    """The argument if given, else stdin, like mail(1). Never nothing.

    An empty message is not a message, and WhatsApp's own app disables the
    send button for one. Until #1602 this path read stdin, got EOF and
    delivered a blank bubble: an id was printed, the exit code was 0, and
    `sent.jsonl` got a row saying it worked — so every habit that catches a bad
    send reported success, because it *was* a successful send of nothing. Two
    of them reached real groups that way, one a client's, where the only
    remaining option is to delete a message a customer has already seen.

    Refusing costs a caller one retry and removes the class.
    """
    text = argument
    if text is None:
        if sys.stdin.isatty():
            errors.print("nothing to send: pass the text as an argument or on stdin", style="red")
            sys.exit(2)
        text = sys.stdin.read()
    if not text.strip():
        # Exit 2, the same usage error as a terminal with nothing on it: from
        # the caller's side these are one mistake, not two.
        errors.print("nothing to send: the text was empty. Pass it as an argument or on stdin",
                     style="red")
        sys.exit(2)
    return text.rstrip("\n")


def _wire(p, text: str, plain: bool) -> str:
    """The characters the platform will actually receive.

    Rendered here, not inside `send`, so the same string can go into
    `sent.jsonl`. Recording the Markdown a caller typed while sending its
    translation means `log` shows a message nobody in the chat ever saw — the
    record and the thing it records disagreeing, which is the whole shape this
    release has been chasing.

    Rendering is not idempotent, so every caller of this sends with
    `plain=True`: `*bold*` is Markdown italic and a second pass moves it to
    `_bold_`.
    """
    render = getattr(p, "render", None)
    if plain or render is None:
        return text
    return render(text)


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
    except ListenerStopped as exc:
        # Exit 3, the same code as a missing credential, because it is the same
        # kind of problem: a person has to do something before any amount of
        # restarting helps. A supervisor that retries on 1 and stops on 3 then
        # does the right thing without being told which failure this was.
        errors.print(str(exc), style="red")
        errors.print(f"details: {inbox.logfile}", style="dim")
        sys.exit(EXIT_CONFIG)
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


def _with_context(inbox: Inbox, message, count: int) -> str:
    """The message as JSON, with the conversation around it when asked for.

    Opt-in and zero by default. Context is real cost — tokens for a model, and
    in a busy group it is also other people's messages leaving the machine — so
    it is asked for rather than assumed, and the line is byte-identical to
    before when it is not.
    """
    if count <= 0:
        return message.to_json()
    record = message.to_dict()
    record["context"] = inbox.context(message.chat, count, before=message.id)
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def handle_receive(name: str, timeout: Optional[float] = None, start: bool = True,
                   context: int = 0) -> None:
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
    print(_with_context(inbox, message, context))


def handle_send(name: str, chat: str, text: Optional[str] = None, reply_to: Optional[str] = None,
                plain: bool = False) -> None:
    """Send text to a chat. Prints the new message id."""
    p = _configured(name)
    inbox = Inbox(name)
    body = _wire(p, _text_from(text), plain)
    try:
        sent = p.send(chat, body, reply_to=reply_to, plain=True)
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


def handle_reply(name: str, message_id: str, text: Optional[str] = None, again: bool = False,
                 plain: bool = False) -> None:
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
    body = _wire(p, _text_from(text), plain)
    _mark_answering(p, inbox, original)
    try:
        sent = p.send(original.chat, body, reply_to=message_id, fresh=again, plain=True)
    except Exception as exc:
        inbox.record_sent(chat=original.chat, text=body, reply_to=message_id,
                          error=str(exc), by="reply")
        errors.print(str(exc), style="red")
        sys.exit(1)
    inbox.record_sent(chat=original.chat, text=body, reply_to=message_id, provider_id=sent,
                      by="reply")
    inbox.done(message_id, by="reply")
    print(sent)


def _unsupported(p, name: str, verb: str,
                 endpoint: str = "PUT and DELETE on /im/v1/messages/<id>") -> None:
    """Say which provider cannot do this and what it would take, not "error".

    A verb that exists on `co whatsapp` and not on `co lark` has to say so in
    the terms the reader is in — otherwise the obvious reading of a bare
    failure is that the message id was wrong. A provider names its own
    endpoint in `unwired`; Feishu and Lark share the default, because a
    Telegram user told to look at /im/v1/messages is sent to the wrong docs.
    """
    where = (getattr(p, "unwired", None) or {}).get(verb) or \
        f"Feishu and Lark have the endpoint for it ({endpoint})"
    errors.print(
        f"co {name} {verb} is not implemented. WhatsApp is the only provider with it so far; "
        f"{where} and nobody has wired it up. Next: co {name} send",
        style="red")
    sys.exit(1)


def handle_edit(name: str, message_id: str, text: Optional[str] = None,
                plain: bool = False) -> None:
    """Replace the text of a message we sent. Prints the edit's id."""
    p = _configured(name)
    inbox = Inbox(name)
    if getattr(p, "edit", None) is None:
        _unsupported(p, name, "edit")
    original = inbox.lookup_sent(message_id)
    if original is None:
        # Deliberately not "no such message": we can only edit our own, so the
        # thing that is missing is a record of US sending it. Someone trying to
        # edit a message they received should be told that, not told to check
        # the id they read correctly off `log`.
        errors.print(f"{name} has no record of sending {message_id}. Only messages this account "
                     f"sent can be edited. Next: co {name} log", style="red")
        sys.exit(1)
    body = _wire(p, _text_from(text), plain)
    try:
        sent = p.edit(original["chat"], message_id, body, plain=True)
    except Exception as exc:
        errors.print(str(exc), style="red")
        sys.exit(1)
    inbox.record_sent(chat=original["chat"], text=body, reply_to=original.get("reply_to"),
                      provider_id=sent, by=f"edit of {message_id}")
    print(sent)


def handle_delete(name: str, message_id: str) -> None:
    """Delete a message for everyone. Prints the deletion's id."""
    p = _configured(name)
    inbox = Inbox(name)
    if getattr(p, "revoke", None) is None:
        _unsupported(p, name, "delete")
    ours = inbox.lookup_sent(message_id)
    if ours is not None:
        chat, sender = ours["chat"], ""
    else:
        # Not ours: deleting somebody else's message is a group-admin action,
        # and WhatsApp needs to be told whose message it was.
        received = inbox.lookup(message_id)
        if received is None:
            errors.print(f"no message {message_id} in {inbox.received} or {inbox.sent}. "
                         f"Next: co {name} log", style="red")
            sys.exit(1)
        chat, sender = received.chat, received.sender
    try:
        sent = p.revoke(chat, message_id, sender=sender)
    except Exception as exc:
        errors.print(str(exc), style="red")
        sys.exit(1)
    inbox.log(f"deleted {message_id} in {chat} as {sent or 'no id'}")
    print(sent)


def handle_group(name: str, phones: list, *, subject: str = "", chat: str = "") -> None:
    """Create a group (subject) or add to one (chat). One line per person.

    Asked to start a room for a new client, the answer used to be "a human has
    to create it on a phone, then add me" (#1617). The per-person lines are the
    point: WhatsApp calls the group a success while quietly leaving out anyone
    whose privacy settings forbid being added.
    """
    p = _configured(name)
    try:
        result = p.create_group(subject, phones) if subject else p.add_to_group(chat, phones)
    except Exception as exc:
        errors.print(f"{exc}. A listener started before this version cannot do "
                     f"this; restart it. Next: co {name} listen", style="red")
        sys.exit(1)
    print(result["chat"])
    missing = 0
    for person in result["participants"]:
        added = person["outcome"] in ("added", "already in the group")
        missing += not added
        print(f"  {'✓' if added else '✗'} +{person['phone']}  {person['outcome']}")
    if result.get("invite_link"):
        print(f"  invite_link: {result['invite_link']}")
    what = f"created group {subject!r}" if subject else "added to group"
    Inbox(name).log(f"{what} {result['chat']}: {len(phones) - missing}/{len(phones)} in")
    print_tip(f"Next: co {name} send {result['chat']} \"<text>\"")
    if missing:
        sys.exit(1)


def handle_react(name: str, message_id: str, emoji: str) -> None:
    """React to any message — ours, or somebody else's. "" removes our reaction.

    The automatic SEEN/ANSWERING receipts only land on messages the bot will
    answer. In a group, people acknowledge each other with a 👍; the bot could
    only stay silent or send a whole message, which is louder than the moment
    deserves (#1633). Prints the reaction's id so a script can check it landed.
    """
    p = _configured(name)
    inbox = Inbox(name)
    if getattr(p, "react", None) is None:
        _unsupported(p, name, "react", "POST /im/v1/messages/<id>/reactions")
    ours = inbox.lookup_sent(message_id)
    if ours is not None:
        chat, sender, mine = ours["chat"], "", True
    else:
        received = inbox.lookup(message_id)
        if received is None:
            errors.print(f"no message {message_id} in {inbox.received} or {inbox.sent}. "
                         f"Next: co {name} log", style="red")
            sys.exit(1)
        chat, sender, mine = received.chat, received.sender, False
    try:
        sent = p.react(chat, message_id, emoji, sender=sender, mine=mine)
    except Exception as exc:
        errors.print(str(exc), style="red")
        sys.exit(1)
    what = f"reacted {emoji}" if emoji else "removed our reaction"
    inbox.log(f"{what} on {message_id} in {chat} as {sent or 'no id'}")
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
    console.print(f"[green]✓[/green] {name} configured · {listener} · "
                  f"{len(inbox.unread())} unread · {inbox.root}")
    _report_connection(name, inbox, pid)


def _report_connection(name: str, inbox: Inbox, pid) -> None:
    """What the listener says about its socket, which is the only thing that knows.

    This line used to read "reachable", inferred from a package being
    importable, a row in SQLite and a pid holding a lock — none of which is the
    network. A connection that had quietly stopped still got a green tick, which
    is the failure this whole release has been about, sitting inside the command
    people run to check for it.

    The listener's own record is only worth reading while that listener is
    alive: a `connected` left behind by a process that has since exited says
    what was true once, and reading it as current is how a stale file becomes a
    confident wrong answer.
    """
    if not pid:
        errors.print("not connected: no listener is running, so nothing is arriving.",
                     style="yellow")
        print_tip(f"Next: co {name} listen")
        sys.exit(EXIT_CONFIG)
    state = inbox.connection_state()
    if not state or state.get("pid") != pid:
        # An older listener's record, or one from before this was written. Say
        # that rather than guessing in either direction — and do not exit 3:
        # "I cannot tell" is not "it is broken", and a caller that stops on it
        # stops on a listener that may be perfectly healthy.
        errors.print(f"listener {pid} is running; it has not said whether its socket is up.",
                     style="dim")
        print_tip(f"Next: co {name} log")
        return
    if state.get("state") == "connected":
        account = state.get("account") or "unknown"
        console.print(f"[green]✓[/green] connected as {account} since {state.get('at', '?')}")
        print_tip(f"Next: co {name} receive")
        return
    errors.print(f"listener {pid} is running but {state.get('state', 'not connected')} "
                 f"since {state.get('at', '?')}"
                 + (f": {state['reason']}" if state.get("reason") else ""), style="yellow")
    print_tip(f"Next: co {name} log")
    sys.exit(EXIT_CONFIG)


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


def _since_to_iso(value: Optional[str]) -> Optional[str]:
    """`30d`, `2w`, or a date, as the timestamp the records are written with.

    The mail CLIs already parse exactly this spelling, and a second grammar for
    the same idea is how `7d` comes to mean two different things in one tool.
    """
    if not value:
        return None
    from .mail_window import parse_since

    try:
        return parse_since(value).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        errors.print(str(error), style="red")
        sys.exit(2)


def handle_chats(name: str) -> None:
    """The conversations this inbox has seen, busiest last."""
    inbox = Inbox(name)
    rows = inbox.chats()
    if not rows:
        errors.print("no conversations yet — nothing has arrived in this inbox.", style="dim")
        print_tip(f"Next: co {name} listen")
        return
    for row in rows:
        who = row["last_sender_name"] or row["last_sender"]
        text = " ".join(str(row["last_text"]).split())[:60]
        # Plain print, not Rich: Rich expands \t into spaces, and `cut -f1` has
        # to give the chat id — the one thing every other verb needs and nothing
        # else prints. The same reason `ls` writes its rows this way.
        print(f"{row['chat']}\t{'group' if row['group'] else 'direct'}\t"
              f"{row['messages']}\t{row['mentioned']}\t{row['last_at']}\t{who}\t{text}")
    print_tip(f"Next: co {name} log --chat <id>")


def handle_log(name: str, follow: bool = False, chat: Optional[str] = None,
               sender: Optional[str] = None, since: Optional[str] = None,
               last: Optional[int] = None) -> None:
    """Every message ever received; -f keeps printing new ones."""
    inbox = Inbox(name)
    if chat or sender or since or last is not None:
        # A filtered read is a query, not a tail: it answers from the record and
        # stops, so `--follow` with a filter would mean two different things at
        # once.
        window = _since_to_iso(since)
        for record in inbox.history(chat=chat, sender=sender, since=window, last=last):
            print(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
        return
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


def handle_consume(name: str, command: List[str], once: bool = False, workers: int = 1,
                   context: int = 0) -> None:
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
        run = subprocess.run(command, input=_with_context(inbox, message, context) + "\n",
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
            sent = p.send(message.chat, _wire(p, reply, False), reply_to=message.id, plain=True)
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
