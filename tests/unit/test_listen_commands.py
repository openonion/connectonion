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
from connectonion.inbox import ANSWERING, Inbox, Message


class FakeProvider:
    def __init__(self, problems=()):
        self.problems = list(problems)
        self.sent = []
        self.reacted = []
        # What happened, in order. Whether the mark lands before or after the
        # work is the whole point of it, so ordering has to be observable.
        self.order = []
        self.reaction_fails = False

    def missing(self):
        return self.problems

    def check(self):
        return self.problems

    def send(self, chat, text, *, reply_to=None, fresh=False):
        self.sent.append((chat, text, reply_to))
        self.order.append("send")
        return f"om_sent{len(self.sent)}"

    def react(self, chat, message_id, emoji, *, sender=""):
        if self.reaction_fails:
            raise RuntimeError("rate limited")
        self.reacted.append((chat, message_id, emoji, sender))
        self.order.append("react")
        return f"om_react{len(self.reacted)}"


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
    assert json.loads(out) == {"id": "om_1", "chat": "oc_a", "thread": None, "sender": "on_x", "sender_name": "",
                               "text": "hi", "kind": "text", "quoted": None, "mentioned": True, "at": "2026-09-02T10:00:00Z"}
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


class TestFindingAConversation:
    """The chat id is what send and reply need, and nothing printed it."""

    @staticmethod
    def _traffic(box):
        deliver(box, i="g1", chat="oc_ops", text="deploy is red")
        deliver(box, i="g2", chat="oc_ops", text="@bot look at it")
        box.deliver(Message(id="g3", chat="oc_ops", sender="on_y", sender_name="Eric Fu",
                            text="never mind", at="2026-09-02T11:00:00Z",
                            thread=None, mentioned=False))
        deliver(box, i="d1", chat="on_x", text="hello")

    def test_chats_lists_every_conversation_with_what_tells_them_apart(self, box, fake, capsys):
        self._traffic(box)

        listen_commands.handle_chats("feishu")

        rows = [line.split("\t") for line in capsys.readouterr().out.splitlines()
                if "\t" in line]
        by_chat = {row[0]: row for row in rows}
        assert set(by_chat) == {"oc_ops", "on_x"}
        assert by_chat["oc_ops"][2] == "3"          # messages
        assert by_chat["oc_ops"][5] == "Eric Fu"    # the last speaker, by name

    def test_the_rows_are_really_tab_separated(self, box, fake, capsys, monkeypatch):
        """`cut -f1` must give the chat id, which is the point of this verb.

        Rich expands \\t into spaces, so a row printed through it looks right on
        a terminal and cannot be cut. The contact listing learned this the same
        way; a row pinned by a width is the only way it stays true.
        """
        from rich.console import Console

        monkeypatch.setattr(listen_commands, "console", Console(force_terminal=False, width=200))
        self._traffic(box)

        listen_commands.handle_chats("feishu")

        first = capsys.readouterr().out.splitlines()[0]
        assert first.split("\t")[0] == "on_x"
        assert len(first.split("\t")) == 7

    def test_an_empty_inbox_says_so_instead_of_printing_nothing(self, box, fake, capsys):
        listen_commands.handle_chats("feishu")

        assert "no conversations yet" in capsys.readouterr().err

    def test_log_narrows_to_one_conversation(self, box, fake, capsys):
        self._traffic(box)

        listen_commands.handle_log("feishu", chat="oc_ops")

        chats = {json.loads(line)["chat"] for line in capsys.readouterr().out.splitlines()}
        assert chats == {"oc_ops"}

    def test_log_keeps_messages_nobody_addressed_to_the_bot(self, box, fake, capsys):
        # The whole point of asking for a conversation: `mention_only` decides
        # when the bot speaks, not what it may read back.
        self._traffic(box)

        listen_commands.handle_log("feishu", chat="oc_ops")

        texts = [json.loads(line)["text"] for line in capsys.readouterr().out.splitlines()]
        assert "deploy is red" in texts and "never mind" in texts

    def test_a_sender_can_be_named_by_id_or_by_name(self, box, fake, capsys):
        self._traffic(box)

        listen_commands.handle_log("feishu", sender="Eric Fu")
        by_name = capsys.readouterr().out.splitlines()
        listen_commands.handle_log("feishu", sender="on_y")
        by_id = capsys.readouterr().out.splitlines()

        assert len(by_name) == 1 and by_name == by_id

    def test_the_cap_keeps_the_most_recent(self, box, fake, capsys):
        # A conversation is read backwards from its last turn. Getting this end
        # wrong is what #1571 was.
        self._traffic(box)

        listen_commands.handle_log("feishu", chat="oc_ops", last=1)

        assert json.loads(capsys.readouterr().out)["text"] == "never mind"

    def test_an_unreadable_window_is_a_usage_error_not_a_traceback(self, box, fake, capsys):
        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_log("feishu", since="last week")

        assert exit_.value.code == 2
        assert "30d" in capsys.readouterr().err

    def test_an_unfiltered_log_is_what_it_always_was(self, box, fake, capsys):
        # No filter means the tail, including the `handled by` preamble.
        self._traffic(box)

        listen_commands.handle_log("feishu")

        assert len(capsys.readouterr().out.splitlines()) >= 4


