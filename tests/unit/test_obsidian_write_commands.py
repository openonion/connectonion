"""The two write commands through the public CLI, with synthetic notes only."""

import json
import os
import shlex

import pytest
from typer.testing import CliRunner

from tests.unit.test_obsidian import isolated_home  # noqa: F401


POSIX_WRITE = pytest.mark.skipif(os.open not in os.supports_dir_fd, reason="POSIX publication required")


@pytest.fixture
def write_cli(tmp_path, isolated_home, monkeypatch):
    from connectonion.cli.main import app
    monkeypatch.setenv("COLUMNS", "240")
    vault = tmp_path / "Selected" / "Synthetic vault"
    (vault / "Course").mkdir(parents=True)
    (vault / "Course/A.md").write_text("Original\n")
    runner = CliRunner()
    def invoke(operation, path, content="Added", extra=(), input=None):
        return runner.invoke(app, ["obsidian", operation, path, "--vault", str(vault),
                                   "--folder", "Course", "--content", content, *extra], input=input)
    return vault, invoke, runner, app


@pytest.mark.parametrize("operation,path", [("create", "Course/New.md"), ("append", "Course/A.md")])
@POSIX_WRITE
def test_preview_json_and_copyable_next(write_cli, operation, path):
    vault, invoke, runner, app = write_cli
    target = vault / path
    before = target.read_bytes() if target.exists() else b""
    result = invoke(operation, path, extra=["--json"])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.stdout)
    assert preview["preview"] is True
    assert preview["content"] == "Added"
    assert (target.read_bytes() if target.exists() else b"") == before
    next_line = next(line for line in result.stderr.splitlines() if line.startswith("Next: "))
    args = shlex.split(next_line.removeprefix("Next: "))
    assert args[:3] == ["co", "obsidian", operation]
    applied = runner.invoke(app, args[1:])
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.stdout)["preview"] is False
    assert target.read_bytes() == before + b"Added"


@pytest.mark.parametrize("operation", ["create", "append"])
def test_yes_alone_is_refused_before_stdin_or_registry(write_cli, operation, monkeypatch):
    from connectonion.useful_tools import obsidian
    monkeypatch.setattr(obsidian, "_registry_path", lambda: pytest.fail("must fail before discovery"))
    _, _, runner, app = write_cli
    result = runner.invoke(app, ["obsidian", operation, "Course/New.md", "--folder", "Course",
                                 "--content", "-", "--yes"])
    assert result.exit_code == 2
    assert "--expect" in result.stderr
    assert not result.stdout.strip()


@POSIX_WRITE
def test_stdin_replay_requires_identical_bytes(write_cli):
    vault, invoke, _, _ = write_cli
    content = "# 新笔记\r\nSecond line\n"
    result = invoke("create", "Course/New.md", "-", ["--json"], input=content)
    assert result.exit_code == 0, result.output
    token = json.loads(result.stdout)["expect"]
    assert "Pipe the same" in result.stderr
    refused = invoke("create", "Course/New.md", "-", ["--yes", "--expect", token], input="different")
    assert refused.exit_code == 1
    assert not (vault / "Course/New.md").exists()
    applied = invoke("create", "Course/New.md", "-", ["--yes", "--expect", token], input=content)
    assert applied.exit_code == 0, applied.output
    assert (vault / "Course/New.md").read_bytes() == content.encode()


@POSIX_WRITE
def test_append_row_can_preview_but_confirmation_uses_path(write_cli):
    vault, _, runner, app = write_cli
    listed = runner.invoke(app, ["obsidian", "ls", "--vault", str(vault), "--folder", "Course"])
    assert listed.exit_code == 0, listed.output
    result = runner.invoke(app, ["obsidian", "append", "1", "--content", "Added", "--json"])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.stdout)
    assert preview["path"] == "Course/A.md"
    refused = runner.invoke(app, ["obsidian", "append", "1", "--content", "Added", "--yes",
                                  "--expect", preview["expect"]])
    assert refused.exit_code == 2
    assert (vault / "Course/A.md").read_text() == "Original\n"
    next_line = next(line for line in result.stderr.splitlines() if line.startswith("Next: "))
    args = shlex.split(next_line.removeprefix("Next: "))
    assert args[3] == "Course/A.md"
    applied = runner.invoke(app, args[1:])
    assert applied.exit_code == 0, applied.output
    assert (vault / "Course/A.md").read_text() == "Original\nAdded"


