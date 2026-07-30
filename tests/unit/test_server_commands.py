"""Unit tests for `co server` — register, list and preflight a deploy target.

The requirement checks are tested by feeding the probe output a box would return
if it were missing each requirement in turn. That is the point of the command:
"it doesn't work on my box" is only answerable if the failure is named.
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

from connectonion.cli.commands import server_commands as sc


@pytest.fixture
def servers_file(tmp_path, monkeypatch):
    """Point the registry at a temp file so tests never touch ~/.co."""
    path = tmp_path / "servers.yaml"
    monkeypatch.setattr(sc, "SERVERS_FILE", path)
    return path


def _probe(**overrides) -> str:
    """Build probe stdout for a box that meets every requirement, minus overrides."""
    facts = {
        "distro": "ubuntu",
        "version": "24.04",
        "python": "3.12",
        "systemd": "yes",
        "systemctl": "yes",
        "sudo": "yes",
        "diskgb": "40",
    }
    facts.update(overrides)
    return "\n".join(f"{k}={v}" for k, v in facts.items())


def _ok(stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr):
    return subprocess.CompletedProcess(args=[], returncode=255, stdout="", stderr=stderr)


class TestRequirementFailuresAreNamed:
    """Each requirement, missing in turn, must be reported by name."""

    def test_a_box_meeting_everything_has_no_failures(self):
        assert sc._requirement_failures(sc._parse_probe(_probe())) == []

    def test_wrong_distro(self):
        failures = sc._requirement_failures(sc._parse_probe(_probe(distro="debian")))
        assert failures and failures[0][0] == "Ubuntu"
        assert "debian" in failures[0][1]

    def test_wrong_ubuntu_version(self):
        failures = sc._requirement_failures(sc._parse_probe(_probe(version="22.04")))
        assert failures and failures[0][0] == "Ubuntu 24.04"
        assert "22.04" in failures[0][1]

    def test_python_missing_entirely(self):
        failures = sc._requirement_failures(sc._parse_probe(_probe(python="")))
        assert ("python3", "not on PATH") in failures

    def test_python_too_old(self):
        failures = sc._requirement_failures(sc._parse_probe(_probe(python="3.10")))
        names = [name for name, _ in failures]
        assert "python 3.11+" in names

    def test_systemd_absent(self):
        failures = sc._requirement_failures(sc._parse_probe(_probe(systemd="", systemctl="")))
        assert ("systemd", "not present") in failures

    def test_systemd_present_but_units_not_manageable(self):
        """systemd existing is not the same as being allowed to manage a unit."""
        failures = sc._requirement_failures(sc._parse_probe(_probe(sudo="")))
        names = [name for name, _ in failures]
        assert "permission to manage units" in names
        assert "systemd" not in names  # systemd itself is fine, don't muddy the report

    def test_disk_too_small(self):
        failures = sc._requirement_failures(sc._parse_probe(_probe(diskgb="2")))
        names = [name for name, _ in failures]
        assert "5 GB free disk" in names

    def test_df_unreadable(self):
        failures = sc._requirement_failures(sc._parse_probe(_probe(diskgb="")))
        assert ("free disk", "could not read df") in failures

    def test_several_missing_requirements_are_all_reported(self):
        failures = sc._requirement_failures(
            sc._parse_probe(_probe(distro="alpine", python="3.9", diskgb="1"))
        )
        assert len(failures) >= 3


class TestServerAdd:
    def test_unreachable_host_saves_nothing(self, servers_file):
        """An unreachable host must fail with ssh's own words, and save nothing."""
        with patch.object(sc, "_ssh", return_value=_fail("ssh: Could not resolve hostname nope")):
            assert sc.handle_server_add("prod", "user@nope") is False

        assert not servers_file.exists()

    def test_reachable_host_is_recorded(self, servers_file):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            assert sc.handle_server_add("prod", "user@1.2.3.4") is True

        saved = yaml.safe_load(servers_file.read_text())
        assert saved["servers"]["prod"]["ssh"] == "user@1.2.3.4"
        assert saved["servers"]["prod"]["last_check"] is None

    def test_nothing_secret_is_written(self, servers_file):
        """The file holds a target, never a credential."""
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        text = servers_file.read_text().lower()
        for forbidden in ("private", "begin openssh", "password", "secret", "token", "key"):
            assert forbidden not in text

    def test_readding_the_same_name_updates_the_target(self, servers_file):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@old")
            sc.handle_server_add("prod", "user@new")

        saved = yaml.safe_load(servers_file.read_text())
        assert saved["servers"]["prod"]["ssh"] == "user@new"

    def test_ssh_is_called_in_batch_mode_so_it_cannot_hang_on_a_prompt(self, servers_file):
        with patch.object(sc.subprocess, "run", return_value=_ok("ok")) as run:
            sc.handle_server_add("prod", "user@1.2.3.4")

        argv = run.call_args.args[0]
        assert "BatchMode=yes" in argv
        assert any(a.startswith("ConnectTimeout=") for a in argv)


class TestServerCheck:
    def test_unknown_name_is_rejected(self, servers_file):
        assert sc.handle_server_check("nope") is False

    def test_a_ready_box_passes_and_is_recorded(self, servers_file):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")
        with patch.object(sc, "_ssh", return_value=_ok(_probe())):
            assert sc.handle_server_check("prod") is True

        saved = yaml.safe_load(servers_file.read_text())
        assert saved["servers"]["prod"]["last_check"] == "ok"

    def test_a_failing_box_records_the_failing_requirement(self, servers_file):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")
        with patch.object(sc, "_ssh", return_value=_ok(_probe(version="22.04"))):
            assert sc.handle_server_check("prod") is False

        saved = yaml.safe_load(servers_file.read_text())
        assert saved["servers"]["prod"]["last_check"] == "Ubuntu 24.04"

    def test_an_unreachable_box_records_unreachable(self, servers_file):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")
        with patch.object(sc, "_ssh", return_value=_fail("Connection refused")):
            assert sc.handle_server_check("prod") is False

        saved = yaml.safe_load(servers_file.read_text())
        assert saved["servers"]["prod"]["last_check"] == "unreachable"


class TestServerList:
    def test_empty_registry_is_not_an_error(self, servers_file):
        assert sc.handle_server_list() is True

    def test_lists_registered_servers(self, servers_file, capsys):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")
            sc.handle_server_add("staging", "user@5.6.7.8")

        sc.handle_server_list()
        out = capsys.readouterr().out
        assert "prod" in out and "staging" in out
        assert "1.2.3.4" in out


class TestLoadServer:
    def test_returns_none_for_unknown(self, servers_file):
        assert sc.load_server("nope") is None

    def test_returns_the_entry_deploy_will_use(self, servers_file):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        assert sc.load_server("prod")["ssh"] == "user@1.2.3.4"
