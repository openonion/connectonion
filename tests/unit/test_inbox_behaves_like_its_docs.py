"""The inbox verbs do what docs/cli/*.md and the co-inbox SKILL say they do.

LLM-Note: Tests for connectonion.cli.commands.listen_commands, inbox/store.py,
inbox/whatsapp.py (the outbox), and the inbox groups in cli/main.py

A tester ran every verb of every provider with no credentials and with fake
ones, and wrote down each place the tool disagreed with its own docs. Each
test here is one of those, measured against the promise it broke:

- a WhatsApp send the CLI reported as failed went out nine minutes later
- Telegram group ids start with "-", and the docs' own examples exited 2
- a bad token made `receive` wait forever for a listener that had already quit
- Rich ate `[whatsapp]` out of the install hint
- queued messages could not be taken while the listener would not start
- consume's failures were in the log only, not on stderr as the SKILL says
- `done BOGUS` succeeded silently and blocked that id forever
- "not configured" was exit 1 on some verbs and 3 on others
- refusals that named no next command
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest
from typer.testing import CliRunner

from connectonion.cli.commands import listen_commands
from connectonion.inbox import Inbox, Message
from connectonion.inbox import store as store_module

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    # GitHub Actions makes Rich force colour; the words are what is asserted.
    return ANSI.sub("", text)


class FakeProvider:
    def __init__(self, problems=()):
        self.problems = list(problems)
        self.sent = []

    def missing(self):
        return self.problems

    def check(self):
        return self.problems

    def send(self, chat, text, *, reply_to=None, fresh=False, plain=False):
        self.sent.append((chat, text, reply_to))
        return f"om_sent{len(self.sent)}"


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    return Inbox("feishu")


@pytest.fixture
def fake(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(listen_commands, "provider", lambda name: provider)
    return provider


def deliver(box, i="om_1", chat="oc_a", text="hi"):
    box.deliver(Message(id=i, chat=chat, sender="on_x", text=text, at="2026-09-02T10:00:00Z"))


# ---- 1. a send reported as failed never goes out --------------------------------

@pytest.fixture
def whatsapp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.delenv("WHATSAPP_SESSION", raising=False)


@pytest.fixture
def neonize(monkeypatch):
    """Just enough of neonize for the listener's sender thread to address a chat."""
    package = ModuleType("neonize")
    utils = ModuleType("neonize.utils")
    jid = ModuleType("neonize.utils.jid")
    jid.build_jid = lambda user, server: SimpleNamespace(User=user, Server=server)
    monkeypatch.setitem(sys.modules, "neonize", package)
    monkeypatch.setitem(sys.modules, "neonize.utils", utils)
    monkeypatch.setitem(sys.modules, "neonize.utils.jid", jid)


def _drain(bot, inbox):
    """Run the listener's sender thread until it has dealt with every request.

    Stops on the spool being empty, not after a fixed sleep: on a loaded
    runner a sleep can end before the thread's first pass, and "nothing was
    sent" would then pass for the wrong reason."""
    stop = threading.Event()
    thread = threading.Thread(target=bot._drain_outbox, args=(inbox, stop), daemon=True)
    thread.start()
    spool = inbox.root / "outbox"
    deadline = time.monotonic() + 10
    while list(spool.glob("*.json")) + list(spool.glob("*.taken")) and time.monotonic() < deadline:
        time.sleep(0.01)
    stop.set()
    thread.join(timeout=5)


def test_a_request_left_by_a_sender_that_gave_up_is_never_sent_later(whatsapp_home, neonize):
    """The tester's case: `send` was killed (or gave up) with its request still
    in outbox/, and the next `co whatsapp listen`, minutes later, sent it. The
    person was told it failed; a message they may have re-sent since then went
    out twice. A request older than the sender's wait has no sender left."""
    from connectonion.inbox import whatsapp

    bot = whatsapp.WhatsApp()
    sent = []
    bot._client = SimpleNamespace(send_message=lambda to, text: (sent.append(text), SimpleNamespace(ID="X"))[1])
    inbox = Inbox("whatsapp")
    spool = inbox.root / "outbox"
    spool.mkdir(parents=True, exist_ok=True)
    old = int((time.time() - 9 * 60) * 1000)
    (spool / f"{old}-abandoned.json").write_text(json.dumps({"chat": "61400000000@s.whatsapp.net",
                                                            "text": "hello"}))

    _drain(bot, inbox)

    assert sent == [], "a request its sender stopped waiting for went out"
    assert list(spool.iterdir()) == []
    assert "abandoned" in inbox.logfile.read_text()


