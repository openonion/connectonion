"""Group history on joining, older media on demand, and a client WhatsApp refuses (#2853).

Added to a group that already held nine messages and some PDFs, the account
recorded one empty message: WhatsApp had sent the history as an encrypted
bundle nobody opened. A photo the listener missed could never be fetched,
because nothing kept its keys. And a fresh install linked with neonize 0.4.3,
which WhatsApp now refuses at connect (405), with only a raw log line to say so.

Everything WhatsApp-side is faked: the CDN is a function, the protobufs are
stand-ins carrying the SDK's field names, and the encryption is done here with
the scheme the code decrypts. Whether WhatsApp really encrypts bundles under
"Group History" needs a real account; the one external fact checked here is
the HKDF fixture from oxidezap/whatsapp-rust (computed with Node's hkdfSync).
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import zlib
from types import ModuleType, SimpleNamespace

import pytest

from connectonion.cli.commands import whatsapp_commands
from connectonion.inbox import whatsapp as wa
from connectonion.inbox import whatsapp_media as media
from connectonion.inbox.store import Inbox, Message

GROUP = "120363000000000002@g.us"
ADDER = "61400000003@s.whatsapp.net"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.setenv("WHATSAPP_SESSION", str(tmp_path / "session.db"))


def encrypt(plain: bytes, info: str):
    """WhatsApp's media scheme, written out independently of the code under test."""
    from cryptography.hazmat.primitives import hashes, padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    key = os.urandom(32)
    expanded = HKDF(algorithm=hashes.SHA256(), length=112, salt=None, info=info.encode()).derive(key)
    iv, cipher_key, mac_key = expanded[:16], expanded[16:48], expanded[48:80]
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain) + padder.finalize()
    encryptor = Cipher(algorithms.AES(cipher_key), modes.CBC(iv)).encryptor()
    body = encryptor.update(padded) + encryptor.finalize()
    blob = body + hmac.new(mac_key, iv + body, hashlib.sha256).digest()[:10]
    return blob, SimpleNamespace(directPath="/v/t62/fictional.enc", mediaKey=key, mimetype="application/protobuf",
                                 fileSHA256=hashlib.sha256(plain).digest(),
                                 fileEncSHA256=hashlib.sha256(blob).digest())


def field1(*entries: bytes) -> bytes:
    """`GroupHistory { repeated bytes messages = 1 }` on the wire, plus one other field."""
    out = b"\x10\x05"   # field 2, varint: skipped
    for entry in entries:
        size, length = b"", len(entry)
        while True:
            size += bytes([(length & 0x7F) | (0x80 if length > 0x7F else 0)])
            length >>= 7
            if not length:
                break
        out += b"\x0a" + size + entry
    return out


# ---- the crypto ------------------------------------------------------------

def test_group_history_keys_match_the_independent_fixture():
    iv, _, _ = media.media_keys(b"\x5a" * 32, "Group History")
    assert iv == bytes([0x71, 0xba, 0xe6, 0x97, 0x44, 0x61, 0xbf, 0x53,
                        0xab, 0xc8, 0x9a, 0xcd, 0xf9, 0xca, 0xbe, 0x19])


def test_a_file_opens_only_under_its_own_kind():
    blob, variant = encrypt(b"%PDF-1.7 fictional itinerary", "WhatsApp Document Keys")
    ref = media.reference(variant, "document")

    assert media.decrypt(blob, ref) == b"%PDF-1.7 fictional itinerary"
    with pytest.raises(media.MediaError, match="MAC"):
        media.decrypt(blob, {**ref, "kind": "image"})
    with pytest.raises(media.MediaError, match="fileEncSha256"):
        media.decrypt(blob[:-1] + b"\0", ref)


