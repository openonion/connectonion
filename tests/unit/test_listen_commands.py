"""Unit tests for the inbox verbs behind `co feishu ...`.

LLM-Note: Tests for connectonion.cli.commands.listen_commands

What it tests:
- receive prints one JSON line and exits 124 with nothing to print
- send and reply take text from an argument or stdin, record the outbox, and print the new id
- reply finds the chat from the log and refuses to answer twice
- serve runs a command per message with the message on stdin and sends its stdout back
- check exits 3 with the problems and ls lists the queue

Components under test:
- Module: connectonion/cli/commands/listen_commands.py
"""

import io
import json
import sys

import pytest

from connectonion.cli.commands import listen_commands
from connectonion.inbox import Inbox, Message


class FakeProvider:
    def __init__(self, problems=()):
        self.problems = list(problems)
        self.sent = []

    def missing(self):
        return self.problems

    def check(self):
        return self.problems

    def send(self, chat, text, *, reply_to=None, fresh=False):
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


def deliver(box, i="om_1", chat="oc_a", text="hi", thread=None):
    box.deliver(Message(id=i, chat=chat, sender="on_x", text=text, at="2026-09-02T10:00:00Z", thread=thread))


def test_receive_prints_one_json_line_and_takes_the_message(box, fake, capsys):
    deliver(box)

    listen_commands.handle_receive("feishu", timeout=0, start=False)

    out = capsys.readouterr().out
    assert json.loads(out) == {"id": "om_1", "chat": "oc_a", "thread": None, "sender": "on_x",
                               "text": "hi", "mentioned": True, "at": "2026-09-02T10:00:00Z"}
    assert box.unread() == []


def test_receive_exits_124_when_nothing_arrives(box, fake):
    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_receive("feishu", timeout=0, start=False)
    assert exit_.value.code == 124


def test_receive_starts_a_listener_unless_told_not_to(box, fake, monkeypatch):
    started = []
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: started.append(self.provider) or 1)
    deliver(box)

    listen_commands.handle_receive("feishu", timeout=0)

    assert started == ["feishu"]


def test_send_takes_text_from_stdin_records_it_and_prints_the_id(box, fake, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("all green\n"))

    listen_commands.handle_send("feishu", "oc_a")

    assert fake.sent == [("oc_a", "all green", None)]
    assert capsys.readouterr().out.strip() == "om_sent1"
    record = json.loads(box.sent.read_text())
    assert record["ok"] is True and record["id"] == "om_sent1" and record["chat"] == "oc_a"


def test_send_with_nothing_on_a_terminal_is_a_usage_error(box, fake, monkeypatch):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty())
    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_send("feishu", "oc_a")
    assert exit_.value.code == 2
    assert fake.sent == []


def test_a_refused_send_is_recorded_and_exits_1(box, fake, monkeypatch, capsys):
    def refuse(chat, text, *, reply_to=None):
        raise RuntimeError("Feishu error 230002: Bot has NOT been added to the chat")

    monkeypatch.setattr(fake, "send", refuse)

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_send("feishu", "oc_a", "hi")

    assert exit_.value.code == 1
    assert "230002" in capsys.readouterr().err
    assert json.loads(box.sent.read_text())["ok"] is False


def test_reply_finds_the_chat_from_the_log_and_forgets_the_taken_message(box, fake, capsys):
    deliver(box, i="om_q", chat="oc_ops", thread="omt_1")
    listen_commands.handle_receive("feishu", timeout=0, start=False)
    capsys.readouterr()

    listen_commands.handle_reply("feishu", "om_q", "fixed")

    assert fake.sent == [("oc_ops", "fixed", "om_q")]
    assert capsys.readouterr().out.strip() == "om_sent1"
    assert list(box.cur.iterdir()) == []
    assert box.already_replied("om_q")


def test_reply_refuses_a_second_answer_unless_asked_again(box, fake, capsys):
    deliver(box, i="om_q")
    listen_commands.handle_reply("feishu", "om_q", "first")

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_reply("feishu", "om_q", "second")
    assert exit_.value.code == 1
    assert "already replied" in capsys.readouterr().err

    listen_commands.handle_reply("feishu", "om_q", "second", again=True)
    assert [s[1] for s in fake.sent] == ["first", "second"]


def test_reply_to_an_unknown_id_exits_1(box, fake, capsys):
    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_reply("feishu", "om_nope", "hello")
    assert exit_.value.code == 1
    assert "no message om_nope" in capsys.readouterr().err
    assert fake.sent == []


def test_serve_pipes_the_message_through_a_command_and_replies_with_its_stdout(box, fake, monkeypatch):
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)
    deliver(box, i="om_s", chat="oc_s", text="what is 2+2")
    command = [sys.executable, "-c",
               "import json,os,sys; m=json.load(sys.stdin); "
               "print('you asked', m['text'], 'in', os.environ['CO_CHAT'], 'msg', os.environ['CO_MSG_ID'])"]

    listen_commands.handle_serve("feishu", command, once=True)

    assert fake.sent == [("oc_s", "you asked what is 2+2 in oc_s msg om_s", "om_s")]
    assert list(box.cur.iterdir()) == []
    assert (box.root / "chats" / "oc_s").is_dir()


def _taken(box):
    return sorted(p.name.split("-", 1)[1] for p in box.cur.iterdir())


def test_serve_sends_nothing_for_a_failing_or_silent_command(box, fake, monkeypatch):
    # A command that exits non-zero did not answer: the message stays taken
    # and comes back in an hour, as the docs promise. Empty stdout with exit
    # 0 is the command choosing silence: done. Both are one log line.
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)
    deliver(box, i="om_f")
    listen_commands.handle_serve("feishu", [sys.executable, "-c", "import sys; sys.exit(3)"], once=True)
    deliver(box, i="om_g")
    listen_commands.handle_serve("feishu", [sys.executable, "-c", "pass"], once=True)

    assert fake.sent == []
    log = box.logfile.read_text()
    assert "exited 3 for om_f" in log
    assert "nothing to say for om_g" in log
    assert _taken(box) == ["om_f"], "the failed one waits for the sweep; the silent one is done"


