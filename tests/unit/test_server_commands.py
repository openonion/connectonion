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


class TestServerSSH:
    def test_unknown_name_is_rejected(self, servers_file):
        assert sc.handle_server_ssh("nope") is False

    def test_opens_a_shell_on_the_registered_target(self, servers_file):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        with patch.object(sc.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0)) as run:
            assert sc.handle_server_ssh("prod") is True

        argv = run.call_args.args[0]
        assert argv[0] == "ssh"
        assert argv[-1] == "user@1.2.3.4"

    def test_runs_one_command_when_given_one(self, servers_file):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        with patch.object(sc.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0)) as run:
            sc.handle_server_ssh("prod", command="uptime")

        assert run.call_args.args[0][-1] == "uptime"

    def test_does_not_capture_output(self, servers_file):
        """An interactive shell needs the terminal.

        Capturing would hang with no prompt visible, which reads as the command
        being broken rather than waiting.
        """
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        with patch.object(sc.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0)) as run:
            sc.handle_server_ssh("prod")

        assert "capture_output" not in run.call_args.kwargs


class TestServerForget:
    def test_unknown_name_is_rejected(self, servers_file):
        assert sc.handle_server_forget("nope") is False

    def test_removes_only_the_named_entry(self, servers_file):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")
            sc.handle_server_add("staging", "user@5.6.7.8")

        assert sc.handle_server_forget("prod") is True

        remaining = yaml.safe_load(servers_file.read_text())["servers"]
        assert "prod" not in remaining
        assert "staging" in remaining

    def test_never_contacts_the_machine(self, servers_file):
        """forget is local-only. Touching the host would blur it into destroy.

        This is the guard that keeps the two commands honest: if forget ever
        starts reaching out, the difference between 'stop tracking it' and
        'stop paying for it' has been lost.
        """
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        with patch.object(sc, "_ssh") as ssh, \
             patch.object(sc.subprocess, "run") as run:
            sc.handle_server_forget("prod")

        ssh.assert_not_called()
        run.assert_not_called()

    def test_says_the_machine_keeps_billing(self, servers_file, capsys):
        """The warning is the whole safety story — assert it is actually printed."""
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        sc.handle_server_forget("prod")
        out = capsys.readouterr().out.lower()
        assert "untouched" in out
        assert "billed" in out


PRICING = {
    "term_months": 12,
    "region": "asia-southeast1",
    "default": "e2-small",
    "machine_types": {"e2-small": {"usd_12mo": 180.0, "description": "2 vCPU, 2 GB"}},
}


class TestServerNewSpendsNothingWithoutConsent:
    """This is the first co command that spends a large discrete amount.

    Every guard below is about that: nothing may be charged before the operator
    has seen the price and said yes.
    """

    def test_declining_the_prompt_creates_nothing(self, servers_file):
        with patch.object(sc, "load_api_key", create=True), \
             patch.object(sc, "_derive_ssh_public_line", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing", return_value=PRICING), \
             patch.object(sc, "_fetch_balance", return_value=500.0), \
             patch.object(sc, "_confirm", return_value=False), \
             patch("requests.post") as post:
            assert sc.handle_server_new("prod") is False

        post.assert_not_called()
        assert not servers_file.exists()

    def test_no_api_key_stops_before_the_prompt(self, servers_file):
        """Do not show a price to someone who cannot be charged anyway."""
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value=None), \
             patch.object(sc, "_fetch_pricing") as pricing, \
             patch("requests.post") as post:
            assert sc.handle_server_new("prod") is False

        pricing.assert_not_called()
        post.assert_not_called()

    def test_a_missing_ssh_key_stops_before_charging(self, servers_file):
        """A server created with no way in is worse than no server."""
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_derive_ssh_public_line", return_value=None), \
             patch("requests.post") as post:
            assert sc.handle_server_new("prod") is False

        post.assert_not_called()

    def test_an_invalid_name_is_rejected_locally(self, servers_file):
        with patch("requests.post") as post:
            assert sc.handle_server_new("Not A Name") is False
        post.assert_not_called()

    def test_a_name_already_registered_is_rejected_before_spending(self, servers_file):
        """Otherwise you pay for a second machine and cannot address it."""
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        with patch("requests.post") as post:
            assert sc.handle_server_new("prod") is False
        post.assert_not_called()

    def test_unreachable_pricing_endpoint_does_not_guess_a_price(self, servers_file):
        """Showing a made-up number and then charging a different one is worse
        than refusing."""
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_derive_ssh_public_line", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing", return_value=None), \
             patch("requests.post") as post:
            assert sc.handle_server_new("prod") is False

        post.assert_not_called()