def test_the_history_payload_is_read_entry_by_entry_and_bounded(monkeypatch):
    assert media.history_entries(zlib.compress(field1(b"one", b"x" * 300))) == [b"one", b"x" * 300]
    monkeypatch.setattr(media, "MAX_HISTORY_ENTRIES", 1)
    with pytest.raises(media.MediaError, match="more than 1"):
        media.history_entries(zlib.compress(field1(b"a", b"b")))


def test_a_file_whatsapp_dropped_is_told_apart(monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(410))
    with pytest.raises(media.MediaGone, match="no longer has this file"):
        media.fetch({"direct_path": "/v/t62/gone.enc"})


# ---- history into the inbox ------------------------------------------------

@pytest.fixture
def sdk(monkeypatch):
    """The two neonize pieces the history reader imports. Importing the real
    neonize starts a runtime thread, which this suite does not leave behind."""
    web = ModuleType("neonize.proto.waWeb.WAWebProtobufsWeb_pb2")

    class WebMessageInfo:
        @staticmethod
        def FromString(data):
            row = json.loads(data)
            kind_field = row.get("field")
            fields = []
            if kind_field:
                variant = SimpleNamespace(**{k: (base64.b64decode(v) if k in ("mediaKey", "fileSHA256", "fileEncSHA256") else v)
                                             for k, v in row["variant"].items()})
                fields = [(SimpleNamespace(name=kind_field, type=11, label=1, is_repeated=False,
                                           TYPE_MESSAGE=11, LABEL_REPEATED=3), variant)]
            message = SimpleNamespace(text=row.get("text", ""), ListFields=lambda: fields)
            return SimpleNamespace(key=SimpleNamespace(remoteJID=row.get("chat", GROUP), ID=row["id"],
                                                       participant=""),
                                   participant=row["sender"], messageTimestamp=row["at"],
                                   pushName=row.get("push", ""), message=message)

    web.WebMessageInfo = WebMessageInfo
    text = ModuleType("neonize.utils.message")
    text.extract_text = lambda message: getattr(message, "text", "")
    for name, module in (("neonize.proto.waWeb.WAWebProtobufsWeb_pb2", web), ("neonize.utils.message", text)):
        monkeypatch.setitem(sys.modules, name, module)


def bundle_event(variant):
    return SimpleNamespace(Message=SimpleNamespace(messageHistoryBundle=variant))


def test_joining_a_group_reads_its_history_into_the_log_and_queues_none(sdk, monkeypatch):
    _, pdf = encrypt(b"%PDF fictional", "WhatsApp Document Keys")
    pdf_ref = {"directPath": pdf.directPath, "mediaKey": base64.b64encode(pdf.mediaKey).decode(),
               "fileSHA256": base64.b64encode(pdf.fileSHA256).decode(),
               "fileEncSHA256": base64.b64encode(pdf.fileEncSHA256).decode(),
               "mimetype": "application/pdf", "fileName": "rates.pdf"}
    entries = [json.dumps({"id": "3EB0H1", "sender": "61400000004@s.whatsapp.net", "at": 1762900000,
                           "text": "the rates are attached"}).encode(),
               json.dumps({"id": "3EB0H2", "sender": "61400000004@s.whatsapp.net", "at": 1762900060,
                           "field": "documentMessage", "variant": pdf_ref}).encode(),
               json.dumps({"id": "3EB0X", "chat": "120363999@g.us", "sender": "x", "at": 1}).encode()]
    blob, variant = encrypt(zlib.compress(field1(*entries)), "Group History")
    monkeypatch.setattr(wa, "fetch", lambda ref: blob)
    inbox = Inbox("whatsapp")
    bundle = Message(id="3EB0BUNDLE", chat=GROUP, sender=ADDER, text="", at="2026-11-13T00:00:00Z",
                     kind="history", mentioned=True)

    wa.WhatsApp().read_history(inbox, bundle, bundle_event(variant))

    rows = [json.loads(line) for line in inbox.received.read_text().splitlines()]
    assert [(r["id"], r["kind"], r.get("history")) for r in rows] == [
        ("3EB0H1", "text", True), ("3EB0H2", "document", True), ("3EB0BUNDLE", "history", True)]
    assert rows[1]["attachments"][0]["file_name"] == "rates.pdf"
    assert not any(r["mentioned"] for r in rows)
    assert "shared 2 earlier messages" in rows[2]["text"]   # another chat's entry is refused
    assert list(inbox.new.iterdir()) == []                  # nothing to answer


