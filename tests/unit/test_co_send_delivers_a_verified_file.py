"""`co send`: a file reaches another agent's Host whole, or not at all.

The case behind it (#3078): several GB of camera originals from a laptop agent
to an editing agent on an office mini PC. Chat apps recompress video, so the
bytes have to arrive as they left, and a dropped connection must not mean
starting the upload again.

Each test runs a real Host in a subprocess and sends over its real sealed
direct socket.
"""

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from connectonion import address
from connectonion.network import file_send
from connectonion.network.connect import RemoteAgent
from connectonion.network.host import file_inbox

ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def receiver(tmp_path, request):
    """A Host named parrot, with one contact: the sender."""
    trust = getattr(request, "param", "careful")
    project = tmp_path / "parrot"
    co_dir = project / ".co"
    address.save(address.generate(), co_dir)
    sender = address.generate()
    (co_dir / "contacts.txt").write_text(sender["address"] + "\n")
    port = _free_port()
    script = (
        "from pathlib import Path\n"
        "from connectonion import Agent, host\n"
        "host(Agent('parrot', model='co/gemini-3.7-flash', api_key='test-key', quiet=True, log=False),\n"
        f"     port={port}, relay_url=None, trust={trust!r}, co_dir=Path({str(co_dir)!r}))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    process = subprocess.Popen([sys.executable, "-c", script], cwd=project, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            info = httpx.get(f"http://127.0.0.1:{port}/info", timeout=1).json()
            break
        except httpx.HTTPError:
            assert process.poll() is None, process.stderr.read().decode()
            time.sleep(0.2)
    else:
        process.kill()
        pytest.fail("the receiving Host did not come up")
    yield {"address": info["address"], "port": port, "co_dir": co_dir, "sender": sender}
    process.terminate()
    process.wait(timeout=10)


def _remote(receiver, keys):
    remote = RemoteAgent(receiver["address"], keys=keys, relay_url="ws://127.0.0.1:9")
    remote._endpoint_resolved = True
    remote._resolved_endpoint = f"ws://127.0.0.1:{receiver['port']}/ws"
    return remote


def _video(tmp_path, megabytes=12) -> Path:
    clip = tmp_path / "C2350.MP4"
    clip.write_bytes(os.urandom(megabytes * 1024 * 1024))
    return clip


def test_the_file_arrives_byte_for_byte_and_is_listed(receiver, tmp_path):
    clip = _video(tmp_path)

    stored = asyncio.run(file_send.send_file(_remote(receiver, receiver["sender"]), clip, clip.name))

    landed = file_inbox.files_dir(receiver["co_dir"]) / stored["path"]
    assert landed.read_bytes() == clip.read_bytes()
    assert stored["sha256"] == hashlib.sha256(clip.read_bytes()).hexdigest()
    assert [entry["path"] for entry in file_inbox.received(receiver["co_dir"])] == [stored["path"]]
    assert file_inbox.received(receiver["co_dir"])[0]["from"] == receiver["sender"]["address"]


def test_an_interrupted_send_resumes_where_it_stopped(receiver, tmp_path):
    clip = _video(tmp_path, megabytes=24)

    class Unplugged(Exception):
        pass

    def unplug(phase, done, total):
        if phase == "sending" and done >= 8 * 1024 * 1024:
            raise Unplugged()

    with pytest.raises(Unplugged):
        asyncio.run(file_send.send_file(_remote(receiver, receiver["sender"]), clip, clip.name, unplug))
    assert file_inbox.received(receiver["co_dir"]) == []

    resumed_from = []

    def watch(phase, done, total):
        if phase == "sending" and not resumed_from:
            resumed_from.append(done)

    stored = asyncio.run(file_send.send_file(_remote(receiver, receiver["sender"]), clip, clip.name, watch))

    assert resumed_from[0] > 8 * 1024 * 1024
    landed = file_inbox.files_dir(receiver["co_dir"]) / stored["path"]
    assert hashlib.sha256(landed.read_bytes()).hexdigest() == stored["sha256"]
    assert landed.read_bytes() == clip.read_bytes()


def test_a_second_file_with_the_same_name_does_not_overwrite_the_first(receiver, tmp_path):
    first = tmp_path / "a" / "take.mov"
    second = tmp_path / "b" / "take.mov"
    for clip, body in ((first, b"first take"), (second, b"second take")):
        clip.parent.mkdir()
        clip.write_bytes(body)
    remote = _remote(receiver, receiver["sender"])

    one = asyncio.run(file_send.send_file(remote, first, "take.mov"))
    two = asyncio.run(file_send.send_file(remote, second, "take.mov"))

    root = file_inbox.files_dir(receiver["co_dir"])
    assert one["path"] != two["path"]
    assert (root / one["path"]).read_bytes() == b"first take"
    assert (root / two["path"]).read_bytes() == b"second take"


def _nothing_staged(receiver):
    return not any(file_inbox.files_dir(receiver["co_dir"]).rglob("*.part"))


def test_a_stranger_cannot_send(receiver, tmp_path):
    clip = _video(tmp_path, megabytes=1)

    with pytest.raises(file_send.SendRefused, match="onboarding"):
        asyncio.run(file_send.send_file(_remote(receiver, address.generate()), clip, clip.name))
    assert _nothing_staged(receiver)


@pytest.mark.parametrize("receiver", ["open"], indirect=True)
def test_an_open_host_still_takes_files_only_from_contacts(receiver, tmp_path):
    """`trust: open` lets anyone talk to the agent; it does not let them fill its disk."""
    clip = _video(tmp_path, megabytes=1)

    with pytest.raises(file_send.SendRefused, match="contact or admin"):
        asyncio.run(file_send.send_file(_remote(receiver, address.generate()), clip, clip.name))
    assert _nothing_staged(receiver)


def test_an_empty_file_arrives_too(receiver, tmp_path):
    empty = tmp_path / "notes.txt"
    empty.write_bytes(b"")

    stored = asyncio.run(file_send.send_file(_remote(receiver, receiver["sender"]), empty, empty.name))

    assert (file_inbox.files_dir(receiver["co_dir"]) / stored["path"]).read_bytes() == b""


@pytest.mark.parametrize("name", ["../escape.mov", "/etc/passwd", "a//b", "a/./b", "", "x\x00y"])
def test_a_name_cannot_leave_the_inbox(name):
    with pytest.raises(file_inbox.FileRefused):
        file_inbox.safe_name(name)


def test_a_folder_keeps_its_shape():
    assert file_inbox.safe_name("footage/day1/C2350.MP4") == "footage/day1/C2350.MP4"


def test_bytes_that_do_not_match_the_offer_are_not_kept(tmp_path):
    root = file_inbox.files_dir(tmp_path)
    receiver = file_inbox.FileReceiver(root, "0xsender")
    receiver.accept({"sha256": "0" * 64, "size": 5, "name": "x.bin"})

    with pytest.raises(file_inbox.FileRefused, match="does not match"):
        receiver.write({"sha256": "0" * 64, "offset": 0, "data": "aGVsbG8=",
                        "chunk_sha256": hashlib.sha256(b"hello").hexdigest()})
    assert list(root.rglob("x.bin")) == []
    assert list(root.rglob("*.part")) == []
    assert file_inbox.received(tmp_path) == []


def test_a_chunk_swapped_after_signing_is_refused(tmp_path):
    """The signature covers the chunk's digest; other bytes beside it do not pass."""
    receiver = file_inbox.FileReceiver(file_inbox.files_dir(tmp_path), "0xsender")
    receiver.accept({"sha256": hashlib.sha256(b"hello").hexdigest(), "size": 5, "name": "x.bin"})

    with pytest.raises(file_inbox.FileRefused, match="signed sha256"):
        receiver.write({"sha256": hashlib.sha256(b"hello").hexdigest(), "offset": 0,
                        "data": "d29ybGQ=", "chunk_sha256": hashlib.sha256(b"hello").hexdigest()})
    assert receiver.received == 0


def test_stopping_a_send_stops_it_rather_than_retrying(receiver, tmp_path):
    """Ctrl-C is the person deciding, not the network failing.

    Measured on the first real 5 GB run: the interrupted send swallowed the
    cancellation as a dropped connection, retried, and reported the receiver as
    unreachable.
    """
    clip = _video(tmp_path, megabytes=24)

    async def stop_midway():
        started = asyncio.Event()

        def watch(phase, done, total):
            if phase == "sending":
                started.set()

        task = asyncio.create_task(
            file_send.send_file(_remote(receiver, receiver["sender"]), clip, clip.name, watch))
        await started.wait()
        task.cancel()
        began = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await task
        return time.monotonic() - began

    assert asyncio.run(stop_midway()) < 1


def test_a_second_send_of_the_same_file_takes_over_from_the_first(receiver, tmp_path):
    """A resumed send can start while the old one is still half alive.

    On the first real 5 GB run a stop signal did not reach the first `co send`,
    and the resumed one ran beside it: two sockets appending to one staging
    file. Only one may write; the newest offer wins and the other is told.
    """
    clip = _video(tmp_path, megabytes=24)

    async def overlap():
        started = asyncio.Event()

        def watch(phase, done, total):
            if phase == "sending" and done >= 4 * 1024 * 1024:
                started.set()

        first = asyncio.create_task(
            file_send.send_file(_remote(receiver, receiver["sender"]), clip, clip.name, watch))
        await started.wait()
        second = await file_send.send_file(_remote(receiver, receiver["sender"]), clip, clip.name)
        with pytest.raises(file_send.SendRefused, match="took over"):
            await first
        return second

    stored = asyncio.run(overlap())

    landed = file_inbox.files_dir(receiver["co_dir"]) / stored["path"]
    assert landed.read_bytes() == clip.read_bytes()
    assert len(file_inbox.received(receiver["co_dir"])) == 1
