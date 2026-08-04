"""`co deploy` one directory down tells you to break your project.

Deploy resolves the project against the bare cwd:

    project_dir = (project_dir or Path.cwd()).resolve()     # deploy_to_server.py
    project_dir = Path.cwd() if project_dir is None else …  # deploy_commands.py

so from a subdirectory `_read_project` finds no `.co/host.yaml` and says:

    Not a ConnectOnion project. Run 'co init' first.

You are in one. The framework knows it — `load_host_config(None)` from the same
directory returns the project's `trust: strict`, because #661 taught it to walk
up. Only deploy cannot see it.

Following the advice is what makes this a bug rather than a wrong message.
Measured end to end, in a subdirectory of a project configured `trust: strict`:

    co init here
    a decoy .co now exists here : True
    trust now reads             : careful      (was strict)
    _read_project               : name=sub, entrypoint=agent.py

Three things at once. The project's trust is silently downgraded — a whitelist-
only agent now admits contacts and accepts an invite code — because the decoy
`.co` shadows the real one, which is the hazard #663 spent a change removing.
Deploy then reports success against the **subdirectory**, so what ships is the
wrong tree with the wrong name.

The fix is the one the rest of the codebase already made: the project is the
directory that owns `.co/`, found by walking up. Then deploy works from a
subdirectory and nobody is told to plant a decoy.
"""

from pathlib import Path

import pytest


@pytest.fixture
def project(tmp_path):
    co = tmp_path / "project" / ".co"
    co.mkdir(parents=True)
    (co / "host.yaml").write_text("name: realagent\nentrypoint: main.py\ntrust: strict\nport: 8123\n")
    (tmp_path / "project" / "main.py").write_text("# the entrypoint\n")
    (tmp_path / "project" / "sub" / "deeper").mkdir(parents=True)
    return tmp_path / "project"


class TestFromASubdirectory:

    @pytest.mark.parametrize("depth", ["sub", "sub/deeper"])
    def test_the_project_is_found(self, project, monkeypatch, depth):
        from connectonion.cli.commands.deploy_to_server import _read_project

        monkeypatch.chdir(project / depth)

        assert (_read_project(None) or {}).get("name") == "realagent"

    def test_the_entrypoint_comes_with_it(self, project, monkeypatch):
        from connectonion.cli.commands.deploy_to_server import _read_project

        monkeypatch.chdir(project / "sub")

        assert (_read_project(None) or {}).get("entrypoint") == "main.py"

    def test_nobody_is_told_to_run_co_init(self, project, monkeypatch, capsys):
        """The advice that plants a decoy `.co` and downgrades the project."""
        from connectonion.cli.commands.deploy_to_server import _read_project

        monkeypatch.chdir(project / "sub")
        _read_project(None)

        assert "co init" not in capsys.readouterr().out


class TestFromTheProjectRoot:
    """Unchanged."""

    def test_it_still_reads_the_project(self, project, monkeypatch):
        from connectonion.cli.commands.deploy_to_server import _read_project

        monkeypatch.chdir(project)

        assert (_read_project(None) or {}).get("name") == "realagent"


class TestOutsideAnyProject:

    def test_it_still_says_so(self, tmp_path, monkeypatch, capsys):
        from connectonion.cli.commands.deploy_to_server import _read_project

        monkeypatch.chdir(tmp_path)

        assert _read_project(None) is None
        assert "co init" in capsys.readouterr().out


class TestWhatMustNotChange:

    def test_an_explicit_directory_still_wins(self, project, tmp_path, monkeypatch):
        from connectonion.cli.commands.deploy_to_server import _read_project

        other = tmp_path / "other"
        (other / ".co").mkdir(parents=True)
        (other / ".co" / "host.yaml").write_text("name: otheragent\n")
        monkeypatch.chdir(project)

        assert (_read_project(other) or {}).get("name") == "otheragent"
