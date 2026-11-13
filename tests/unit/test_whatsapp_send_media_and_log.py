"""`send --image/--file` printed only `'text'`; `log` left out what we said (#3001).

An agent delivering video previews to a team group could not send a single
picture: the listener it handed them to was a release from before pictures
existed, which read every request as text and answered with the missing key.
And `log --chat … --since 2d` could not show it what it had already replied,
because only received.jsonl was read.

The send runs the whole real path here: the CLI, the outbox, and a listener
thread draining it onto a fake client. Nothing talks to WhatsApp.
"""

import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion import __version__
from connectonion.cli.commands import listen_commands
from connectonion.inbox import whatsapp as wa
from connectonion.inbox.store import Inbox, Message

GROUP = "120363000000000001@g.us"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.setenv("WHATSAPP_SESSION", str(tmp_path / "session.db"))
    monkeypatch.setattr(wa, "_build_jid", lambda chat: SimpleNamespace(User=chat.split("@")[0]))
    monkeypatch.setattr(wa, "SEND_TIMEOUT_SECONDS", 2.0)


class MediaClient:
    def __init__(self):
        self.calls = []

    def send_image(self, to, file, caption=None, quoted=None):
        self.calls.append(("image", to.User, Path(file).name, caption))
        return SimpleNamespace(ID="3EBIMG")

    def send_document(self, to, file, caption=None, filename=None, mimetype=None, quoted=None):
        self.calls.append(("document", to.User, filename, caption))
        return SimpleNamespace(ID="3EBDOC")


def running_listener(monkeypatch, version):
    """A listener holding the lock that recorded `version` (None: before tracking)."""
    monkeypatch.setattr(Inbox, "listener_pid", lambda self: 4242)
    monkeypatch.setattr(Inbox, "listener_version", lambda self, pid: version)


@pytest.fixture
def listener():
    bot = wa.WhatsApp()
    bot._client = MediaClient()
    stop = threading.Event()
    thread = threading.Thread(target=bot._drain_outbox, args=(Inbox("whatsapp"), stop), daemon=True)
    thread.start()
    yield bot
    stop.set()
    thread.join(timeout=5)


def test_an_image_and_a_file_go_out_through_the_real_send_path(tmp_path, monkeypatch, listener, capsys):
    running_listener(monkeypatch, __version__)
    card = tmp_path / "preview.png"
    card.write_bytes(PNG)
    cut = tmp_path / "cut-v2.mp4"
    cut.write_bytes(b"\0\0\0\x18ftypmp42")

    listen_commands.handle_send("whatsapp", GROUP, "v2 preview", plain=True, image=str(card))
    listen_commands.handle_send("whatsapp", GROUP, "the cut", plain=True, file=str(cut))

    assert capsys.readouterr().out.split() == ["3EBIMG", "3EBDOC"]
    assert listener._client.calls == [("image", GROUP.split("@")[0], "preview.png", "v2 preview"),
                                      ("document", GROUP.split("@")[0], "cut-v2.mp4", "the cut")]


def test_a_listener_from_before_pictures_is_named_and_nothing_is_queued(tmp_path, monkeypatch, capsys):
    running_listener(monkeypatch, None)
    card = tmp_path / "preview.png"
    card.write_bytes(PNG)

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_send("whatsapp", GROUP, "v2 preview", plain=True, image=str(card))

    assert exit_.value.code == 1
    err = " ".join(capsys.readouterr().err.split())
    assert "cannot send pictures or files" in err and "co whatsapp listen --restart" in err
    assert not list((Inbox("whatsapp").root / "outbox").glob("*.json"))


def test_a_request_the_listener_does_not_know_says_so_instead_of_naming_a_key():
    bot = wa.WhatsApp()
    bot._client = MediaClient()

    with pytest.raises(RuntimeError) as refused:
        bot._perform({"kind": "sticker_pack", "chat": GROUP})

    assert "sticker_pack" in str(refused.value) and "listen --restart" in str(refused.value)
    assert str(refused.value) != "'text'"


def test_log_since_includes_what_we_said_and_nothing_older(capsys):
    box = Inbox("whatsapp")
    for at, i, text in (("2026-10-20T09:00:00Z", "3EB0OLD", "October"),
                        ("2026-11-12T09:00:00Z", "3EB0NEW", "is v2 ready?")):
        box.deliver(Message(id=i, chat=GROUP, sender="61400000002@s.whatsapp.net",
                            text=text, at=at, mentioned=True))
    sent = [{"at": "2026-10-20T09:05:00Z", "chat": GROUP, "text": "old reply", "id": "3EB0R1", "ok": True},
            {"at": "2026-11-12T09:05:00Z", "chat": GROUP, "text": "v2 is up", "id": "3EB0R2", "ok": True},
            {"at": "2026-11-12T09:06:00Z", "chat": GROUP, "text": "failed", "id": None, "ok": False}]
    box.sent.write_text("".join(json.dumps(r) + "\n" for r in sent))
    # own.jsonl echoes our sends too; one message is one line in the log.
    box.own.write_text(json.dumps({"id": "3EB0R2", "chat": GROUP, "at": "2026-11-12T09:05:01Z",
                                   "text": "v2 is up", "from_me": True}) + "\n")

    listen_commands.handle_log("whatsapp", chat=GROUP, since="2026-11-01")

    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    assert [(r["id"], bool(r.get("from_me"))) for r in rows] == [("3EB0NEW", False), ("3EB0R2", True)]


def test_restart_keeps_the_old_listener_when_this_co_cannot_run_a_new_one(monkeypatch, capsys):
    """`listen --restart` starts the new listener on this co's own Python, not
    the old listener's venv. A co without the whatsapp extra stopped the only
    working listener and then could not start one: no listener at all."""
    running_listener(monkeypatch, None)
    killed = []
    monkeypatch.setattr("os.kill", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(wa.WhatsApp, "listen_requirements", lambda self: [wa.SDK_MISSING])

    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_listen("whatsapp", restart=True)

    assert exit_.value.code == listen_commands.EXIT_CONFIG
    assert killed == []
    assert "connectonion[whatsapp]" in capsys.readouterr().err
