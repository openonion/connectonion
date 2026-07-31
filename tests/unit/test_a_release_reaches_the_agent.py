"""A released fix reaches a deployed agent on the next deploy.

`connectonion` in requirements.txt is an unpinned line that never changes, so
the hash that decides whether to install never changed either — and a server
kept whatever version it was first deployed with, forever. 1.5.6 shipped the fix
for every agent calling itself `oo`, and redeploying from a 1.5.6 laptop left
1.5.5 running on the box. openonion/connectonion#460
"""

import hashlib
import subprocess
from unittest.mock import patch

import pytest

from connectonion import __version__
from connectonion.cli.commands import deploy_to_server as dts


def _ok(stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


@pytest.fixture
def project(tmp_path):
    (tmp_path / "requirements.txt").write_text("connectonion\n")
    return tmp_path


def _stamp_for(project, version):
    return hashlib.sha256(
        (project / "requirements.txt").read_bytes() + b"\ncli:" + version.encode()
    ).hexdigest()


class TestUpgradingTheCliShipsTheFix:
    def test_a_newer_cli_reinstalls_even_though_the_file_is_identical(self, project):
        """The whole bug: an unpinned line has an unchanging hash."""
        stale = _stamp_for(project, "1.5.5")

        with patch.object(dts, "_ssh", return_value=_ok(stale)) as ssh:
            dts._install_deps_if_changed("user@host", "myagent", project)

        assert any("pip install" in c.args[1] for c in ssh.call_args_list), \
            "skipped the install, so the release never reaches the server"

    def test_the_same_cli_still_skips(self, project):
        """A code-only change must still take seconds, not minutes."""
        current = _stamp_for(project, __version__)

        with patch.object(dts, "_ssh", return_value=_ok(current)) as ssh:
            dts._install_deps_if_changed("user@host", "myagent", project)

        assert not any("pip install" in c.args[1] for c in ssh.call_args_list)

    def test_the_stamp_written_back_carries_the_version(self, project):
        with patch.object(dts, "_ssh", return_value=_ok("stale")) as ssh:
            dts._install_deps_if_changed("user@host", "myagent", project)

        install = next(c.args[1] for c in ssh.call_args_list if "pip install" in c.args[1])
        assert _stamp_for(project, __version__) in install


class TestTheReinstallActuallyUpgrades:
    def test_pip_is_told_to_upgrade(self, project):
        """Measured against a real venv: one on 1.5.4 with `connectonion`
        unpinned stayed on 1.5.4 through `pip install -r`, and moved only with
        -U. Without it the reinstall changes nothing."""
        with patch.object(dts, "_ssh", return_value=_ok("stale")) as ssh:
            dts._install_deps_if_changed("user@host", "myagent", project)

        install = next(c.args[1] for c in ssh.call_args_list if "pip install" in c.args[1])
        assert " -U " in install or install.endswith(" -U")

    def test_it_still_runs_from_the_project_directory(self, project):
        """A requirements.txt may name a local wheel or `-e .` (#377)."""
        with patch.object(dts, "_ssh", return_value=_ok("stale")) as ssh:
            dts._install_deps_if_changed("user@host", "myagent", project)

        install = next(c.args[1] for c in ssh.call_args_list if "pip install" in c.args[1])
        assert f"cd {dts.SRV}/myagent" in install