def test_serve_keeps_a_message_whose_reply_the_platform_refused(box, fake, monkeypatch):
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)

    def refuse(chat, text, *, reply_to=None):
        raise RuntimeError("Feishu error 99991400: too many requests")

    fake.send = refuse
    deliver(box, i="om_r")

    listen_commands.handle_serve("feishu", [sys.executable, "-c", "print('answer')"], once=True)

    assert _taken(box) == ["om_r"], "not consumed by a refusal it can retry later"
    assert "reply to om_r failed" in box.logfile.read_text()


def test_serve_refuses_a_command_it_cannot_run_before_taking_a_message(box, fake, monkeypatch, capsys):
    # A typo in the command used to claim the message into cur/ and then
    # traceback, stranding one message per restart.
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)
    deliver(box, i="om_n")

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_serve("feishu", ["./no-such-answer.sh"], once=True)

    assert exit_.value.code == 2
    assert "no-such-answer.sh" in capsys.readouterr().err
    assert len(box.unread()) == 1, "the message was not claimed"


def test_listen_exits_3_before_taking_the_lock_when_the_sdk_is_missing(box, fake, capsys):
    fake.listen_requirements = lambda: ["The Feishu SDK is not installed. Run: pip install lark-oapi"]

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_listen("feishu")

    assert exit_.value.code == 3
    assert "pip install lark-oapi" in capsys.readouterr().err
    assert box.listener_pid() is None


def test_a_listener_that_died_is_reported_with_its_reason_inline(box, fake, monkeypatch, capsys):
    # "see the log" sent an agent to a file it may not read; the reason is
    # three lines, so print them.
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: None)
    box.log("The Feishu SDK is not installed. Run: pip install lark-oapi")
    box.log("listener exited at once with 3; see the lines above")

    with pytest.raises(SystemExit):
        listen_commands.handle_receive("feishu", timeout=0)

    assert "pip install lark-oapi" in capsys.readouterr().err


def test_check_exits_3_and_names_each_problem(box, monkeypatch, capsys):
    monkeypatch.setattr(listen_commands, "provider",
                        lambda name: FakeProvider(["FEISHU_APP_ID is not set. Create a self-built application."]))

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_check("feishu")

    assert exit_.value.code == 3
    assert "FEISHU_APP_ID is not set" in capsys.readouterr().out


def test_check_reports_listener_and_unread_when_configured(box, fake, capsys):
    deliver(box)

    listen_commands.handle_check("feishu")

    out = capsys.readouterr().out
    assert "feishu reachable" in out and "no listener running" in out and "1 unread" in out


def test_ls_lists_the_queue_one_line_each(box, fake, capsys):
    deliver(box, i="om_1", text="first\nline")
    deliver(box, i="om_2", text="second")

    listen_commands.handle_ls("feishu")

    assert capsys.readouterr().out == "om_1\toc_a\ton_x\tfirst line\nom_2\toc_a\ton_x\tsecond\n"


def test_every_verb_that_talks_to_the_platform_exits_3_when_unconfigured(box, monkeypatch, capsys):
    monkeypatch.setattr(listen_commands, "provider", lambda name: FakeProvider(["FEISHU_APP_ID is not set."]))
    for call in (
        lambda: listen_commands.handle_listen("feishu"),
        lambda: listen_commands.handle_send("feishu", "oc", "x"),
        lambda: listen_commands.handle_reply("feishu", "om", "x"),
        lambda: listen_commands.handle_receive("feishu", timeout=0),
    ):
        with pytest.raises(SystemExit) as exit_:
            call()
        assert exit_.value.code == 3
    assert capsys.readouterr().err.count("FEISHU_APP_ID is not set") == 4


def test_receive_exits_1_when_the_listener_could_not_start(box, fake, monkeypatch, capsys):
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: None)

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_receive("feishu", timeout=0)

    assert exit_.value.code == 1
    assert "listener exited at once" in capsys.readouterr().err


def test_done_forgets_a_taken_message_so_it_does_not_come_back(box, fake, capsys):
    deliver(box, i="om_q")
    listen_commands.handle_receive("feishu", timeout=0, start=False)
    capsys.readouterr()

    listen_commands.handle_done("feishu", "om_q")

    assert list(box.cur.iterdir()) == []
    assert box.release_stale(max_age=0) == 0


def test_listen_reports_a_refused_connection_in_one_line_and_exits_1(box, fake, capsys):
    # Invalid credentials made the SDK raise ClientException("app_id is
    # invalid") straight through Typer as a full traceback. The operator needs
    # the platform's sentence, the exit code, and a released lock; not a stack.
    def refuse(inbox, *, raw=False):
        raise RuntimeError("1000040346: app_id is invalid")

    fake.run = refuse

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_listen("feishu")

    assert exit_.value.code == 1
    err = capsys.readouterr().err
    assert "app_id is invalid" in err
    assert "Traceback" not in err
    assert "listener stopped" in box.logfile.read_text()
    assert box.listener_pid() is None, "the lock is released for the next listener"


def test_ls_skips_malformed_queue_files_without_claiming_valid_messages(box, capsys):
    (box.new / '1-torn').write_text('{')
    deliver(box)
    listen_commands.handle_ls('feishu')
    assert 'om_1\toc_a' in capsys.readouterr().out
    assert box.receive(0).id == 'om_1'
    assert (box.bad / '1-torn').exists()