def test_a_request_the_listener_took_at_the_deadline_is_waited_for_not_reported_failed(
        whatsapp_home, monkeypatch):
    """The race: the listener picks the request up in the same instant the
    sender gives up. Reporting failure there is the bug — the message is on its
    way. Withdrawing is one atomic step, so exactly one side owns the request:
    if the sender cannot withdraw it, the listener has it, and the sender waits
    for the answer instead of saying it failed.

    Ordered with events, not sleeps: the first version slept its way to the
    deadline and failed on slower CI runners, where the second wait ran out
    before a sleep-timed answer arrived. Here the sender's first wait ends
    ("the deadline passed") only after the listener has claimed the request,
    and the answer is written only once the sender is in its second wait.
    """
    from connectonion.inbox import whatsapp

    spool = Inbox("whatsapp").root / "outbox"
    real_await = whatsapp._await
    claimed, second_wait = threading.Event(), threading.Event()
    waits = []

    def ordered_await(answer, seconds):
        waits.append(seconds)
        if len(waits) == 1:
            assert claimed.wait(10), "the listener never claimed the request"
            return None  # the sender's deadline passed with no answer yet
        second_wait.set()
        return real_await(answer, 10)

    monkeypatch.setattr(whatsapp, "_await", ordered_await)
    outcome = {}

    def ask():
        try:
            outcome["id"] = whatsapp.WhatsApp().send("61400000000@s.whatsapp.net", "on it", plain=True)
        except Exception as exc:
            outcome["error"] = str(exc)

    caller = threading.Thread(target=ask, daemon=True)
    caller.start()
    deadline = time.monotonic() + 10
    while not list(spool.glob("*.json")) and time.monotonic() < deadline:
        time.sleep(0.01)
    (request,) = list(spool.glob("*.json"))
    ticket = request.name[:-len(".json")]
    # The listener's claim, at the sender's deadline...
    os.rename(request, spool / f"{ticket}.taken")
    claimed.set()
    # ...and its answer, after the sender found it could not withdraw.
    assert second_wait.wait(10), "the sender reported instead of waiting for the listener"
    (spool / f"{ticket}.result").write_text(json.dumps({"id": "3EB0LATE"}))
    caller.join(timeout=10)

    assert outcome == {"id": "3EB0LATE"}
    assert len(waits) == 2


def test_a_withdrawn_request_is_gone_before_the_failure_is_reported(whatsapp_home, monkeypatch):
    from connectonion.inbox import whatsapp

    monkeypatch.setattr(whatsapp, "SEND_TIMEOUT_SECONDS", 0.2)

    with pytest.raises(RuntimeError, match="Next: co whatsapp listen"):
        whatsapp.WhatsApp().send("61400000000@s.whatsapp.net", "anyone there")

    assert list((Inbox("whatsapp").root / "outbox").iterdir()) == []


# ---- 2. Telegram ids that start with "-" ---------------------------------------

@pytest.fixture
def cli():
    from connectonion.cli.main import app

    return app


@pytest.mark.parametrize("argv,handler,expected", [
    (["telegram", "done", "-100123.55"], "handle_done", ("telegram", "-100123.55")),
    (["telegram", "reply", "-100123.55", "on it"], "handle_reply", ("telegram", "-100123.55", "on it")),
    (["telegram", "react", "-100123.55", "👍"], "handle_react", ("telegram", "-100123.55", "👍")),
    (["telegram", "delete", "-100123.55"], "handle_delete", ("telegram", "-100123.55")),
    (["discord", "send", "-5", "hi"], "handle_send", ("discord", "-5", "hi")),
])
def test_a_negative_chat_or_message_id_is_an_argument_not_an_option(cli, monkeypatch, argv, handler,
                                                                    expected):
    seen = {}
    monkeypatch.setattr(listen_commands, handler, lambda *args, **kwargs: seen.update(args=args, kwargs=kwargs))

    result = CliRunner().invoke(cli, argv)

    assert result.exit_code == 0, plain(result.output)
    assert seen["args"] == expected


