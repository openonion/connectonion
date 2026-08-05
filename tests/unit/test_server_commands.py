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


_REAL_WAIT_UNTIL_IT_ACCEPTS_YOUR_KEY = sc._wait_until_it_accepts_your_key


@pytest.fixture(autouse=True)
def _do_not_wait_for_a_real_machine(monkeypatch):
    """`co server new` blocks until the box accepts the key. A unit test has no
    box, so it would block for the full timeout. TestReadyMeansYouCanLogIn
    patches this itself and asserts the call, so the behaviour stays covered."""
    monkeypatch.setattr(sc, "_wait_until_it_accepts_your_key",
                        lambda target, name="": True)


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
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
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
             patch.object(sc, "_ensure_ssh_key", return_value=None), \
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
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
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
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
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
             patch.object(sc, "_ensure_ssh_key", return_value=line), \
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
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
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
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
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
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing", return_value=PRICING), \
             patch.object(sc, "_fetch_balance", return_value=500.0), \
             patch.object(sc, "_confirm", return_value=True), \
             patch("requests.post", return_value=response):
            sc.handle_server_new("prod")

        assert sc.load_server("prod") is None


def _response(status, payload=None):
    # content is set because handle_server_destroy checks it before parsing.
    return Mock(status_code=status, content=b"{}",
                json=Mock(return_value=payload or {}))


class TestThePriceIsQuotedAgainstSpendableCredit:
    """`co server new` is the one command that shows someone their balance before
    spending a large amount of it. Showing the wrong number there is worse than
    showing none: they say yes to a purchase they cannot afford."""

    def test_it_reads_balance_not_lifetime_topups(self):
        """credits_usd ignores everything already spent — an account that added
        $315 and spent $291 reads as $315 of headroom. The backend then correctly
        refuses with 402, for a purchase the prompt just said they could afford."""
        payload = {"credits_usd": 315.0, "total_cost_usd": 291.0, "balance_usd": 24.0}

        with patch("requests.get", return_value=_response(200, payload)):
            assert sc._fetch_balance("k") == 24.0

    def test_a_failed_lookup_shows_no_balance_rather_than_a_wrong_one(self):
        with patch("requests.get", return_value=_response(500)):
            assert sc._fetch_balance("k") is None

class TestServerLsReconcilesWithBilling:
    """The local file is a cache; the backend is the ledger. The row that only
    the backend can produce — billed for, not registered here — is somebody
    paying for a machine `co` would otherwise never show them."""

    def test_a_server_you_pay_for_but_never_registered_is_surfaced(self, servers_file, capsys):
        with patch.object(sc, "_fetch_billed_servers", return_value=[
            {"name": "ghost", "expires_at": "2027-07-30T00:00:00", "ssh_target": "co@1.2.3.4"},
        ]):
            assert sc.handle_server_list() is True

        out = capsys.readouterr().out
        assert "ghost" in out
        assert "not registered here" in out

    def test_it_names_the_command_that_stops_the_billing(self, servers_file, capsys):
        with patch.object(sc, "_fetch_billed_servers", return_value=[
            {"name": "ghost", "expires_at": "2027-07-30T00:00:00", "ssh_target": None},
        ]):
            sc.handle_server_list()

        assert "co server destroy" in capsys.readouterr().out

    def test_being_offline_still_lists_local_targets(self, servers_file, capsys):
        """The billing lookup is best-effort. Not being able to reach the API must
        not stop you seeing your own deploy targets."""
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        with patch.object(sc, "_fetch_billed_servers", return_value=None):
            assert sc.handle_server_list() is True

        out = capsys.readouterr().out
        assert "prod" in out
        assert "not registered here" not in out

    def test_unknown_and_empty_are_not_the_same_answer(self, servers_file, capsys):
        """None is 'we could not ask', [] is 'you own nothing'. Only the second
        justifies showing a BILLING column at all."""
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        with patch.object(sc, "_fetch_billed_servers", return_value=[]):
            sc.handle_server_list()
        assert "not ours" in capsys.readouterr().out

    def test_a_failed_lookup_reads_as_unknown_not_as_empty(self, servers_file):
        """A 500 or a timeout must not be reported as 'you own no servers' — that
        is the one answer that would hide a machine you are paying for."""
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch("requests.get", return_value=_response(500)):
            assert sc._fetch_billed_servers() is None


