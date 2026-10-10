"""#2114: co ai's bash tool ran whichever `co` came first on PATH (a 1.8.8
pyenv shim), so the agent read the help of a version without `co linear`
and fell back to the browser. The shell must run the co that is running."""

import os
import subprocess
import sys

import pytest

from connectonion.cli.commands import ai_commands


def script(directory, name, text):
    path = directory / name
    path.write_text(f"#!/bin/sh\necho {text}\n")
    path.chmod(0o755)


@pytest.mark.skipif(sys.platform == "win32", reason="the bash tool is Unix-only")
def test_the_agents_shell_runs_this_installs_co_and_nothing_else_of_it(tmp_path, monkeypatch):
    old, running = tmp_path / "old-bin", tmp_path / "running-bin"
    old.mkdir(), running.mkdir()
    script(old, "co", "co-1.8.8")
    script(old, "python", "users-python")
    script(running, "co", "co-running")
    script(running, "python", "co-venv-python")
    monkeypatch.setenv("PATH", os.pathsep.join([str(old), "/usr/bin", "/bin"]))
    monkeypatch.setattr(sys, "executable", str(running / "python"))

    ai_commands._this_co_first()

    shell = subprocess.run("co; python", shell=True, executable="/bin/bash",
                           capture_output=True, text=True).stdout.split()
    assert shell == ["co-running", "users-python"]