def test_a_bundle_that_does_not_open_says_why_and_does_not_stop_the_listener(sdk, monkeypatch):
    blob, variant = encrypt(zlib.compress(field1(b"{}")), "WhatsApp History Keys")   # the wrong key
    monkeypatch.setattr(wa, "fetch", lambda ref: blob)
    inbox = Inbox("whatsapp")
    bundle = Message(id="3EB0B2", chat=GROUP, sender=ADDER, text="", at="2026-11-13T00:00:00Z", kind="history")

    wa.WhatsApp().read_history(inbox, bundle, bundle_event(variant))

    [row] = [json.loads(line) for line in inbox.received.read_text().splitlines()]
    assert "could not be read" in row["text"] and "MAC" in row["text"]


# ---- download ----------------------------------------------------------------

def stored(inbox, **record):
    inbox.received.parent.mkdir(parents=True, exist_ok=True)
    with inbox.received.open("a") as handle:
        handle.write(json.dumps({"chat": GROUP, "sender": ADDER, "text": "", "at": "2026-11-12T00:00:00Z",
                                 **record}) + "\n")


def run_download(*args):
    try:
        whatsapp_commands.handle_download(*args)
    except SystemExit as exit_:
        return exit_.code
    return 0


def test_download_fetches_a_stored_document_with_its_extension(tmp_path, monkeypatch, capsys):
    blob, variant = encrypt(b"%PDF fictional", "WhatsApp Document Keys")
    variant.fileName = "rates.pdf"
    inbox = Inbox("whatsapp")
    stored(inbox, id="3EB0D1", kind="document", attachments=[media.reference(variant, "document")])
    monkeypatch.setattr(media, "fetch", lambda ref: blob)

    assert run_download("3EB0D1", str(tmp_path / "out")) == 0
    saved = tmp_path / "out" / "3EB0D1.pdf"
    assert capsys.readouterr().out.strip() == str(saved) and saved.read_bytes() == b"%PDF fictional"


def test_download_says_which_failure_it_is(monkeypatch, capsys):
    blob, variant = encrypt(b"jpeg", "WhatsApp Image Keys")
    inbox = Inbox("whatsapp")
    stored(inbox, id="3EB0T", kind="text", text="hello")
    stored(inbox, id="3EB0OLD", kind="image")
    stored(inbox, id="3EB0GONE", kind="image", attachments=[media.reference(variant, "image")])

    def gone(ref):
        raise media.MediaGone("WhatsApp no longer has this file")

    monkeypatch.setattr(media, "fetch", gone)
    assert run_download("3EB0T") == 1
    assert run_download("3EB0OLD") == 1
    assert run_download("3EB0GONE") == whatsapp_commands.EXIT_GONE == 4
    err = " ".join(capsys.readouterr().err.split())
    assert "has no media to download" in err
    assert "arrived before its keys were kept for a later download" in err
    assert "no longer has this file" in err


def test_live_media_keeps_what_a_later_download_needs(tmp_path, monkeypatch):
    _, variant = encrypt(b"jpeg", "WhatsApp Image Keys")
    descriptor = SimpleNamespace(name="imageMessage", type=11, label=1, is_repeated=False,
                                 TYPE_MESSAGE=11, LABEL_REPEATED=3)
    event = SimpleNamespace(Message=SimpleNamespace(ListFields=lambda: [(descriptor, variant)]))
    message = Message(id="3EB0LIVE", chat=GROUP, sender=ADDER, text="", at="", kind="image")

    class Offline:
        def download_any(self, message, path=None):
            raise RuntimeError("listener offline for media")

    wa.WhatsApp().fetch_media(Inbox("whatsapp", tmp_path), message, event, Offline())

    assert message.attachments[0]["direct_path"] == variant.directPath
    assert "error" in message.media   # the live fetch failed, the keys are still kept