class TestServerDestroy:
    def test_a_mistyped_confirmation_destroys_nothing(self, servers_file):
        """It asks for the name back rather than y/N: a reflex 'y' is exactly how
        someone deletes production while meaning to tidy their config."""
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch("questionary.text") as text, \
             patch("requests.delete") as delete:
            text.return_value.ask.return_value = "prd"
            assert sc.handle_server_destroy("prod") is False

        delete.assert_not_called()

    def test_the_typed_name_must_match_exactly(self, servers_file):
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch("questionary.text") as text, \
             patch("requests.delete", return_value=_response(200, {"refunded_usd": 0})) as delete:
            text.return_value.ask.return_value = "prod"
            assert sc.handle_server_destroy("prod") is True

        delete.assert_called_once()

    def test_no_api_key_stops_before_the_request(self, servers_file):
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value=None), \
             patch("requests.delete") as delete:
            assert sc.handle_server_destroy("prod", yes=True) is False

        delete.assert_not_called()

    def test_a_failed_delete_keeps_the_local_entry(self, servers_file):
        """Removing it would hide a server that is still running and still billing
        — the exact state this whole change exists to make visible."""
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch("requests.delete", return_value=_response(502, {"detail": "boom"})):
            assert sc.handle_server_destroy("prod", yes=True) is False

        assert "prod" in yaml.safe_load(servers_file.read_text())["servers"]

    def test_a_successful_delete_drops_the_local_entry(self, servers_file):
        with patch.object(sc, "_ssh", return_value=_ok("ok")):
            sc.handle_server_add("prod", "user@1.2.3.4")

        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch("requests.delete", return_value=_response(200, {"refunded_usd": 0})):
            assert sc.handle_server_destroy("prod", yes=True) is True

        assert "prod" not in yaml.safe_load(servers_file.read_text())["servers"]

    def test_the_refund_is_reported_as_an_amount_not_a_policy(self, servers_file, capsys):
        """"Prorated" tells the user nothing they can check. A number against what
        they paid does."""
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch("requests.delete", return_value=_response(
                 200, {"refunded_usd": 150.41, "charged_usd": 180.0})):
            assert sc.handle_server_destroy("prod", yes=True) is True

        out = capsys.readouterr().out
        assert "$150.41" in out
        assert "$180.00" in out

    def test_an_expired_server_says_nothing_was_refunded(self, servers_file, capsys):
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch("requests.delete", return_value=_response(200, {"refunded_usd": 0.0})):
            sc.handle_server_destroy("prod", yes=True)

        assert "Nothing refunded" in capsys.readouterr().out

    def test_a_404_points_at_forget_instead(self, servers_file, capsys):
        """A local-only entry has nothing to destroy, and telling the user to
        retry destroy would leave them stuck."""
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key", return_value="k"), \
             patch("requests.delete", return_value=_response(404)):
            assert sc.handle_server_destroy("prod", yes=True) is False

        assert "co server forget" in capsys.readouterr().out

class TestAServerNameIsNotRewritten:
    """The name you type is the name of the machine.

    GCE instance names must start with a letter, so `co server new 1prod` used to
    pass validation, take the $180 charge, and fail at the API. Refusing it here
    is one rule; rewriting it into something GCE accepts would mean the name you
    typed and the machine you got differ, and only for some names.
    """

    def test_a_leading_digit_is_refused_before_anything_is_charged(self):
        with patch("requests.post") as post:
            assert sc.handle_server_new("1prod") is False
        post.assert_not_called()

    def test_the_message_says_what_is_wrong(self, capsys):
        sc.handle_server_new("1prod")
        # Rich wraps to the terminal width, so a phrase can arrive split across
        # lines — collapse the whitespace before looking for it.
        printed = " ".join(capsys.readouterr().out.split())
        assert "starting with a letter" in printed

    def test_ordinary_names_still_pass_the_check(self):
        for name in ["prod", "a", "my-agent-2"]:
            assert sc.SERVER_NAME_PATTERN.match(name), name