class TestTheConversationAroundAMessage:
    """A group asks things across several messages; a consumer got only the last."""

    @staticmethod
    def _conversation(box, fake, capsys=None):
        """Three earlier turns and our answer, then the message that asks for it.

        The earlier ones are taken off the queue first, because `receive`
        returns the oldest and the point of the test is the *last* message
        arriving with the conversation behind it.
        """
        deliver(box, i="om_1", chat="oc_ops", text="the price sheet is wrong")
        deliver(box, i="om_2", chat="oc_ops", text="it's missing the cleaning column")
        deliver(box, i="om_other", chat="oc_else", text="unrelated chatter")
        for _ in range(3):
            listen_commands.handle_receive("feishu", timeout=0, start=False)
        box.record_sent(chat="oc_ops", text="looking now", provider_id="om_s1", by="reply")
        deliver(box, i="om_3", chat="oc_ops", text="@bot recompute")
        if capsys is not None:
            capsys.readouterr()

    def test_without_the_flag_the_line_is_what_it_always_was(self, box, fake, capsys):
        # Opt-in: anyone parsing this today must see the same bytes.
        self._conversation(box, fake, capsys)

        listen_commands.handle_receive("feishu", timeout=0, start=False)

        assert "context" not in json.loads(capsys.readouterr().out)

    def test_the_turns_before_it_come_along(self, box, fake, capsys):
        self._conversation(box, fake, capsys)

        listen_commands.handle_receive("feishu", timeout=0, start=False, context=10)

        record = json.loads(capsys.readouterr().out)
        assert [turn["text"] for turn in record["context"]] == [
            "the price sheet is wrong", "it's missing the cleaning column", "looking now"]

    def test_our_own_replies_are_in_it(self, box, fake, capsys):
        # A transcript with the bot's answers missing reads as though it never
        # responded, and a model given that apologises for ignoring someone it
        # already helped.
        self._conversation(box, fake, capsys)

        listen_commands.handle_receive("feishu", timeout=0, start=False, context=10)

        turns = json.loads(capsys.readouterr().out)["context"]
        assert [turn["from"] for turn in turns] == ["them", "them", "us"]

    def test_another_chat_does_not_leak_in(self, box, fake, capsys):
        self._conversation(box, fake, capsys)

        listen_commands.handle_receive("feishu", timeout=0, start=False, context=10)

        texts = [turn["text"] for turn in json.loads(capsys.readouterr().out)["context"]]
        assert "unrelated chatter" not in texts

    def test_the_message_itself_is_not_repeated_in_its_own_context(self, box, fake, capsys):
        self._conversation(box, fake, capsys)

        listen_commands.handle_receive("feishu", timeout=0, start=False, context=10)

        record = json.loads(capsys.readouterr().out)
        assert record["text"] not in [turn["text"] for turn in record["context"]]

    def test_the_count_keeps_the_most_recent_turns(self, box, fake, capsys):
        # The cap has to fall on the older end: a conversation is understood
        # from its last few turns, not its first.
        self._conversation(box, fake, capsys)

        listen_commands.handle_receive("feishu", timeout=0, start=False, context=1)

        turns = json.loads(capsys.readouterr().out)["context"]
        assert [turn["text"] for turn in turns] == ["looking now"]

    def test_consume_hands_the_context_to_the_command(self, box, fake, monkeypatch):
        monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)
        self._conversation(box, fake)
        command = [sys.executable, "-c",
                   "import json,sys; m=json.load(sys.stdin); "
                   "print(len(m.get('context', [])), 'turns before it')"]

        listen_commands.handle_consume("feishu", command, once=True, context=10)

        assert fake.sent[-1][1] == "3 turns before it"