def test_telegram_send_takes_a_group_id(cli, monkeypatch):
    from connectonion.cli.commands import telegram_commands

    seen = {}
    monkeypatch.setattr(telegram_commands, "handle_telegram_send", lambda chat, text: seen.update(chat=chat, text=text))

    result = CliRunner().invoke(cli, ["telegram", "send", "-100123", "hi"])

    assert result.exit_code == 0, plain(result.output)
    assert seen == {"chat": "-100123", "text": "hi"}


def test_real_options_still_work_beside_a_negative_id_and_typos_still_fail(cli, monkeypatch):
    seen = {}
    monkeypatch.setattr(listen_commands, "handle_reply", lambda *args, **kwargs: seen.update(args=args, kwargs=kwargs))

    ok = CliRunner().invoke(cli, ["telegram", "reply", "-100123.55", "--again", "--plain", "twice"])
    assert ok.exit_code == 0, plain(ok.output)
    assert seen["args"] == ("telegram", "-100123.55", "twice")
    assert seen["kwargs"] == {"again": True, "plain": True}

    seen.clear()
    typo = CliRunner().invoke(cli, ["telegram", "reply", "-100123.55", "--plian", "x"])
    assert typo.exit_code == 2, "a mistyped flag must not be sent as the text"
    assert seen == {}


# ---- 3. a listener that quits at once is reported, on every provider -----------

class _Child:
    """A `co <p> listen` that takes the lock, says it stopped, and exits 3 —
    what Telegram and Discord do with a revoked token."""

    def __init__(self, box, pid=7001, *, stops=True):
        self.box, self.pid, self.stops = box, pid, stops
        self.returncode = None
        self.polls = 0

    def poll(self):
        self.polls += 1
        if self.polls == 1:
            self.box.lock.write_text(f"{self.pid}\n")
            return None
        if self.polls == 2 and self.stops:
            self.box.connection.write_text(json.dumps({"state": "stopped", "pid": self.pid,
                                                       "reason": "Telegram refused: Unauthorized"}))
            return None
        if self.stops:
            self.returncode = 3
        return self.returncode

    def wait(self, timeout=None):
        return self.poll()


def _spawn(box, monkeypatch, child):
    held = {"now": True}

    def popen(argv, **kwargs):
        box.log("Telegram no longer accepts this token. Next: copy the current token from @BotFather")
        return child

    monkeypatch.setattr(store_module.subprocess, "Popen", popen)
    # The lock is held for as long as the child is running.
    monkeypatch.setattr(store_module, "_held", lambda path: child.returncode is None and held["now"])
    monkeypatch.setattr(store_module.time, "sleep", lambda s: None)


def test_a_listener_that_says_stopped_is_not_reported_as_started(box, monkeypatch):
    child = _Child(box)
    _spawn(box, monkeypatch, child)

    assert box.ensure_listener(settle=3) is None
    assert box.listener_exit_code == 3


def test_receive_with_a_revoked_token_says_the_listener_exited_instead_of_timing_out(box, fake, monkeypatch,
                                                                                    capsys):
    child = _Child(box)
    _spawn(box, monkeypatch, child)

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_receive("feishu", timeout=0)

    err = plain(capsys.readouterr().err)
    assert exit_.value.code == 3, "a token a person must replace is exit 3, as on listen"
    assert "listener exited at once" in err
    assert "@BotFather" in err
    assert "no message within the timeout" not in err


def test_receive_notices_a_listener_that_stops_while_it_waits(box, fake, monkeypatch, capsys):
    """Started, said nothing within the settle window, then died with exit 3:
    the wait must end, not continue for a listener that is gone."""
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: 7002)
    monkeypatch.setattr(Inbox, "exited_listener", lambda self: 3)
    box.log("Discord closed the Gateway with 4004. Next: copy the token again")

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_receive("feishu", timeout=None)

    assert exit_.value.code == 3
    assert "4004" in plain(capsys.readouterr().err)


