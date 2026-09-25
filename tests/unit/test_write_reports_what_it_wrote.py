"""A write tool's success message is a claim about the disk; hold it to that (#1338).

Unattended `co ai` runs reported `write(...) ✓` three times in one day while
the target file never changed. The agent's only feedback is the tool's return
value, so every path that returns without the requested bytes on disk must come
back as a ToolFailure (✗, trace status "error"), and a real success must say
where it landed and what is there now.
"""

from pathlib import Path
from types import SimpleNamespace

from connectonion.core.tool_result import ToolFailure
from connectonion.useful_tools.diff_writer import MODE_AUTO, MODE_NORMAL, MODE_PLAN, DiffWriter
from connectonion.useful_tools.file_tools import FileTools, write


def _drop_writes(monkeypatch):
    """A write that returns normally but never reaches the file.

    Stands in for everything the run logs could not show: a sync folder
    reverting the file, a filesystem acknowledging and dropping data, another
    process restoring the old copy between our write and our return.
    """
    monkeypatch.setattr(Path, "write_text", lambda self, *a, **k: None)


class FakeIO:
    def __init__(self, responses):
        self.sent = []
        self._responses = list(responses)

    def send(self, event):
        self.sent.append(event)

    def receive(self):
        return self._responses.pop(0) if self._responses else {"type": "io_closed"}


# --- file_tools.write (what co ai uses via FileTools) -----------------------

def test_write_that_never_lands_is_a_failure(tmp_path, monkeypatch):
    path = tmp_path / "digest.html"
    _drop_writes(monkeypatch)

    result = write(str(path), "<div>today</div>")

    assert isinstance(result, ToolFailure)
    assert "Successfully" not in result
    assert not path.exists()


def test_write_that_lands_different_bytes_is_a_failure(tmp_path, monkeypatch):
    path = tmp_path / "drafts.md"
    real_write_text = Path.write_text
    monkeypatch.setattr(
        Path, "write_text", lambda self, data, *a, **k: real_write_text(self, data[:3], *a, **k)
    )

    result = FileTools().write(str(path), "# Needs reply\n")

    assert isinstance(result, ToolFailure)
    assert "does not match" in result


def test_write_success_names_the_resolved_path_and_utf8_size(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    content = "héllo\n"  # 6 characters, 7 UTF-8 bytes

    result = write("notes/today.md", content)

    assert not isinstance(result, ToolFailure)
    resolved = (tmp_path / "notes" / "today.md").resolve()
    assert str(resolved) in result
    assert "7 bytes" in result
    assert resolved.read_text(encoding="utf-8") == content


# --- DiffWriter (approval flow) ---------------------------------------------

def test_diffwriter_write_that_never_lands_is_a_failure(tmp_path, monkeypatch):
    path = tmp_path / "out.txt"
    _drop_writes(monkeypatch)

    result = DiffWriter(mode=MODE_AUTO).write(None, str(path), "new")

    assert isinstance(result, ToolFailure)


def test_diffwriter_success_names_the_resolved_path(tmp_path):
    path = tmp_path / "out.txt"

    result = DiffWriter(mode=MODE_AUTO).write(None, str(path), "new")

    assert not isinstance(result, ToolFailure)
    assert str(path.resolve()) in result
    assert path.read_text(encoding="utf-8") == "new"


def test_diffwriter_rejection_is_a_failure(tmp_path):
    path = tmp_path / "out.txt"
    path.write_text("old", encoding="utf-8")
    io = FakeIO([{"answer": "No, reject and give feedback"}, {"answer": "not now"}])

    result = DiffWriter(mode=MODE_NORMAL).write(SimpleNamespace(io=io), str(path), "new")

    assert isinstance(result, ToolFailure)
    assert "User rejected" in result
    assert path.read_text(encoding="utf-8") == "old"


def test_diffwriter_closed_channel_is_a_failure_not_a_write(tmp_path):
    path = tmp_path / "out.txt"
    path.write_text("old", encoding="utf-8")
    io = FakeIO([])  # the client went away while we waited for approval

    result = DiffWriter(mode=MODE_NORMAL).write(SimpleNamespace(io=io), str(path), "new")

    assert isinstance(result, ToolFailure)
    assert path.read_text(encoding="utf-8") == "old"


def test_diffwriter_plan_mode_preview_is_not_reported_as_a_write(tmp_path):
    path = tmp_path / "out.txt"

    result = DiffWriter(mode=MODE_PLAN).write(None, str(path), "new")

    assert isinstance(result, ToolFailure)
    assert result.startswith("[Plan mode]")
    assert "not written" in result.lower()
    assert not path.exists()


# --- the run log --------------------------------------------------------------

def test_a_failed_write_is_logged_with_its_full_path_and_reason(tmp_path, monkeypatch):
    """The ✗ line truncates the call; the reason must still reach the log."""
    from unittest.mock import patch

    from connectonion.core.llm import ToolCall
    from connectonion.core.tool_executor import execute_and_record_tools
    from connectonion.logger import Logger
    from tests.unit.test_file_tool_failure_results import RecordingAgent, file_tool_registry

    path = tmp_path / "a-long-directory-name-the-call-line-cuts-off" / "digest.html"
    _drop_writes(monkeypatch)

    with patch("connectonion.console._rich_console.print") as terminal_print:
        execute_and_record_tools(
            [ToolCall(name="write", arguments={"content": "<div>", "path": str(path)},
                      id="call-1", extra_content=None)],
            file_tool_registry(FileTools()),
            RecordingAgent(),
            Logger("write-test", log=False),
        )

    terminal_output = "\n".join(str(c.args[0]) for c in terminal_print.call_args_list)
    assert "✗" in terminal_output
    assert "✓" not in terminal_output
    assert str(path.resolve()) in terminal_output
    assert "no file is there" in terminal_output