def test_a_reply_marks_the_message_as_being_answered_before_it_sends(box, fake, capsys):
    # The listener marks a message "seen" as it queues it; this is the other
    # half — the mark changes the moment an answer is actually on its way, so
    # the chat can tell "queued" from "being worked on".
    deliver(box, i="om_q", chat="oc_ops")

    listen_commands.handle_reply("feishu", "om_q", "fixed")

    assert fake.order == ["react", "send"]
    assert fake.reacted == [("oc_ops", "om_q", ANSWERING, "on_x")]


def test_a_mark_that_fails_does_not_cost_the_reply(box, fake, capsys):
    # A receipt is worth less than the answer it was announcing.
    fake.reaction_fails = True
    deliver(box, i="om_q", chat="oc_ops")

    listen_commands.handle_reply("feishu", "om_q", "fixed")

    assert fake.sent == [("oc_ops", "fixed", "om_q")]
    assert "rate limited" in (box.root / "log").read_text(encoding="utf-8")


def test_a_message_that_was_not_addressed_to_us_is_not_marked(box, fake, capsys):
    # Someone can reply by hand to anything in the log. Marking a message the
    # bot was never asked about puts our emoji on a stranger's conversation.
    box.deliver(Message(id="om_chatter", chat="oc_ops", sender="on_x", text="hi",
                        at="2026-09-02T10:00:00Z", thread=None, mentioned=False))

    listen_commands.handle_reply("feishu", "om_chatter", "fixed")

    assert fake.reacted == []
    assert fake.sent == [("oc_ops", "fixed", "om_chatter")]


def test_marking_can_be_turned_off(box, fake, capsys, monkeypatch):
    monkeypatch.setenv("CO_INBOX_REACT", "0")
    deliver(box, i="om_q", chat="oc_ops")

    listen_commands.handle_reply("feishu", "om_q", "fixed")

    assert fake.reacted == []
    assert fake.sent == [("oc_ops", "fixed", "om_q")]


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


def test_consume_pipes_the_message_through_a_command_and_replies_with_its_stdout(box, fake, monkeypatch):
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)
    deliver(box, i="om_s", chat="oc_s", text="what is 2+2")
    command = [sys.executable, "-c",
               "import json,os,sys; m=json.load(sys.stdin); "
               "print('you asked', m['text'], 'in', os.environ['CO_CHAT'], 'msg', os.environ['CO_MSG_ID'])"]

    listen_commands.handle_consume("feishu", command, once=True)

    assert fake.sent == [("oc_s", "you asked what is 2+2 in oc_s msg om_s", "om_s")]
    assert list(box.cur.iterdir()) == []
    assert (box.root / "chats" / "oc_s").is_dir()


def test_consume_marks_before_running_the_command_not_after(box, fake, monkeypatch):
    # In `consume` the command *is* the answering, and it can take minutes.
    # Marking after it would light up for the instant before the reply lands,
    # which is the same as not marking at all — and that interval is precisely
    # what the chat cannot otherwise tell apart from the bot being down.
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)
    deliver(box, i="om_s", chat="oc_s", text="what is 2+2")
    marks = []
    command = [sys.executable, "-c", "import sys; sys.stdin.read(); print('4')"]
    original = listen_commands._mark_answering

    def record(p, inbox, message):
        marks.append(list(p.order))
        return original(p, inbox, message)

    monkeypatch.setattr(listen_commands, "_mark_answering", record)
    listen_commands.handle_consume("feishu", command, once=True)

    assert marks == [[]]                      # nothing had happened yet
    assert fake.order == ["react", "send"]
    assert fake.reacted == [("oc_s", "om_s", ANSWERING, "on_x")]


def _taken(box):
    return sorted(p.name.split("-", 1)[1] for p in box.cur.iterdir())