class TestWeCanReachTheServerWeJustCreated:
    """A machine from `co server new` has only the derived key installed.

    ssh does not offer that key unless told to, so `co server check` on a
    freshly created server answered `Permission denied (publickey)` — for a
    machine the account had just been charged $180 for. Found by running it.
    """

    def test_ssh_offers_the_servers_own_key_when_it_is_on_disk(self, tmp_path):
        """Per-server since #427 step 4 — there is no global key to offer."""
        from connectonion.cli.commands.keys_commands import per_host_key_path

        with patch("connectonion.cli.commands.keys_commands.SSH_PRIVATE_KEY",
                   tmp_path / "id_ed25519"), \
             patch("connectonion.cli.commands.server_commands._server_name",
                   return_value="prod"), \
             patch("connectonion.cli.commands.keys_commands.per_host_key_path") as php, \
             patch.object(sc.subprocess, "run", return_value=_ok("ok")) as run:
            key = tmp_path / "id_ed25519_prod"
            key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")
            php.return_value = key
            sc._ssh("co@1.2.3.4", "echo ok")

        argv = run.call_args.args[0]
        assert "-i" in argv and str(key) in argv

    def test_the_operators_own_keys_still_work(self, tmp_path):
        """No IdentitiesOnly: a box registered by hand opens with whichever key
        already worked, and adding ours must not take that away."""
        key = tmp_path / "connectonion_ed25519"
        key.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n")

        with patch("connectonion.cli.commands.keys_commands.SSH_PRIVATE_KEY", key), \
             patch.object(sc.subprocess, "run", return_value=_ok("ok")) as run:
            sc._ssh("user@host", "echo ok")

        assert "IdentitiesOnly=yes" not in run.call_args.args[0]

    def test_no_derived_key_on_disk_changes_nothing(self, tmp_path):
        with patch("connectonion.cli.commands.keys_commands.SSH_PRIVATE_KEY",
                   tmp_path / "absent"), \
             patch.object(sc.subprocess, "run", return_value=_ok("ok")) as run:
            sc._ssh("user@host", "echo ok")

        assert "-i" not in run.call_args.args[0]

    def test_creating_a_server_writes_the_private_half_first(self, tmp_path):
        """Only installing the public half produces a machine nobody can open."""
        written = []

        with patch("connectonion.cli.commands.keys_commands._find_co_dir",
                   return_value=tmp_path), \
             patch("connectonion.address.load",
                   return_value={"seed_phrase": "abandon ability able"}), \
             patch("connectonion.address.derive_ssh_key",
                   return_value={"public_line": "ssh-ed25519 AAAA x",
                                 "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n"}), \
             patch("connectonion.cli.commands.keys_commands.write_per_host_ssh_key",
                   side_effect=lambda seed, host, user="root": written.append((seed, host))):
            line = sc._ensure_ssh_key("prod")

        assert line == "ssh-ed25519 AAAA x"
        assert written, "the private half was never written"