# ---- a client WhatsApp refuses ----------------------------------------------

def test_a_405_stops_the_listener_with_the_upgrade_command(monkeypatch):
    bot = wa.WhatsApp()
    bot._client = SimpleNamespace(disconnect=lambda: None)
    stopped = SimpleNamespace(set=lambda: None)
    monkeypatch.setattr(wa, "_neonize_versions", lambda: ("0.4.3.post0", "0.10.0"))

    bot._connect_failed(Inbox("whatsapp"), stopped, SimpleNamespace(Reason=wa.CLIENT_OUTDATED, Message=""))

    assert bot._fatal_reason.startswith("WhatsApp rejected this client as outdated (405)")
    assert "neonize 0.4.3.post0" in bot._fatal_reason and "connectonion[whatsapp]" in bot._fatal_reason


def test_check_names_an_installed_neonize_older_than_the_pin(monkeypatch):
    monkeypatch.setattr(wa, "_neonize_versions", lambda: ("0.4.3.post0", "0.10.0"))
    [problem] = wa.WhatsApp().protocol_floor()
    assert "neonize 0.4.3.post0 is installed; this co needs 0.10.0" in problem
    monkeypatch.setattr(wa, "_neonize_versions", lambda: ("0.10.0", "0.10.0"))
    assert wa.WhatsApp().protocol_floor() == []


def test_the_installed_neonize_is_not_older_than_the_pin():
    """A lock or an environment that drifted back below the pin would link a
    client WhatsApp refuses."""
    import re
    from importlib import metadata
    from pathlib import Path

    from packaging.version import Version

    try:
        installed = metadata.version("neonize")
    except metadata.PackageNotFoundError:
        pytest.skip("the whatsapp extra is not installed")
    pyproject = (Path(__file__).parents[2] / "pyproject.toml").read_text()
    pinned = re.search(r'"neonize==([^"]+)"', pyproject).group(1)
    assert Version(installed) >= Version(pinned) >= Version("0.10.0")


def test_the_sdk_pieces_used_are_the_sdks():
    """The stand-ins above are honest only if neonize has these names. In a
    subprocess: importing neonize starts a runtime thread."""
    import importlib.util
    import subprocess

    if importlib.util.find_spec("neonize") is None:
        pytest.skip("the whatsapp extra is not installed")
    check = (
        "from neonize.proto import Neonize_pb2 as n\n"
        f"assert n.CLIENT_OUTDATED == {wa.CLIENT_OUTDATED}\n"
        "from neonize.events import ClientOutdatedEv\n"
        "from neonize.proto.waE2E.WAWebProtobufsE2E_pb2 import Message, MessageHistoryBundle\n"
        "from neonize.proto.waWeb.WAWebProtobufsWeb_pb2 import WebMessageInfo\n"
        "names = lambda t: {f.name for f in t.DESCRIPTOR.fields}\n"
        "assert 'messageHistoryBundle' in names(Message)\n"
        "assert {'directPath', 'mediaKey', 'fileSHA256', 'fileEncSHA256', 'mimetype'} <= names(MessageHistoryBundle)\n"
        "assert {'key', 'message', 'messageTimestamp', 'participant', 'pushName'} <= names(WebMessageInfo)\n"
        "from neonize.proto.waCommon.WACommon_pb2 import MessageKey\n"
        "assert {'remoteJID', 'ID', 'participant'} <= names(MessageKey)\n"
    )
    result = subprocess.run([sys.executable, "-c", check], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