def test_consume_sends_nothing_for_a_failing_or_silent_command(box, fake, monkeypatch):
    # A command that exits non-zero did not answer: the message stays taken
    # and comes back in an hour, as the docs promise. Empty stdout with exit
    # 0 is the command choosing silence: done. Both are one log line.
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)
    deliver(box, i="om_f")
    listen_commands.handle_consume("feishu", [sys.executable, "-c", "import sys; sys.exit(3)"], once=True)
    deliver(box, i="om_g")
    listen_commands.handle_consume("feishu", [sys.executable, "-c", "pass"], once=True)

    assert fake.sent == []
    log = box.logfile.read_text()
    # The loop names the message and why it is coming back; the handler
    # supplies the reason. One line, not two.
    assert "om_f not finished" in log and "command exited 3" in log
    assert "nothing to say for om_g" in log
    assert _taken(box) == ["om_f"], "the failed one waits for the sweep; the silent one is done"


def test_consume_keeps_a_message_whose_reply_the_platform_refused(box, fake, monkeypatch):
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)

    def refuse(chat, text, *, reply_to=None):
        raise RuntimeError("Feishu error 99991400: too many requests")

    fake.send = refuse
    deliver(box, i="om_r")

    listen_commands.handle_consume("feishu", [sys.executable, "-c", "print('answer')"], once=True)

    assert _taken(box) == ["om_r"], "not consumed by a refusal it can retry later"
    assert "om_r not finished" in box.logfile.read_text()
    assert "reply failed" in box.logfile.read_text()


def test_consume_refuses_a_command_it_cannot_run_before_taking_a_message(box, fake, monkeypatch, capsys):
    # A typo in the command used to claim the message into cur/ and then
    # traceback, stranding one message per restart.
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self: 1)
    deliver(box, i="om_n")

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_consume("feishu", ["./no-such-answer.sh"], once=True)

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
    assert "feishu configured" in out and "no listener running" in out and "1 unread" in out


class TestCheckDoesNotClaimTheNetwork:
    """"reachable" was inferred from an import, a SQLite row and a pid."""

    def test_configured_is_not_the_same_word_as_connected(self, box, fake, capsys):
        # The old line said "reachable" without touching the network, so a
        # connection that had quietly stopped still got a green tick — the
        # failure this release is about, inside the command people run to look
        # for it.
        listen_commands.handle_check("feishu")

        captured = capsys.readouterr()
        assert "reachable" not in captured.out
        assert "no listener is running" in captured.err

    def test_a_running_listener_that_says_it_is_connected_is_reported_as_connected(
            self, box, fake, capsys, monkeypatch):
        monkeypatch.setattr(Inbox, "listener_pid", lambda self: 4242)
        box.record_connection("connected", account="61410724095", ids=["61410724095"])
        import json as _json
        state = _json.loads(box.connection.read_text())
        state["pid"] = 4242
        box.connection.write_text(_json.dumps(state))

        listen_commands.handle_check("feishu")

        assert "connected as 61410724095" in capsys.readouterr().out

    def test_a_disconnected_listener_is_not_a_green_tick(self, box, fake, capsys, monkeypatch):
        monkeypatch.setattr(Inbox, "listener_pid", lambda self: 4242)
        import json as _json
        box.record_connection("disconnected")
        state = _json.loads(box.connection.read_text())
        state["pid"] = 4242
        box.connection.write_text(_json.dumps(state))

        listen_commands.handle_check("feishu")

        assert "disconnected" in capsys.readouterr().err

    def test_another_listeners_record_is_not_read_as_this_ones(
            self, box, fake, capsys, monkeypatch):
        # A `connected` left by a process that has since exited says what was
        # true once. Reading it as current is how a stale file becomes a
        # confident wrong answer.
        monkeypatch.setattr(Inbox, "listener_pid", lambda self: 4242)
        box.record_connection("connected", account="61410724095")   # records os.getpid()

        listen_commands.handle_check("feishu")

        captured = capsys.readouterr()
        assert "connected as" not in captured.out
        assert "has not said whether its socket is up" in captured.err

    def test_a_stopped_listener_says_why(self, box, fake, capsys, monkeypatch):
        monkeypatch.setattr(Inbox, "listener_pid", lambda self: 4242)
        import json as _json
        box.record_connection("stopped", reason="logged out by the phone")
        state = _json.loads(box.connection.read_text())
        state["pid"] = 4242
        box.connection.write_text(_json.dumps(state))

        listen_commands.handle_check("feishu")

        # Unwrapped: Rich folds at the console width, so the sentence is broken
        # across lines and a literal substring is not in the output at all —
        # the same shape that made a `--since` assertion pass locally and fail
        # on every CI job.
        said = " ".join(capsys.readouterr().err.split())
        assert "logged out by the phone" in said


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
