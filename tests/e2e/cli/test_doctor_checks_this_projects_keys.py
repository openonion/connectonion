"""`co doctor` puts a green tick beside the wrong key file.

The check resolves the project's key against the bare cwd:

    local_keys = Path(".co") / "keys" / "agent.key"
    global_keys = Path.home() / ".co" / "keys" / "agent.key"
    if local_keys.exists(): ... else global_keys ...

so one directory down the project's own key is invisible and the machine's is
reported in its place. Diffing the whole `co doctor` output between a project
root and a subdirectory of it, on a project that has its own keypair:

    project      Keys ✓ .co/keys/agent.key
    project/sub  Keys ✓ <home>/.co/keys/agent.key

One line differs, and it is the one that says which identity this project uses.
Both carry a green tick.

Same shape as `co keys` (#680), and the same correction to #665: I wrote there
that these commands "fail in the visible direction — the command says it found
nothing". `co doctor` does not fail. It reports success against the wrong file.

## Why this runs the real command

The first version of this test called `handle_doctor()` in-process and passed
while the bug was present: rich renders the table to the terminal width, and at
pytest's default the path was truncated away entirely, leaving `Keys ✓` with
nothing to assert against. The row only carries its path at a width that shows
it. So this drives the CLI in a subprocess with `COLUMNS` set, which is how the
bug was measured in the first place.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def project_with_its_own_key(tmp_path):
    from connectonion import address

    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    address.save(address.generate(), home / ".co")

    project = tmp_path / "project"
    (project / ".co").mkdir(parents=True)
    own = address.generate()
    address.save(own, project / ".co")
    (project / "sub" / "deeper").mkdir(parents=True)
    return project, home, own


def _doctor(cwd: Path, home: Path) -> str:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["COLUMNS"] = "200"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3]) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-m", "connectonion.cli.main", "doctor"],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=300,
    )
    return result.stdout


def _keys_row(output: str) -> str:
    return next((l for l in output.splitlines() if "Keys" in l), "")


class TestFromASubdirectory:

    @pytest.mark.parametrize("depth", ["sub", "sub/deeper"])
    def test_it_does_not_report_the_machine_key(self, project_with_its_own_key, depth):
        project, home, _ = project_with_its_own_key

        row = _keys_row(_doctor(project / depth, home))

        assert str(home) not in row, f"doctor reported the machine's key: {row.strip()}"

    def test_it_reports_a_key_at_all(self, project_with_its_own_key):
        """A tick against nothing would pass the test above and help nobody."""
        project, home, _ = project_with_its_own_key

        assert "agent.key" in _keys_row(_doctor(project / "sub", home))


class TestFromTheProjectRoot:
    """Unchanged — this already worked."""

    def test_it_reports_the_projects_key(self, project_with_its_own_key):
        project, home, _ = project_with_its_own_key

        row = _keys_row(_doctor(project, home))

        assert "agent.key" in row and str(home) not in row


class TestTheGlobalFallbackStays:
    """A project with no key of its own is what `co init` usually produces."""

    def test_a_keyless_project_reports_the_machine_key(self, tmp_path):
        from connectonion import address

        home = tmp_path / "home2"
        (home / ".co").mkdir(parents=True)
        address.save(address.generate(), home / ".co")

        keyless = tmp_path / "keyless"
        (keyless / ".co").mkdir(parents=True)
        (keyless / "sub").mkdir()

        assert "agent.key" in _keys_row(_doctor(keyless / "sub", home))