class TestTheKeyBelongsToTheOperatorNotTheProject:
    """A server belongs to the person who paid for it.

    The key was derived from the nearest project's recovery phrase, so
    `co server new` run in one project and `co deploy --to` run in another
    produced two different keys — and the second was locked out of the machine
    the first had just bought. The account charged for the server is the global
    one in ~/.co; its key has to be the same one.
    """

    def _identity(self, tmp_path, seed):
        co = tmp_path / ".co"
        co.mkdir(parents=True, exist_ok=True)
        return co, {"seed_phrase": seed}

    def test_two_projects_derive_the_same_key(self, tmp_path, monkeypatch):
        home, global_data = self._identity(tmp_path, "operator phrase")
        monkeypatch.setattr(sc.Path, "home", staticmethod(lambda: tmp_path))

        seen = []

        def fake_load(co_dir):
            return global_data if co_dir == home else {"seed_phrase": "project phrase"}

        with patch("connectonion.address.load", side_effect=fake_load), \
             patch("connectonion.address.derive_ssh_key",
                   side_effect=lambda s, host=None, user="root": seen.append(s) or {
                       "public_line": f"key-for-{s}", "private_key": "x"}), \
             patch("connectonion.cli.commands.keys_commands.write_per_host_ssh_key"), \
             patch("connectonion.cli.commands.keys_commands._find_co_dir",
                   return_value=tmp_path / "project" / ".co"):
            # A name is required since #427 step 4 — every key belongs to a server.
            first = sc._ensure_ssh_key("prod")
            second = sc._ensure_ssh_key("prod")

        assert first == second == "key-for-operator phrase"
        assert "project phrase" not in seen

    def test_it_falls_back_to_the_project_when_there_is_no_global_identity(self, tmp_path,
                                                                          monkeypatch):
        """A machine with only a project identity should still get a key."""
        monkeypatch.setattr(sc.Path, "home", staticmethod(lambda: tmp_path / "empty"))
        project = tmp_path / "project" / ".co"
        project.mkdir(parents=True)

        with patch("connectonion.address.load",
                   return_value={"seed_phrase": "project phrase"}), \
             patch("connectonion.address.derive_ssh_key",
                   return_value={"public_line": "project-key", "private_key": "x"}), \
             patch("connectonion.cli.commands.keys_commands.write_per_host_ssh_key"), \
             patch("connectonion.cli.commands.keys_commands._find_co_dir",
                   return_value=project):
            assert sc._ensure_ssh_key("prod") == "project-key"


class TestTheKeyPairOnDiskAlwaysMatches:
    """Writing one half and keeping the other produces a pair that cannot
    authenticate — ssh calls it "contents do not match public" and refuses,
    which is a confusing way to learn a server you paid for is unreachable."""

    def test_both_halves_are_rewritten_together(self, tmp_path, monkeypatch):
        """Per-server since #427 step 4; the property is unchanged."""
        from connectonion.cli.commands import keys_commands as kc

        monkeypatch.setattr(kc, "SSH_PRIVATE_KEY", tmp_path / "id_ed25519")
        priv = tmp_path / "id_ed25519_prod"
        pub = tmp_path / "id_ed25519_prod.pub"
        priv.write_text("an older key from another phrase")
        pub.write_text("ssh-ed25519 STALE stale\n")

        with patch("connectonion.address.derive_ssh_key",
                   return_value={"private_key": "FRESH PRIVATE",
                                 "public_line": "ssh-ed25519 FRESH fresh"}):
            kc.write_per_host_ssh_key("some phrase", "prod")

        assert priv.read_text() == "FRESH PRIVATE"
        assert pub.read_text().strip() == "ssh-ed25519 FRESH fresh"

    def test_it_does_not_live_in_the_operators_ssh_directory(self):
        """~/.ssh belongs to the operator; overwriting a file there is not ours
        to do, and this file is overwritten by design."""
        from connectonion.cli.commands import keys_commands as kc

        assert ".ssh" not in kc.SSH_PRIVATE_KEY.parts


class TestThePromptLeadsWithTheMonthlyPrice:
    """A server is a monthly thing in everybody's head. "$360" alone is a number
    nobody can compare to anything they already pay for; "$30 a month" places it
    immediately. The year is how we charge, so it is said too — next to it, never
    instead of it."""

    PRICING = {
        "term_months": 12, "region": "australia-southeast1", "default": "e2-small",
        "machine_types": {"e2-small": {"usd_month": 30.0, "usd_12mo": 360.0,
                                       "description": "2 vCPU (shared), 2 GB"}},
    }

    def _prompt(self, pricing):
        with patch("questionary.confirm") as confirm:
            confirm.return_value.ask.return_value = False
            sc._confirm("prod", "e2-small", pricing, 500.0)

    def test_both_the_month_and_the_year_are_shown(self, capsys):
        self._prompt(self.PRICING)
        out = " ".join(capsys.readouterr().out.split())

        assert "$30 / month" in out
        assert "$360.00 for 12 months" in out

    def test_the_backends_monthly_figure_is_used_not_one_we_divide(self, capsys):
        """One price, one place. A CLI that divided could round its way to a
        different number than the one on the website."""
        pricing = {**self.PRICING, "machine_types": {
            "e2-small": {"usd_month": 29.0, "usd_12mo": 360.0, "description": "x"}}}

        self._prompt(pricing)

        assert "$29 / month" in " ".join(capsys.readouterr().out.split())

    def test_an_older_backend_without_the_field_still_prompts(self, capsys):
        """The yearly price is the one actually charged, so a missing monthly
        figure is worth deriving rather than crashing on."""
        pricing = {**self.PRICING, "machine_types": {
            "e2-small": {"usd_12mo": 360.0, "description": "x"}}}

        self._prompt(pricing)

        assert "$30 / month" in " ".join(capsys.readouterr().out.split())

