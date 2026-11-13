"""A co rem command that fails on a file says what failed, and on which file.

2026-11-12: a saved task listed a PNG as a research capture. Reading it as
text raised UnicodeDecodeError, and the CLI printed "Cannot read or write the
selected co rem files", which sent the owner looking for a permission problem.
Fictional files only.
"""

from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import service
from connectonion.rem.config import prepare

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def status_fails(tmp_path, monkeypatch, fail):
    prepare(tmp_path)
    monkeypatch.setattr(service, "status", lambda root, **kwargs: fail(root))
    return CliRunner().invoke(app, ["rem", "--root", str(tmp_path), "status"])


def test_a_file_that_is_not_text_is_named_and_not_called_a_read_or_write_failure(tmp_path, monkeypatch):
    capture = tmp_path / "web" / "fernhill-chart.png"
    capture.parent.mkdir()
    capture.write_bytes(PNG)
    result = status_fails(tmp_path, monkeypatch, lambda root: capture.read_text(encoding="utf-8"))
    assert result.exit_code != 0
    assert "Cannot read or write" not in result.output, result.output
    assert f"{capture} is not UTF-8 text" in result.output, result.output
    assert "position 0" in result.output, result.output


def test_a_decode_failure_without_a_file_still_says_it_was_decoding(tmp_path, monkeypatch):
    result = status_fails(tmp_path, monkeypatch, lambda root: PNG.decode("utf-8"))
    assert "Cannot read or write" not in result.output, result.output
    assert "A co rem file is not UTF-8 text" in result.output, result.output


def test_a_file_that_cannot_be_opened_is_still_a_read_or_write_failure_naming_it(tmp_path, monkeypatch):
    missing = tmp_path / "nowhere" / "fixture.json"
    result = status_fails(tmp_path, monkeypatch, lambda root: missing.read_text(encoding="utf-8"))
    assert "Cannot read or write the selected co rem files" in result.output, result.output
    assert str(missing) in result.output, result.output
