"""`co whatsapp send --image / --file`: a picture or a document, not only text (#1856).

The agent planning a trip in a WhatsApp group was asked "你可以发图片吗？" (can
you send pictures?) and could not: a rating card or a rendered itinerary had to
be flattened into a wall of text. The media goes through the same outbox as
text, because the listener owns the only socket a linked device may have.
"""

import json
from types import SimpleNamespace

import pytest

from connectonion.cli.commands import listen_commands
from connectonion.inbox import whatsapp as wa
from connectonion.inbox.store import Inbox

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 64
GIF = b"GIF89a" + b"\0" * 64


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    # CI does not install neonize; the stand-in carries the SDK's field names.
    monkeypatch.setattr(wa, "_build_jid", lambda chat: SimpleNamespace(User=chat.split("@")[0]))


def _file(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.fixture
def queued(monkeypatch):
    """What send() hands the listener, with the listener answering an id."""
    requests = []
    monkeypatch.setattr(wa.WhatsApp, "_request", lambda self, payload: requests.append(payload) or {"id": "3EBMEDIA"})
    return requests


def _bot(client=None):
    bot = wa.WhatsApp.__new__(wa.WhatsApp)
    bot.name = "whatsapp"
    bot._client = client
    return bot


def test_an_image_is_queued_with_its_absolute_path_and_rendered_caption(tmp_path, monkeypatch, queued):
    _file(tmp_path, "card.png", PNG)
    monkeypatch.chdir(tmp_path)
    assert _bot().send("447700900123@s.whatsapp.net", "**Tonight**", image="card.png") == "3EBMEDIA"
    [request] = queued
    assert request["kind"] == "image" and request["path"] == str(tmp_path / "card.png")
    assert request["caption"] == "*Tonight*" and request["mime"] == "image/png"


def test_a_file_is_queued_as_a_document_with_its_name_and_type(tmp_path, queued):
    plan = _file(tmp_path, "itinerary.pdf", b"%PDF-1.7 plan")
    _bot().send("447700900123@s.whatsapp.net", "", file=str(plan), plain=True)
    [request] = queued
    assert (request["kind"], request["name"], request["mime"]) == ("document", "itinerary.pdf", "application/pdf")
    assert request["caption"] == ""


@pytest.mark.parametrize("make, options, says", [
    (lambda d: d / "missing.png", {"image"}, "No file at"),
    (lambda d: _file(d, "empty.png", b""), {"image"}, "is empty"),
    (lambda d: _file(d, "anim.gif", GIF), {"image"}, "--file"),
    (lambda d: _file(d, "card.png", PNG), {"image", "file"}, "one of --image or --file"),
])
def test_what_cannot_be_sent_is_refused_before_anything_is_queued(tmp_path, queued, make, options, says):
    path = str(make(tmp_path))
    with pytest.raises(ValueError, match=says):
        _bot().send("447700900123@s.whatsapp.net", "", plain=True, **{o: path for o in options})
    assert queued == []


def test_a_picture_over_whatsapps_limit_is_refused_and_pointed_at_file(tmp_path, monkeypatch, queued):
    monkeypatch.setattr(wa, "IMAGE_LIMIT_BYTES", 32)
    big = _file(tmp_path, "big.jpg", JPEG)
    with pytest.raises(ValueError, match="--file"):
        _bot().send("447700900123@s.whatsapp.net", "", image=str(big), plain=True)
    assert queued == []


class MediaClient:
    """neonize's client: send_image and send_document, answering a SendResponse."""

    def __init__(self):
        self.calls = []

    def send_image(self, to, file, caption=None, quoted=None):
        self.calls.append(("image", to.User, file, caption, quoted))
        return SimpleNamespace(ID="3EBIMG")

    def send_document(self, to, file, caption=None, filename=None, mimetype=None, quoted=None):
        self.calls.append(("document", to.User, file, caption, filename, mimetype, quoted))
        return SimpleNamespace(ID="3EBDOC")


def test_the_listener_sends_the_image_on_its_own_connection(tmp_path):
    client = MediaClient()
    card = _file(tmp_path, "card.png", PNG)
    outcome = _bot(client)._perform({"kind": "image", "chat": "447700900123@s.whatsapp.net",
                                     "path": str(card), "caption": "Tonight", "reply_to": None})
    assert outcome == "3EBIMG"
    assert client.calls == [("image", "447700900123", str(card), "Tonight", None)]


def test_the_listener_sends_a_document_with_its_name_and_no_empty_caption(tmp_path):
    client = MediaClient()
    plan = _file(tmp_path, "itinerary.pdf", b"%PDF")
    outcome = _bot(client)._perform({"kind": "document", "chat": "120363@g.us", "path": str(plan),
                                     "caption": "", "name": "itinerary.pdf", "mime": "application/pdf",
                                     "reply_to": None})
    assert outcome == "3EBDOC"
    assert client.calls == [("document", "120363", str(plan), None, "itinerary.pdf", "application/pdf", None)]


class CliProvider:
    """What the CLI talks to: WhatsApp's own attachment checks, a recorded send."""
    via_listener = False
    sends_media = True

    def __init__(self):
        self.sent = []

    def missing(self):
        return []

    def render(self, text):
        return text

    def attachment(self, *, image=None, file=None):
        return wa.WhatsApp.attachment(self, image=image, file=file)

    def send(self, chat, text, **kw):
        self.sent.append((chat, text, kw))
        return "3EBCLI"


def test_the_cli_sends_an_image_without_a_caption_and_never_reads_stdin(tmp_path, monkeypatch, capsys):
    p = CliProvider()
    monkeypatch.setattr(listen_commands, "provider", lambda name: p)
    monkeypatch.setattr("sys.stdin", SimpleNamespace(read=lambda *a: pytest.fail("read stdin for a caption")))
    card = _file(tmp_path, "card.png", PNG)
    listen_commands.handle_send("whatsapp", "447700900123@s.whatsapp.net", None, image=str(card))
    assert capsys.readouterr().out.strip() == "3EBCLI"
    [(chat, text, kw)] = p.sent
    assert text == "" and kw["image"] == str(card)
    record = json.loads((Inbox("whatsapp").root / "sent.jsonl").read_text().splitlines()[-1])
    assert record["ok"] and record["media"] == {"kind": "image", "path": str(card), "size": len(PNG)}


def test_the_cli_refuses_a_bad_attachment_and_sends_nothing(tmp_path, monkeypatch, capsys):
    p = CliProvider()
    monkeypatch.setattr(listen_commands, "provider", lambda name: p)
    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_send("whatsapp", "447700900123@s.whatsapp.net", "hi",
                                    image=str(tmp_path / "missing.png"))
    assert exit_.value.code == 1 and p.sent == []
    assert "No file at" in capsys.readouterr().err


def test_a_provider_that_cannot_send_media_refuses_and_sends_nothing(tmp_path, monkeypatch, capsys):
    p = CliProvider()
    p.sends_media = False
    monkeypatch.setattr(listen_commands, "provider", lambda name: p)
    card = _file(tmp_path, "card.png", PNG)
    with pytest.raises(SystemExit) as exit_:
        listen_commands.handle_send("feishu", "oc_1", "hi", image=str(card))
    assert exit_.value.code == 1 and p.sent == []
    assert "--image" in capsys.readouterr().err


def test_send_help_offers_image_and_file():
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    result = CliRunner().invoke(app, ["whatsapp", "send", "--help"], env={"COLUMNS": "200", "NO_COLOR": "1"})
    assert "--image" in result.output and "--file" in result.output


def test_the_sdk_methods_used_exist_where_neonize_is_installed():
    # In a subprocess: importing neonize starts its runtime thread.
    import importlib.util
    import subprocess
    import sys
    if importlib.util.find_spec("neonize") is None:
        pytest.skip("the WhatsApp extra (neonize) is not installed")
    check = ("from neonize.client import NewClient as C; "
             "assert hasattr(C, 'send_image') and hasattr(C, 'send_document')")
    result = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
