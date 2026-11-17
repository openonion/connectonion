"""`co send` to an agent it cannot reach directly: a small file waits on the backend (#3088).

The receiver is behind a router, or its Host is not running. A file of up to
10 MB waits on the backend for a week, boxed to the receiver, and `co receive`
there takes it. The backend here is a stand-in for oo-api's /api/v1/files that
keeps what it is given in a dict; the boxes, the keys and the landing are real.
"""

import hashlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from connectonion import address
from connectonion.cli.commands import send_commands
from connectonion.network import file_send, file_stash
from connectonion.network.host import file_inbox


class _Backend(BaseHTTPRequestHandler):
    """/api/v1/files with the bearer token as the caller's address."""
    files: dict = {}

    def log_message(self, *args):
        pass

    def _caller(self):
        return self.headers["Authorization"].removeprefix("Bearer ")

    def _reply(self, status, body):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _id(self):
        return int(urlparse(self.path).path.rsplit("/", 1)[1])

    def do_POST(self):
        to = parse_qs(urlparse(self.path).query)["to"][0]
        data = self.rfile.read(int(self.headers["Content-Length"]))
        file_id = len(self.files) + 1
        self.files[file_id] = {"id": file_id, "to": to, "from_address": self._caller(),
                               "meta": self.headers["X-File-Meta"], "data": data, "size": len(data),
                               "expires_at": "2026-11-24T00:00:00+00:00"}
        self._reply(200, {"id": file_id, "size": len(data)})

    def do_GET(self):
        if urlparse(self.path).path == "/api/v1/files":
            mine = [{k: v for k, v in f.items() if k not in ("data", "to")}
                    for f in self.files.values() if f["to"] == self._caller()]
            return self._reply(200, {"files": mine})
        found = self.files.get(self._id())
        if not found or found["to"] != self._caller():
            return self._reply(404, {"detail": "no such file"})
        self._reply(200, found["data"])

    def do_DELETE(self):
        found = self.files.get(self._id())
        if found and self._caller() in (found["to"], found["from_address"]):
            del self.files[self._id()]
            return self._reply(200, {"deleted": True})
        self._reply(404, {"detail": "no such file"})


@pytest.fixture
def backend(monkeypatch):
    _Backend.files = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Backend)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("CONNECTONION_BACKEND_URL", f"http://127.0.0.1:{server.server_port}")
    caller = {}
    monkeypatch.setattr("connectonion.credentials.require_ambient_api_key", lambda: caller["address"])
    yield {"files": _Backend.files, "as": lambda keys: caller.update(address=keys["address"])}
    server.shutdown()


@pytest.fixture
def parrot(tmp_path):
    """The receiving agent's project, with one contact: kim."""
    co_dir = tmp_path / "parrot" / ".co"
    keys = address.generate()
    address.save(keys, co_dir)
    kim = address.generate()
    (co_dir / "contacts.txt").write_text(kim["address"] + "\n")
    return {"keys": keys, "co_dir": co_dir, "kim": kim}


def _clip(tmp_path, size=3 * 1024 * 1024):
    clip = tmp_path / "C2350.MP4"
    clip.write_bytes(os.urandom(size))
    return clip


def test_a_file_waits_and_the_receiver_takes_it_byte_for_byte(backend, parrot, tmp_path):
    clip = _clip(tmp_path)
    backend["as"](parrot["kim"])
    left = file_stash.leave(parrot["kim"], parrot["keys"]["address"], clip, "C2350.MP4")
    stored = backend["files"][left["id"]]
    assert clip.read_bytes() not in stored["data"]   # the backend holds a box, not the file
    assert b"C2350" not in stored["meta"].encode()   # nor its name

    backend["as"](parrot["keys"])
    taken = file_stash.collect(parrot["keys"], parrot["co_dir"])
    [entry] = taken["landed"]
    landed = file_inbox.files_dir(parrot["co_dir"]) / entry["path"]
    assert hashlib.sha256(landed.read_bytes()).hexdigest() == hashlib.sha256(clip.read_bytes()).hexdigest()
    assert entry["from"] == parrot["kim"]["address"] and entry["via"] == "backend"
    assert file_inbox.received(parrot["co_dir"]) == [entry]
    assert backend["files"] == {}   # deleted there once taken


def test_a_strangers_file_is_left_waiting_and_named(backend, parrot, tmp_path):
    stranger = address.generate()
    backend["as"](stranger)
    file_stash.leave(stranger, parrot["keys"]["address"], _clip(tmp_path, 10), "x.txt")

    backend["as"](parrot["keys"])
    taken = file_stash.collect(parrot["keys"], parrot["co_dir"])
    assert taken["landed"] == [] and [w["from"] for w in taken["waiting"]] == [stranger["address"]]
    assert file_inbox.received(parrot["co_dir"]) == []
    assert len(backend["files"]) == 1   # kept until the receiver decides, or it expires


def test_a_box_from_someone_other_than_its_sender_is_refused_and_deleted(backend, parrot, tmp_path):
    """The backend says kim sent it; only kim's key could have made the box."""
    forger = address.generate()
    backend["as"](forger)
    left = file_stash.leave(forger, parrot["keys"]["address"], _clip(tmp_path, 10), "x.txt")
    backend["files"][left["id"]]["from_address"] = parrot["kim"]["address"]

    backend["as"](parrot["keys"])
    taken = file_stash.collect(parrot["keys"], parrot["co_dir"])
    assert taken["landed"] == [] and "not boxed by its sender" in taken["refused"][0]["reason"]
    assert backend["files"] == {} and file_inbox.received(parrot["co_dir"]) == []


def test_an_unsafe_name_from_a_contact_is_refused_and_deleted(backend, parrot, tmp_path):
    backend["as"](parrot["kim"])
    file_stash.leave(parrot["kim"], parrot["keys"]["address"], _clip(tmp_path, 10), "../../.bashrc")

    backend["as"](parrot["keys"])
    taken = file_stash.collect(parrot["keys"], parrot["co_dir"])
    assert taken["landed"] == [] and "unsafe file name" in taken["refused"][0]["reason"]
    assert backend["files"] == {}


def _unreachable(monkeypatch, parrot):
    async def not_direct(*args, **kwargs):
        raise file_send.NotDirect("0x… is not reachable directly from here")
    monkeypatch.setattr(file_send, "send_file", not_direct)
    # `connectonion.network.connect` as a dotted path is the function the package re-exports.
    monkeypatch.setattr(sys.modules["connectonion.network.connect"], "_this_callers_identity", lambda: parrot["kim"])


def test_co_send_leaves_a_small_file_waiting_when_the_receiver_is_not_reachable(
        backend, parrot, tmp_path, monkeypatch, capsys):
    _unreachable(monkeypatch, parrot)
    backend["as"](parrot["kim"])
    assert send_commands.handle_send(parrot["keys"]["address"], [str(_clip(tmp_path, 1000))], None) == 0
    out = capsys.readouterr()
    assert "not reachable directly" in out.err
    assert "waiting for the receiver, encrypted to it, for 7 days" in out.out
    assert len(backend["files"]) == 1


def test_co_send_says_a_large_file_cannot_wait(backend, parrot, tmp_path, monkeypatch, capsys):
    _unreachable(monkeypatch, parrot)
    backend["as"](parrot["kim"])
    clip = _clip(tmp_path, file_stash.STASH_BYTES + 1)
    assert send_commands.handle_send(parrot["keys"]["address"], [str(clip)], None) == 1
    assert "only files up to 10.0 MB can wait" in capsys.readouterr().err
    assert backend["files"] == {}
