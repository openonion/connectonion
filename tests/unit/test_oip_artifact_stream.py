import hashlib
from pathlib import Path

import pytest

from connectonion.cli.browser_agent.artifacts import (
    ArtifactReceiver,
    ArtifactStager,
    ArtifactTransferError,
)
from connectonion.cli.browser_agent import client as browser_client
from connectonion.cli.browser_agent.client import _oip_command
from connectonion.network.oip import browser_daemon_pb2 as wire
from connectonion.network.oip.framing import (
    CHUNK_BYTES,
    ProtocolError,
    decode_frame,
    encode_frame,
)


def _envelope(**kwargs):
    return wire.Envelope(protocol_version=2, request_id="req-1", **kwargs)


def _staged(tmp_path, content: bytes, *, name: str, media_type: str):
    stager = ArtifactStager(tmp_path / "stage")
    source = stager.reserve("req-1", Path(name or "artifact.bin").suffix or ".bin")
    source.write_bytes(content)
    return stager.adopt(source, proposed_name=name, media_type=media_type)


def test_frame_round_trip_uses_one_binary_envelope():
    frame = _envelope(
        sequence=0,
        command=wire.BrowserCommand(argv=["go_to", "https://example.com"]),
    )

    encoded = encode_frame(frame)

    assert encoded[:4] == b"OIP2"
    assert decode_frame(encoded) == frame


def test_frame_rejects_oversized_data_chunk_before_dispatch():
    frame = _envelope(
        stream_id=1,
        stream_data=wire.StreamData(payload=b"x" * (CHUNK_BYTES + 1)),
    )

    with pytest.raises(ProtocolError, match="chunk"):
        encode_frame(frame)


def test_screenshot_output_path_stays_on_the_caller():
    frame, destination = _oip_command(
        "take_screenshot --full-page --out /private/caller/evidence.png",
        caller="caller",
        account="0xaccount",
        tab="research",
        engine="onion",
    )

    assert destination == "/private/caller/evidence.png"
    assert list(frame.command.argv) == ["take_screenshot", "--full-page"]
    assert "/private/caller" not in frame.SerializeToString().decode(errors="ignore")


def test_remote_host_adapter_fails_closed_until_secure_artifact_carrier(monkeypatch):
    monkeypatch.setattr(
        browser_client,
        "_request_with_identity",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("remote screenshot reached the local daemon")
        ),
    )

    code, message = browser_client.request_as(
        "take_screenshot", caller="0xcaller", account="0xaccount"
    )

    assert code == 7
    assert message.startswith("REMOTE_BROWSER_ARTIFACT_STREAM_UNAVAILABLE")


def test_artifact_stream_has_no_one_megabyte_file_limit(tmp_path):
    content = (b"artifact-stream" * 100_000) + b"end"
    staged = _staged(tmp_path, content, name="capture.png", media_type="image/png")
    receiver = ArtifactReceiver(tmp_path / "caller")

    destination = receiver.receive(staged.open_frame(), staged.data_frames(), staged.fin_frame())

    assert destination.read_bytes() == content
    assert destination.stat().st_size > 1024 * 1024
    assert staged.chunk_count > 1


def test_receiver_rejects_wrong_offset_and_removes_partial_file(tmp_path):
    content = b"safe"
    digest = hashlib.sha256(content).digest()
    opened = _envelope(
        stream_id=7,
        stream_open=wire.StreamOpen(
            artifact_id="a7",
            proposed_name="capture.png",
            media_type="image/png",
            expected_size=len(content),
            sha256=digest,
        ),
    )
    bad_data = _envelope(
        stream_id=7,
        sequence=1,
        offset=9,
        stream_data=wire.StreamData(payload=content),
    )
    finished = _envelope(
        stream_id=7,
        sequence=2,
        offset=len(content),
        stream_fin=wire.StreamFin(actual_size=len(content), sha256=digest),
    )

    with pytest.raises(ArtifactTransferError, match="offset"):
        ArtifactReceiver(tmp_path / "caller").receive(opened, [bad_data], finished)

    assert not list((tmp_path / "caller").glob("*.part-*"))


@pytest.mark.parametrize("name", ["../secret", "/tmp/secret", "..\\secret", ""])
def test_receiver_ignores_unsafe_daemon_filenames(tmp_path, name):
    content = b"safe"
    staged = _staged(tmp_path, content, name=name, media_type="image/png")

    destination = ArtifactReceiver(tmp_path / "caller").receive(
        staged.open_frame(), staged.data_frames(), staged.fin_frame()
    )

    assert destination.parent == (tmp_path / "caller")
    assert destination.name.endswith(".png")
    assert ".." not in destination.name


def test_receiver_does_not_overwrite_an_existing_download(tmp_path):
    staged = _staged(
        tmp_path,
        b"new",
        name="report.bin",
        media_type="application/octet-stream",
    )
    destination = tmp_path / "caller" / "report.bin"
    destination.parent.mkdir()
    destination.write_bytes(b"old")

    received = ArtifactReceiver(tmp_path / "caller").receive(
        staged.open_frame(), staged.data_frames(), staged.fin_frame()
    )

    assert destination.read_bytes() == b"old"
    assert received.name == "report-1.bin"
    assert received.read_bytes() == b"new"