@pytest.mark.skipif(os.name == "nt", reason="symlinks require privileges on Windows")
@pytest.mark.parametrize("operation", ["create", "append"])
def test_write_preview_rejects_a_vault_redirect_after_selection(write_cli, tmp_path, monkeypatch, operation):
    from connectonion.cli.commands import obsidian_commands as commands
    from connectonion.useful_tools import obsidian

    vault, invoke, runner, app = write_cli
    alternate = tmp_path / "Alternate" / vault.name / "Course"
    alternate.mkdir(parents=True)
    (alternate / "A.md").write_text("Unselected note\n")
    if operation == "append":
        listed = runner.invoke(app, ["obsidian", "ls", "--vault", str(vault), "--folder", "Course"])
        assert listed.exit_code == 0, listed.output
    hook = "_select_note" if operation == "append" else "_selection"
    select = getattr(commands, hook)

    def redirect_after_selection(*args, **kwargs):
        selection = select(*args, **kwargs)
        vault.parent.rename(tmp_path / "Retained")
        vault.parent.symlink_to(alternate.parent.parent, target_is_directory=True)
        return selection

    monkeypatch.setattr(commands, hook, redirect_after_selection)
    monkeypatch.setattr(obsidian, "_read_markdown", lambda *args: pytest.fail("preview must not read a redirected vault"))
    if operation == "append":
        result = runner.invoke(app, ["obsidian", "append", "1", "--content", "Added", "--json"])
    else:
        result = invoke("create", "Course/New.md", extra=["--json"])

    assert result.exit_code == 2, result.output
    assert "parent directory changed" in result.stderr
    assert not result.stdout.strip()


def test_stale_confirmation_has_recovery_and_no_success_stdout(write_cli):
    vault, invoke, _, _ = write_cli
    preview = json.loads(invoke("append", "Course/A.md", extra=["--json"]).stdout)
    (vault / "Course/A.md").write_text("User edit\n")
    result = invoke("append", "Course/A.md", extra=["--yes", "--expect", preview["expect"], "--json"])
    assert result.exit_code == 1
    assert not result.stdout.strip()
    assert "preview" in result.stderr
    assert "Next: co obsidian append --help" in result.stderr
    assert (vault / "Course/A.md").read_text() == "User edit\n"


@POSIX_WRITE
def test_content_is_a_literal_shell_argument_in_next(write_cli):
    _, invoke, runner, app = write_cli
    content = "[red]Literal[/red] 'quote' $(echo nope) `echo nope`"
    preview = invoke("create", "Course/New.md", content)
    assert preview.exit_code == 0, preview.output
    assert "[red]Literal[/red]" in preview.stdout
    next_line = next(line for line in preview.stdout.splitlines() if line.startswith("Next: "))
    args = shlex.split(next_line.removeprefix("Next: "))
    assert "--content=" + content in args
    applied = runner.invoke(app, args[1:])
    assert applied.exit_code == 0, applied.output


@pytest.mark.parametrize("operation", ["create", "append"])
def test_expect_without_yes_is_usage_error(write_cli, operation):
    _, invoke, _, _ = write_cli
    result = invoke(operation, "Course/A.md", extra=["--expect", "0" * 64])
    assert result.exit_code == 2
    assert not result.stdout.strip()


@POSIX_WRITE
@pytest.mark.parametrize("folder,path", [(".", "./-draft.md"), ("./-course", "./-course/A.md")])
def test_leading_dash_paths_have_replayable_confirm_and_read(write_cli, folder, path):
    vault, _, runner, app = write_cli
    (vault / "-course").mkdir()
    for operation in ("create", "append"):
        preview = runner.invoke(app, ["obsidian", operation, path, "--vault", str(vault),
                                      "--folder", folder, "--content", "text", "--json"])
        assert preview.exit_code == 0, preview.output
        next_line = next(line for line in preview.stderr.splitlines() if line.startswith("Next: "))
        applied = runner.invoke(app, shlex.split(next_line.removeprefix("Next: "))[1:])
        assert applied.exit_code == 0, applied.output
        read_line = next(line for line in applied.stderr.splitlines() if line.startswith("Next: "))
        read = runner.invoke(app, shlex.split(read_line.removeprefix("Next: "))[1:])
        assert read.exit_code == 0, read.output
        assert "text" in read.stdout