def test_consume_does_not_wait_forever_on_a_listener_that_quit(box, fake, monkeypatch, capsys):
    child = _Child(box)
    _spawn(box, monkeypatch, child)

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_consume("feishu", [sys.executable, "-c", "pass"], once=True)

    assert exit_.value.code == 3
    assert "listener exited at once" in plain(capsys.readouterr().err)


# ---- 4. Rich does not eat the extra's name -------------------------------------

HINT = "The WhatsApp library is not installed. Run: pip install 'connectonion[whatsapp]'"


def test_the_install_hint_keeps_its_brackets_everywhere_it_is_printed(box, monkeypatch, capsys):
    provider = FakeProvider([HINT])
    provider.listen_requirements = lambda: [HINT]
    monkeypatch.setattr(listen_commands, "provider", lambda name: provider)

    for call in (lambda: listen_commands.handle_check("whatsapp"),
                 lambda: listen_commands.handle_send("whatsapp", "c", "x")):
        with pytest.raises(SystemExit):
            call()
    provider.problems = []
    with pytest.raises(SystemExit):
        listen_commands.handle_listen("whatsapp")  # also what reaches the log

    captured = capsys.readouterr()
    assert plain(captured.out + captured.err).count("connectonion[whatsapp]") == 3


# ---- 5. a queued message does not need a listener ------------------------------

def test_a_queued_message_is_taken_even_when_no_listener_can_start(box, fake, monkeypatch, capsys):
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: None)
    deliver(box, i="om_q")

    listen_commands.handle_receive("feishu", timeout=0)

    assert json.loads(capsys.readouterr().out)["id"] == "om_q"


def test_three_receives_share_three_queued_messages_without_a_listener(box, fake, monkeypatch):
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: None)
    for i in range(3):
        deliver(box, i=f"om_{i}")
    taken, failed = [], []

    def one():
        try:
            listen_commands.handle_receive("feishu", timeout=0)
            taken.append(1)
        except SystemExit as exc:
            failed.append(exc.code)

    threads = [threading.Thread(target=one) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert failed == [] and len(taken) == 3
    assert box.unread() == []


# ---- 6. consume reports its failures on stderr ---------------------------------

def test_consume_says_on_stderr_when_the_command_fails(box, fake, monkeypatch, capsys):
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: 1)
    deliver(box, i="om_f")

    listen_commands.handle_consume("feishu", [sys.executable, "-c", "import sys; sys.exit(7)"], once=True)

    err = plain(capsys.readouterr().err)
    assert "om_f" in err and "exited 7" in err


def test_consume_says_on_stderr_when_the_reply_is_refused(box, fake, monkeypatch, capsys):
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, **_: 1)

    def refuse(chat, text, *, reply_to=None, fresh=False, plain=False):
        raise RuntimeError("Feishu error 230002: bot is not in the chat")

    fake.send = refuse
    deliver(box, i="om_r")

    listen_commands.handle_consume("feishu", [sys.executable, "-c", "print('answer')"], once=True)

    err = plain(capsys.readouterr().err)
    assert "om_r" in err and "230002" in err


# ---- 7. done refuses an id it has never seen -----------------------------------

def test_done_refuses_an_id_that_was_never_received(box, fake, capsys):
    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_done("feishu", "BOGUSID")

    assert exit_.value.code == 1
    assert "Next: co feishu ls" in plain(capsys.readouterr().err)
    assert not box.completed.exists() or "BOGUSID" not in box.completed.read_text()


def test_done_still_forgets_a_received_message_taken_or_not(box, fake):
    deliver(box, i="om_a")
    deliver(box, i="om_b")
    box.receive(timeout=0)

    listen_commands.handle_done("feishu", "om_a")   # taken
    listen_commands.handle_done("feishu", "om_b")   # still queued, answered from `ls`

    assert box.unread() == [] and list(box.cur.iterdir()) == []


# ---- 8. not configured is exit 3 on every verb ---------------------------------