class TestARecreatedServerDoesNotLookLikeAnAttack:
    """Cloud providers reuse addresses.

    When one comes back attached to a machine we just created, the key in
    known_hosts belongs to a machine that no longer exists and ssh refuses with
    a warning about a possible attack — accept-new covers a host never seen, not
    one whose key changed. The operator's first command after paying for a
    server failed exactly this way.
    """

    def test_creating_a_server_drops_the_old_host_key_for_its_address(self):
        with patch.object(sc.subprocess, "run", return_value=_ok("")) as run:
            sc._forget_host_key("co@203.0.113.7")

        assert run.call_args.args[0] == ["ssh-keygen", "-R", "203.0.113.7"]

    def test_it_uses_the_host_not_the_whole_target(self):
        with patch.object(sc.subprocess, "run", return_value=_ok("")) as run:
            sc._forget_host_key("someuser@example.com")

        assert run.call_args.args[0][-1] == "example.com"

    def test_a_created_server_forgets_its_addresss_old_key(self, servers_file):
        """The point is that it happens on create, without being asked."""
        forgotten = []
        server = {"ssh_target": "co@203.0.113.7", "expires_at": "2027-07-31T00:00:00",
                  "charged_usd": 180.0}

        with patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing",
                          return_value={"default": "e2-small",
                                        "machine_types": {"e2-small": {"usd_12mo": 180.0}}}), \
             patch("connectonion.cli.commands.project_cmd_lib.load_api_key",
                   return_value="k"), \
             patch("requests.post", return_value=_response(200, server)), \
             patch.object(sc, "_forget_host_key", side_effect=forgotten.append):
            assert sc.handle_server_new("prod", yes=True) is True

        assert forgotten == ["co@203.0.113.7"]


class TestReadyMeansYouCanLogIn:
    """The API returns as soon as the instance has an address, which is before
    the guest agent has copied the key into authorized_keys — about ten seconds.
    `co server new` printed "✓ ready" and suggested `co server check` next, and
    that command answered "Permission denied (publickey)": the most alarming
    possible way to say "wait ten seconds", on a machine just paid for.
    """

    @pytest.fixture(autouse=True)
    def _use_the_real_wait(self, monkeypatch):
        """This class is the one testing it, so it opts out of the module fixture."""
        monkeypatch.setattr(sc, "_wait_until_it_accepts_your_key",
                            _REAL_WAIT_UNTIL_IT_ACCEPTS_YOUR_KEY)

    def test_it_waits_until_ssh_succeeds(self):
        attempts = []

        def flaky(target, command):
            attempts.append(target)
            return _ok("ok") if len(attempts) >= 3 else _fail("Permission denied (publickey)")

        with patch.object(sc, "_ssh", side_effect=flaky), patch("time.sleep"):
            assert _REAL_WAIT_UNTIL_IT_ACCEPTS_YOUR_KEY("co@1.2.3.4", "prod") is True

        assert len(attempts) == 3

    def test_a_machine_that_never_opens_says_so_instead_of_hanging(self, capsys):
        with patch.object(sc, "_ssh", return_value=_fail("Permission denied (publickey)")), \
             patch.object(sc, "KEY_INSTALL_TIMEOUT_SECONDS", 0):
            assert _REAL_WAIT_UNTIL_IT_ACCEPTS_YOUR_KEY("co@1.2.3.4", "prod") is False

        out = " ".join(capsys.readouterr().out.split())
        assert "charged for" in out, "the operator has paid; say so"
        assert "co server check" in out

    def test_creating_a_server_waits_before_calling_it_ready(self, servers_file):
        waited = []
        server = {"ssh_target": "co@203.0.113.7", "expires_at": "2027-07-31T00:00:00",
                  "charged_usd": 180.0}

        with patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
             patch.object(sc, "_fetch_pricing",
                          return_value={"default": "e2-small",
                                        "machine_types": {"e2-small": {"usd_12mo": 180.0}}}), \
             patch("connectonion.cli.commands.project_cmd_lib.load_api_key",
                   return_value="k"), \
             patch("requests.post", return_value=_response(200, server)), \
             patch.object(sc, "_forget_host_key"), \
             patch.object(sc, "_wait_until_it_accepts_your_key",
                          side_effect=lambda t, name="": waited.append(t) or True):
            assert sc.handle_server_new("prod", yes=True) is True

        assert waited == ["co@203.0.113.7"]


