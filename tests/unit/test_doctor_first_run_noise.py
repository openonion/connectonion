"""`co doctor` on a first run says what is true about this machine, once.

Four findings from a 1.8.8b7 first-run test:

1. It ended "Run 'co auth' if you need to authenticate" directly under its
   own "Authentication ✓ Valid credentials".
2. Its skill rows said permissions "are not auto-approved by ConnectOnion
   1.6.9" — a version string frozen into the message three minors ago.
3. A machine with ~40 Claude Code skills that declare `allowed-tools` got ~40
   identical rows, burying everything else in the Skills panel.
4. `co` on PATH was ~/.local/bin/co at 1.8.8b3 while the package diagnosed was
   1.8.8b8, and nothing said so — so every `co` the user typed ran other code.
"""

import io
from pathlib import Path
from unittest.mock import Mock

import pytest
from rich.console import Console

from connectonion import address
from connectonion.cli.commands import doctor_commands


@pytest.fixture
def out(monkeypatch):
    buffer = io.StringIO()
    monkeypatch.setattr(doctor_commands, "console", Console(file=buffer, width=240, color_system=None))
    monkeypatch.setattr(doctor_commands, "_path_co_version", lambda path: None, raising=False)
    return buffer


def _run():
    doctor_commands.handle_doctor()


def test_an_authenticated_machine_is_not_told_to_authenticate(out, monkeypatch, tmp_path):
    address.save(address.generate(), Path.home() / ".co")
    monkeypatch.setenv("OPENONION_API_KEY", "a-token")
    monkeypatch.chdir(tmp_path)
    ok = Mock(status_code=200)
    monkeypatch.setattr(doctor_commands.requests, "get", lambda *a, **k: ok)
    monkeypatch.setattr(doctor_commands.requests, "post", lambda *a, **k: ok)

    _run()

    text = out.getvalue()
    assert "Valid credentials" in text
    assert "Run 'co auth'" not in text


def test_an_unauthenticated_machine_still_is(out, monkeypatch, tmp_path):
    monkeypatch.delenv("OPENONION_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    _run()

    assert "co auth" in out.getvalue()


def _claude_skills(count):
    root = Path.home() / ".claude" / "skills"
    for i in range(count):
        (root / f"s{i}").mkdir(parents=True)
        (root / f"s{i}" / "SKILL.md").write_text(
            f"---\nname: s{i}\ndescription: skill {i}\nallowed-tools: Read, Edit\n---\nDo it.\n")


def test_many_skills_with_one_finding_are_one_row(out, monkeypatch, tmp_path):
    monkeypatch.delenv("OPENONION_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    _claude_skills(12)

    _run()

    text = out.getvalue()
    # Panel rows only; the verdict below the panels names the finding once more.
    rows = [line for line in text.splitlines() if "allowed-tools" in line and line.startswith("│")]
    assert len(rows) == 1, "\n".join(rows)
    assert "12" in rows[0]


def test_no_frozen_version_in_the_skill_text(out, monkeypatch, tmp_path):
    monkeypatch.delenv("OPENONION_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    _claude_skills(1)

    _run()

    assert "1.6.9" not in out.getvalue()


def test_a_co_on_path_from_another_version_is_named(out, monkeypatch, tmp_path):
    from connectonion import __version__

    monkeypatch.delenv("OPENONION_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(doctor_commands.shutil, "which", lambda name: "/home/u/.local/bin/co")
    monkeypatch.setattr(doctor_commands, "_path_co_version", lambda path: "1.8.8b3")

    _run()

    text = out.getvalue()
    assert "1.8.8b3" in text and __version__ in text
    assert "/home/u/.local/bin/co" in text


def test_the_version_is_read_from_the_co_on_path(monkeypatch):
    """The helper the check relies on, with the subprocess faked."""
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Mock(returncode=0, stdout="co 1.8.8b3\n"))
    assert doctor_commands._path_co_version("/x/co") == "1.8.8b3"

    def missing(*a, **k):
        raise FileNotFoundError("/x/co")

    monkeypatch.setattr(subprocess, "run", missing)
    assert doctor_commands._path_co_version("/x/co") is None