def test_telegram_send_without_a_token_is_exit_3(cli, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    result = CliRunner().invoke(cli, ["telegram", "send", "123", "hi"])

    assert result.exit_code == 3, plain(result.output)


def test_receive_exits_3_when_the_listener_needs_an_sdk(box, fake, monkeypatch, capsys):
    """listen and check already exit 3 for a missing SDK; receive, which
    starts that same listener, said 1."""

    class NoSdk:
        pid = 7003
        returncode = 3

        def poll(self):
            return 3

        def wait(self, timeout=None):
            return 3

    def popen(argv, **kwargs):
        box.log("The Feishu SDK is not installed. Run: pip install lark-oapi")
        return NoSdk()

    monkeypatch.setattr(store_module.subprocess, "Popen", popen)
    monkeypatch.setattr(store_module.time, "sleep", lambda s: None)

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_receive("feishu", timeout=0)

    assert exit_.value.code == 3
    assert "pip install lark-oapi" in plain(capsys.readouterr().err)


def test_whatsapp_send_without_the_extra_and_no_listener_is_exit_3_at_once(box, monkeypatch, capsys):
    provider = FakeProvider()
    provider.via_listener = True
    provider.listen_requirements = lambda: [HINT]
    monkeypatch.setattr(listen_commands, "provider", lambda name: provider)

    started = time.monotonic()
    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_send("whatsapp", "61400000000@s.whatsapp.net", "hi")

    assert exit_.value.code == 3
    assert time.monotonic() - started < 5, "no thirty-second wait for a listener that cannot exist"
    assert "connectonion[whatsapp]" in plain(capsys.readouterr().err)
    assert provider.sent == []


# ---- 9. every refusal names the next command -----------------------------------

def test_a_credential_refusal_names_check(box, fake, capsys):
    def refuse(chat, text, **kwargs):
        raise RuntimeError("Feishu refused the credentials: 10003 invalid param")

    fake.send = refuse

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_send("feishu", "oc_a", "hello")

    assert exit_.value.code == 1
    assert "Next: co feishu check" in plain(capsys.readouterr().err)


@pytest.mark.parametrize("words", ["Telegram refused: Unauthorized", "Discord refused: 401: Unauthorized"])
def test_an_unauthorized_send_names_check(box, fake, capsys, words):
    def refuse(chat, text, **kwargs):
        raise RuntimeError(words)

    fake.send = refuse

    with pytest.raises(SystemExit):
        listen_commands.handle_send("telegram", "123", "hello")

    assert "Next: co telegram check" in plain(capsys.readouterr().err)


def test_any_other_refusal_still_names_a_command(box, fake, capsys):
    def refuse(chat, text, **kwargs):
        raise RuntimeError("Telegram refused: Bad Request: chat not found")

    fake.send = refuse

    with pytest.raises(SystemExit):
        listen_commands.handle_send("telegram", "123", "hello")

    assert re.search(r"Next: co telegram \w+", plain(capsys.readouterr().err))


def test_reply_to_an_unknown_id_names_the_next_command(box, fake, capsys):
    with pytest.raises(SystemExit):
        listen_commands.handle_reply("feishu", "BOGUSID", "hi")

    assert "Next: co feishu log" in plain(capsys.readouterr().err)


def test_the_cli_telegram_send_refusal_names_check(monkeypatch, capsys):
    from connectonion.cli.commands import telegram_commands

    monkeypatch.setattr(telegram_commands, "send_telegram",
                        lambda chat, text: {"success": False, "error": "Telegram refused the message: Unauthorized"})

    with pytest.raises(SystemExit) as exit_:
        telegram_commands.handle_telegram_send("123", "hi")

    assert exit_.value.code == 1
    assert "Next: co telegram check" in plain(capsys.readouterr().out + capsys.readouterr().err)


def test_discords_length_limit_names_a_command():
    from connectonion.inbox.discord import Discord

    with pytest.raises(RuntimeError) as refused:
        Discord().send("123", "x" * 2001)

    assert re.search(r"Next: .*co discord", str(refused.value))


def test_a_usage_error_inside_a_provider_points_at_that_verbs_help(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "CO_TIPS": "on"}
    done = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "telegram", "reply"],
                          capture_output=True, text=True, env=env)

    assert done.returncode == 2
    assert "Next: co telegram reply --help" in done.stderr, done.stderr
    assert "co commands" not in done.stderr