class TestEveryServerHasItsOwnKey:
    """#427 step 4: the shared key is retired; a key belongs to one machine.

    This class used to assert the migration's transitional state — both lines
    installed, both offered — because removing the shared key before every box
    carried its own would have orphaned machines we own, and the way back into a
    server is a key it already trusts.

    That step is done. Before it landed, each live server was checked to open
    with its per-server key alone:

        nw-runner (claude-runner)    NEW_KEY_WORKS
        nw-prod   (naturewill-test)  NEW_KEY_WORKS
        naturewill-prod              NEW_KEY_WORKS
        test      (co-test-deploy)   unreachable — the box no longer exists

    A machine that still holds only the old line has to be re-provisioned: the
    key that opened it can no longer be derived.
    """

    PHRASE = ("legal winner thank year wave sausage worth useful legal "
              "winner thank yellow")

    @pytest.fixture
    def phrase_on_disk(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        co_dir = tmp_path / ".co"
        co_dir.mkdir()
        from connectonion import address
        keys = address.generate()
        keys["seed_phrase"] = self.PHRASE
        address.save(keys, co_dir)
        return co_dir

    def test_a_deploy_installs_one_line_and_it_is_this_servers(
            self, phrase_on_disk, servers_file):
        from connectonion import address

        lines = sc._ssh_public_lines("prod")

        assert len(lines) == 1, lines
        assert lines[0] == address.derive_ssh_key(self.PHRASE, host="prod")["public_line"]

    def test_each_server_gets_its_own_key(self, phrase_on_disk, servers_file):
        """The point of the tree: a key leaked off one box does not open the next."""
        assert sc._ssh_public_lines("prod")[0] != sc._ssh_public_lines("staging")[0]

    def test_ssh_offers_the_server_its_own_key(self, phrase_on_disk, servers_file):
        from connectonion.cli.commands.keys_commands import per_host_key_path

        sc._ssh_public_lines("prod")          # a deploy, which caches the key
        sc._update(lambda servers: servers.update(
            {"prod": {"ssh": "co@1.2.3.4", "hostname": "prod.example"}}))

        for handle in ("prod", "co@1.2.3.4"):
            assert sc._identity(handle) == ["-i", str(per_host_key_path("prod"))], handle

    def test_a_server_we_have_never_seen_gets_no_key_to_offer(
            self, phrase_on_disk, servers_file):
        """There is no shared key to fall back on any more.

        ssh then tries the operator's own keys, which is how a box registered by
        hand with `co server add` has always opened — `_identity` never passes
        IdentitiesOnly, so offering nothing is not the same as refusing.
        """
        assert sc._identity("root@5.6.7.8") == []

    def test_a_name_is_required_to_get_a_line(self, phrase_on_disk, servers_file):
        """Hostless meant the shared key, which is the thing that was retired."""
        assert sc._ssh_public_lines() == []
        assert sc._ensure_ssh_key(None) is None