class TestServerNewSuccess:
    def test_a_created_server_is_registered_so_no_ip_is_ever_typed(self, servers_file):
        response = Mock(status_code=200)
        response.json.return_value = {
            "ssh_target": "co@1.2.3.4", "expires_at": "2027-07-31T00:00:00+00:00",
            "charged_usd": 180.0,
        }

        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_derive_ssh_public_line", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing", return_value=PRICING), \
             patch.object(sc, "_fetch_balance", return_value=500.0), \
             patch.object(sc, "_confirm", return_value=True), \
             patch("requests.post", return_value=response):
            assert sc.handle_server_new("prod") is True

        assert sc.load_server("prod")["ssh"] == "co@1.2.3.4"

    def test_the_derived_key_is_what_gets_sent(self, servers_file):
        """The server must trust the key the operator already has."""
        line = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAtest connectonion"
        response = Mock(status_code=200)
        response.json.return_value = {"ssh_target": "co@1.2.3.4",
                                      "expires_at": "2027-07-31T00:00:00+00:00",
                                      "charged_usd": 180.0}

        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_derive_ssh_public_line", return_value=line), \
             patch.object(sc, "_fetch_pricing", return_value=PRICING), \
             patch.object(sc, "_fetch_balance", return_value=500.0), \
             patch.object(sc, "_confirm", return_value=True), \
             patch("requests.post", return_value=response) as post:
            sc.handle_server_new("prod")

        assert post.call_args.kwargs["json"]["ssh_public_key"] == line


class TestServerNewFailureReporting:
    def test_insufficient_credit_says_nothing_was_charged(self, servers_file, capsys):
        response = Mock(status_code=402)
        response.json.return_value = {"detail": {
            "error": "insufficient_credits", "balance": 5.0, "required": 180.0,
            "shortfall": 175.0}}

        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_derive_ssh_public_line", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing", return_value=PRICING), \
             patch.object(sc, "_fetch_balance", return_value=5.0), \
             patch.object(sc, "_confirm", return_value=True), \
             patch("requests.post", return_value=response):
            assert sc.handle_server_new("prod") is False

        out = capsys.readouterr().out.lower()
        assert "nothing was created or charged" in out

    def test_a_failed_refund_is_shown_in_red_not_buried(self, servers_file, capsys):
        response = Mock(status_code=502)
        response.json.return_value = {"detail": {
            "error": "provisioning_failed", "refunded": False, "amount": 180.0,
            "message": "charged for a machine that does not exist — contact support"}}

        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_derive_ssh_public_line", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing", return_value=PRICING), \
             patch.object(sc, "_fetch_balance", return_value=500.0), \
             patch.object(sc, "_confirm", return_value=True), \
             patch("requests.post", return_value=response):
            sc.handle_server_new("prod")

        assert "contact support" in capsys.readouterr().out.lower()

    def test_a_failed_creation_registers_nothing_locally(self, servers_file):
        response = Mock(status_code=502)
        response.json.return_value = {"detail": {"error": "provisioning_failed",
                                                 "refunded": True, "amount": 180.0,
                                                 "message": "zone full, refunded"}}

        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch.object(sc, "_derive_ssh_public_line", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing", return_value=PRICING), \
             patch.object(sc, "_fetch_balance", return_value=500.0), \
             patch.object(sc, "_confirm", return_value=True), \
             patch("requests.post", return_value=response):
            sc.handle_server_new("prod")

        assert sc.load_server("prod") is None
