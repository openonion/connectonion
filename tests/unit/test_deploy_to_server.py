"""Unit tests for `co deploy --to` — deploy onto a server you own.

The tests that matter here guard one invariant: **a deploy must never recreate
the machine's state.** That is what makes a redeploy stop reissuing the agent's
address, and what lets a fix made by hand over ssh survive. Everything else in
this file is secondary to the rsync exclusions and the pip-skip.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from connectonion.cli.commands import deploy_to_server as dts
from connectonion.cli.commands import server_commands as sc


@pytest.fixture
def project(tmp_path):
    """A minimal deployable project."""
    (tmp_path / ".co").mkdir()
    (tmp_path / ".co" / "host.yaml").write_text(
        yaml.safe_dump({"name": "myagent", "entrypoint": "agent.py"})
    )
    (tmp_path / "agent.py").write_text("print('hi')\n")
    return tmp_path


def _ok(stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr="boom"):
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


class TestSyncNeverTouchesState:
    """The invariant. If these fail, a deploy destroys the agent's identity."""

    @staticmethod
    def _rsync_argv(run):
        """The rsync call specifically — the sync also shells out to chown."""
        for call in run.call_args_list:
            argv = call.args[0]
            if argv and argv[0] == "rsync":
                return argv
        raise AssertionError(f"no rsync call in {run.call_args_list}")

    def test_rsync_never_sends_a_local_identity(self, project):
        """The one rule that must never regress: a local `.co/keys/` cannot be
        pushed over the server's. What the filters *achieve* is asserted against
        a real rsync in test_deploy_sync_filters.py; this only pins the argv so
        the exclusion cannot be dropped by accident."""
        with patch.object(dts.subprocess, "run", return_value=_ok()) as run:
            dts._sync_code("user@host", "myagent", project)

        argv = self._rsync_argv(run)
        pairs = [(argv[i], argv[i + 1]) for i in range(len(argv) - 1)]
        assert ("--exclude", ".co/keys/") in pairs

    def test_rsync_uses_delete_so_removed_code_goes_away(self, project):
        """--delete is wanted for code; the .co/ exclusion is what protects state.

        Without --delete a file deleted locally would linger on the server
        forever. The pairing of --delete with the exclusion is the whole design.
        """
        with patch.object(dts.subprocess, "run", return_value=_ok()) as run:
            dts._sync_code("user@host", "myagent", project)

        assert "--delete" in self._rsync_argv(run)

    def test_nothing_under_co_is_ever_deleted_on_the_server(self, project):
        """`--delete` must not reach inside `.co/`. admins.txt, provision.json
        and the agent's own keys exist only there, and no include-list can
        anticipate what a future version writes beside them.

        This replaced a test that asserted an include-list carried `.co/skills/`
        past a `.co/*` exclude. That assertion held while the same rule was
        dropping `host.yaml`, `OO.md` and `commands/` — which is why the
        outcome, not the argv, is now the thing under test
        (test_deploy_sync_filters.py).
        """
        with patch.object(dts.subprocess, "run", return_value=_ok()) as run:
            dts._sync_code("user@host", "myagent", project)

        argv = self._rsync_argv(run)
        pairs = [(argv[i], argv[i + 1]) for i in range(len(argv) - 1)]
        assert ("--filter", "P .co/**") in pairs

    def test_the_state_exclusion_is_not_a_blanket_co_exclusion(self, project):
        """`--exclude .co/` would prune the directory before the skills include
        could match. The exclusion has to be `.co/*` so rsync still descends."""
        with patch.object(dts.subprocess, "run", return_value=_ok()) as run:
            dts._sync_code("user@host", "myagent", project)

        argv = self._rsync_argv(run)
        pairs = [(argv[i], argv[i + 1]) for i in range(len(argv) - 1)]
        assert ("--exclude", ".co/") not in pairs

    def test_rsync_also_excludes_the_venv_and_git(self, project):
        """The venv lives on the server and must not be overwritten by a local one."""
        with patch.object(dts.subprocess, "run", return_value=_ok()) as run:
            dts._sync_code("user@host", "myagent", project)

        argv = self._rsync_argv(run)
        pairs = [(argv[i], argv[i + 1]) for i in range(len(argv) - 1)]
        assert ("--exclude", ".venv/") in pairs
        assert ("--exclude", ".git/") in pairs

    def test_setup_never_writes_inside_the_state_directory(self, project):
        """ensure(setup) may create .co/ but must not write files into it.

        provision.json is written separately, after a successful deploy — so any
        write to .co/<something> from the setup script would be a bug.
        """
        with patch.object(dts, "_ssh", return_value=_ok()) as ssh:
            dts._ensure_setup("user@host", "myagent", "agent.py", 0, None)

        script = ssh.call_args.args[1]
        assert "mkdir -p /srv/myagent/.co" in script
        # nothing redirected into the state dir
        assert "> /srv/myagent/.co/" not in script


class TestConvergence:
    def test_a_current_schema_skips_setup_entirely(self):
        """The common deploy must not reinstall python on every run."""
        with patch.object(dts, "_ssh", return_value=_ok()) as ssh:
            assert dts._ensure_setup("user@host", "myagent", "agent.py",
                                     dts.PROVISION_SCHEMA, None) is True

        ssh.assert_not_called()

    def test_an_older_schema_runs_the_setup(self):
        with patch.object(dts, "_ssh", return_value=_ok()) as ssh:
            dts._ensure_setup("user@host", "myagent", "agent.py", 0, None)

        assert "python3 -m venv" in ssh.call_args.args[1]

    def test_authorized_keys_is_ensured_even_at_the_current_schema(self):
        """Access self-heals on every deploy — it is the only way back in.

        A one-time write would mean a server whose authorized_keys got clobbered
        needs a rescue path. Re-asserting it every deploy removes that class of
        problem.
        """
        line = "ssh-ed25519 AAAA test"
        with patch.object(dts, "_ssh", return_value=_ok()) as ssh:
            dts._ensure_setup("user@host", "myagent", "agent.py",
                              dts.PROVISION_SCHEMA, line)

        script = ssh.call_args.args[1]
        assert "authorized_keys" in script
        assert "grep -qxF" in script  # idempotent append, not a duplicate every time

    def test_a_missing_marker_reads_as_schema_zero(self):
        with patch.object(dts, "_ssh", return_value=_fail()):
            assert dts._read_provision("user@host", "myagent") == {"schema": 0}

    def test_a_corrupt_marker_reads_as_schema_zero(self):
        """A truncated or hand-edited marker means converge again, not crash."""
        with patch.object(dts, "_ssh", return_value=_ok("{not json\nVENV_PRESENT")):
            assert dts._read_provision("user@host", "myagent") == {"schema": 0}

    def test_a_valid_marker_is_parsed(self):
        probe = json.dumps({"schema": 1}) + "\nVENV_PRESENT"
        with patch.object(dts, "_ssh", return_value=_ok(probe)):
            assert dts._read_provision("user@host", "myagent")["schema"] == 1

    def test_a_marker_without_the_venv_it_speaks_for_reads_as_schema_zero(self):
        """The marker records what *was* true. A venv removed by a disk cleanup
        or a restored snapshot leaves it standing, and the deploy then skipped
        creating one — pip short-circuited on an unchanged requirements hash, and
        the restart failed naming a python that is not there. openonion/connectonion#376
        """
        with patch.object(dts, "_ssh", return_value=_ok(json.dumps({"schema": 2}))):
            assert dts._read_provision("user@host", "myagent") == {"schema": 0}

    def test_the_interpreter_is_checked_in_the_same_round_trip(self):
        """Not a second ssh call: the marker read already costs one."""
        with patch.object(dts, "_ssh", return_value=_ok("{}\nVENV_PRESENT")) as ssh:
            dts._read_provision("user@host", "myagent")

        assert ssh.call_count == 1
        assert ".venv/bin/python" in ssh.call_args.args[1]


class TestDependencyInstall:
    def test_no_requirements_file_means_nothing_to_do(self, project):
        with patch.object(dts, "_ssh") as ssh:
            assert dts._install_deps_if_changed("user@host", "myagent", project) is True
        ssh.assert_not_called()

    def test_unchanged_requirements_skip_the_install(self, project):
        """A code-only change should take seconds, not minutes."""
        (project / "requirements.txt").write_text("requests\n")
        import hashlib
        digest = hashlib.sha256((project / "requirements.txt").read_bytes()).hexdigest()

        with patch.object(dts, "_ssh", return_value=_ok(digest)) as ssh:
            assert dts._install_deps_if_changed("user@host", "myagent", project) is True

        # only the stamp read, no install
        assert ssh.call_count == 1
        assert "pip install" not in ssh.call_args.args[1]

    def test_changed_requirements_trigger_the_install(self, project):
        (project / "requirements.txt").write_text("requests\n")

        with patch.object(dts, "_ssh", side_effect=[_ok("stale-hash"), _ok()]) as ssh:
            assert dts._install_deps_if_changed("user@host", "myagent", project) is True

        assert "pip install" in ssh.call_args_list[-1].args[1]

    def test_a_failed_install_stops_the_deploy(self, project):
        (project / "requirements.txt").write_text("requests\n")

        with patch.object(dts, "_ssh", side_effect=[_ok("stale"), _fail("no matching dist")]):
            assert dts._install_deps_if_changed("user@host", "myagent", project) is False


class TestSystemdUnit:
    def test_unit_restarts_always_and_starts_on_boot(self):
        unit = dts._unit_text("myagent", "agent.py")
        assert "Restart=always" in unit
        assert "WantedBy=multi-user.target" in unit

    def test_unit_runs_the_venv_python_not_the_system_one(self):
        unit = dts._unit_text("myagent", "agent.py")
        assert "/srv/myagent/.venv/bin/python agent.py" in unit

    def test_an_unchanged_unit_is_not_rewritten(self):
        """Rewriting every deploy would mean a daemon-reload for no reason."""
        # Same user the target implies — the unit runs as whoever owns the files.
        wanted = dts._unit_text("myagent", "agent.py", user="user")
        with patch.object(dts, "_ssh", return_value=_ok(wanted)) as ssh:
            # The deploy flow resolves the account once and passes it down, so
            # this call counts only the ssh the unit write itself does.
            assert dts._write_unit_if_changed(
                "user@host", "myagent", "agent.py", user="user"
            ) is True

        assert ssh.call_count == 1  # the read only

    def test_a_changed_unit_is_written_and_reloaded(self):
        with patch.object(dts, "_ssh", side_effect=[_ok("old content"), _ok()]) as ssh:
            assert dts._write_unit_if_changed(
                "user@host", "myagent", "agent.py", user="user"
            ) is True

        script = ssh.call_args_list[-1].args[1]
        assert "daemon-reload" in script
        assert "systemctl enable" in script


class TestRestart:
    def test_a_unit_that_dies_immediately_is_reported_as_failure(self):
        """systemctl restart returns 0 for a unit that starts and dies.

        Trusting the exit code would report a broken deploy as a success, which
        is the worst possible outcome for a deploy command.
        """
        with patch.object(dts, "_ssh",
                          side_effect=[_ok(), _ok("verdict=never-started state=failed"), _ok("traceback…")]):
            assert dts._restart("user@host", "myagent") is False

    def test_an_active_unit_passes(self):
        with patch.object(dts, "_ssh",
                          side_effect=[_ok(), _ok("verdict=up")]):
            assert dts._restart("user@host", "myagent") is True

    def test_journal_is_shown_when_the_unit_does_not_come_up(self, capsys):
        """The traceback is what the operator needs, not an exit code."""
        with patch.object(dts, "_ssh",
                          side_effect=[_ok(), _ok("verdict=never-started state=failed"),
                                       _ok("ModuleNotFoundError: no foo")]):
            dts._restart("user@host", "myagent")

        assert "ModuleNotFoundError" in capsys.readouterr().out


class TestHandleDeployTo:
    def test_unknown_server_is_rejected_before_anything_runs(self, project):
        with patch.object(dts, "load_server", return_value=None), \
             patch.object(dts, "_ssh") as ssh:
            assert dts.handle_deploy_to("nope", project) is False
        ssh.assert_not_called()

    def test_a_project_without_host_yaml_is_rejected(self, tmp_path):
        with patch.object(dts, "load_server", return_value={"ssh": "user@host"}):
            assert dts.handle_deploy_to("prod", tmp_path) is False

    def test_a_missing_entrypoint_is_caught_locally(self, project):
        (project / "agent.py").unlink()
        with patch.object(dts, "load_server", return_value={"ssh": "user@host"}), \
             patch.object(dts, "_ssh") as ssh:
            assert dts.handle_deploy_to("prod", project) is False
        # caught before touching the server
        ssh.assert_not_called()

    def test_an_invalid_agent_name_is_rejected(self, project):
        """The name becomes a directory and a unit name, so the same rule as the
        cloud path applies."""
        (project / ".co" / "host.yaml").write_text(
            yaml.safe_dump({"name": "Not A Valid Name", "entrypoint": "agent.py"})
        )
        with patch.object(dts, "load_server", return_value={"ssh": "user@host"}):
            assert dts.handle_deploy_to("prod", project) is False

    def test_the_marker_is_written_only_after_everything_succeeded(self, project):
        """A marker written too early would let a later deploy skip setup that
        never actually completed."""
        with patch.object(dts, "load_server", return_value={"ssh": "user@host"}), \
             patch.object(sc, "_ensure_ssh_key", return_value=None), \
             patch.object(dts, "_read_provision", return_value={"schema": 0}), \
             patch.object(dts, "_ensure_setup", return_value=True), \
             patch.object(dts, "_sync_code", return_value=True), \
             patch.object(dts, "_install_deps_if_changed", return_value=True), \
             patch.object(dts, "_write_unit_if_changed", return_value=True), \
             patch.object(dts, "_restart", return_value=False), \
             patch.object(dts, "_mark_provisioned") as mark:
            assert dts.handle_deploy_to("prod", project) is False

        mark.assert_not_called()

    def test_a_successful_deploy_marks_the_schema(self, project):
        with patch.object(dts, "load_server", return_value={"ssh": "user@host"}), \
             patch.object(sc, "_ensure_ssh_key", return_value=None), \
             patch.object(dts, "_read_provision", return_value={"schema": 0}), \
             patch.object(dts, "_ensure_setup", return_value=True), \
             patch.object(dts, "_sync_code", return_value=True), \
             patch.object(dts, "_install_deps_if_changed", return_value=True), \
             patch.object(dts, "_write_unit_if_changed", return_value=True), \
             patch.object(dts, "_restart", return_value=True), \
             patch.object(dts, "_mark_provisioned") as mark:
            assert dts.handle_deploy_to("prod", project) is True

        mark.assert_called_once()


class TestAdminSeeding:
    """The deploying key must be able to command the agent it just deployed.

    Without this the agent has no reachable admin at all: ADMIN_ADD is gated on
    super-admin, super-admin is the agent's OWN address, and that private key only
    ever exists on the server.
    """

    ADDR = "0x" + "ab" * 32

    def test_the_deployer_is_written_into_the_agents_admin_list(self):
        with patch.object(dts, "_ssh", return_value=_ok()) as ssh:
            dts._ensure_setup("user@host", "myagent", "agent.py",
                              dts.PROVISION_SCHEMA, None, self.ADDR)

        script = ssh.call_args.args[1]
        assert "/srv/myagent/.co/admins.txt" in script
        assert self.ADDR in script

    def test_it_is_ensured_every_deploy_and_appended_only_once(self):
        """Same reasoning as authorized_keys: it self-heals, and a deploy loop must
        not grow the file by one line every time."""
        with patch.object(dts, "_ssh", return_value=_ok()) as ssh:
            dts._ensure_setup("user@host", "myagent", "agent.py",
                              dts.PROVISION_SCHEMA, None, self.ADDR)

        assert "grep -qxF" in ssh.call_args.args[1]

    def test_no_local_identity_means_no_admin_line(self):
        """Not an error — the deploy proceeds, the agent just has no admin, which
        is the state before this existed."""
        with patch.object(dts, "_ssh", return_value=_ok()) as ssh:
            dts._ensure_setup("user@host", "myagent", "agent.py", 0, None, None)

        assert "admins.txt" not in ssh.call_args.args[1]


class TestHttps:
    """A provisioned server has only 22, 80 and 443 open, and the agent listens on
    8000. Without Caddy in front, nothing a browser can reach ever answers."""

    def test_the_hostname_is_proxied_to_the_agent_on_loopback(self):
        text = dts._caddyfile_with("", "myagent", "prod-abc.agents.openonion.ai", 8000)

        assert "prod-abc.agents.openonion.ai {" in text
        assert "reverse_proxy 127.0.0.1:8000" in text

    def test_a_project_that_moved_its_port_is_proxied_there(self):
        """Caddy pointing at 8000 when the agent listens elsewhere is a 502 that
        looks like the agent crashed."""
        assert "reverse_proxy 127.0.0.1:9100" in dts._caddyfile_with("", "a", "x.example", 9100)

    def test_websockets_need_no_stanza_of_their_own(self):
        """reverse_proxy passes upgrades through unchanged, and chat, dashboard
        pushes and remote exec all ride that one connection. A separate /ws block
        would be a second thing to keep correct."""
        assert "/ws" not in dts._caddyfile_with("", "a", "x.example", 8000)

    def test_the_unit_publishes_the_domain_so_the_agent_announces_a_reachable_url(self):
        """Without it announce.py publishes http://<ip>:8000 to the relay, and
        8000 is closed — so every client probes an endpoint that can never
        answer."""
        unit = dts._unit_text("myagent", "agent.py", "prod-abc.agents.openonion.ai")

        assert "Environment=AGENT_PUBLIC_DOMAIN=prod-abc.agents.openonion.ai" in unit

    def test_a_hand_registered_server_gets_no_domain_line(self):
        """`co server add` gives us an ssh target and no name. Inventing one would
        fail the certificate challenge instead of failing honestly."""
        unit = dts._unit_text("myagent", "agent.py", None)

        assert "AGENT_PUBLIC_DOMAIN" not in unit

    def test_an_unchanged_caddyfile_on_a_running_caddy_is_not_rewritten(self):
        """A reload every deploy would hide whether certificate work was actually
        caused by a change."""
        wanted = dts._caddyfile_with("", "myagent", "x.example", 8000)
        with patch.object(dts, "_ssh") as ssh:
            ssh.side_effect = [_ok(wanted), _ok("active")]
            assert dts._ensure_caddy("user@host", "myagent", "x.example", 8000) is True

        assert ssh.call_count == 2  # read the file, check the service. No write.

    def test_a_changed_caddyfile_is_written_and_reloaded(self):
        with patch.object(dts, "_ssh") as ssh:
            ssh.side_effect = [_ok("something else"), _ok("")]
            assert dts._ensure_caddy("user@host", "myagent", "x.example", 8000) is True

        script = ssh.call_args.args[1]
        assert "/etc/caddy/Caddyfile" in script
        assert "systemctl reload caddy" in script

    def test_caddy_is_installed_only_when_missing(self):
        """apt on every deploy would add a minute to a code-only change."""
        with patch.object(dts, "_ssh") as ssh:
            ssh.side_effect = [_ok("something else"), _ok("")]
            dts._ensure_caddy("user@host", "myagent", "x.example", 8000)

        assert "command -v caddy" in ssh.call_args.args[1]


class TestACrashLoopIsNotASuccessfulDeploy:
    """`Restart=always` means a unit that dies on import is "active" in the
    moment right after the restart, and again after every crash. Asking once
    therefore always says yes — a real deploy reported success for an agent
    looping on an ImportError, and the operator's first hint was a 502.

    A single delayed look is not enough either: the restart resets NRestarts, so
    an eight-second probe called a healthy deploy on an agent that took ten
    seconds to fail. That happened too, on the fix for the first bug.
    """

    def _ssh(self, stdout):
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")

    def _run(self, verdict_line, capsys=None):
        def fake_ssh(target, command, timeout=300):
            if "verdict" in command:
                return self._ssh(verdict_line)
            if "journalctl" in command:
                return self._ssh("ImportError: cannot import name 'create_agent'")
            return self._ssh("")

        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            return dts._restart("co@host", "my-agent")

    def test_an_agent_that_keeps_dying_fails_the_deploy(self, capsys):
        assert self._run("verdict=crashed restarts=3 state=activating") is False
        out = capsys.readouterr().out
        assert "crashed" in out
        assert "ImportError" in out, "the traceback is what the operator needs"

    def test_an_agent_that_stays_up_passes(self):
        assert self._run("verdict=up") is True

    def test_an_agent_that_never_comes_up_fails(self, capsys):
        assert self._run("verdict=never-started state=activating") is False
        assert "never came up" in capsys.readouterr().out

    def test_the_watch_waits_for_a_stable_period_rather_than_looking_once(self):
        """The bug in the first fix: one look, eight seconds in, on an agent
        that takes ten seconds to fail."""
        sent = []

        def fake_ssh(target, command, timeout=300):
            sent.append(command)
            return self._ssh("verdict=up")

        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            dts._restart("co@host", "my-agent")

        watch = next(c for c in sent if "verdict" in c)
        assert "NRestarts" in watch
        assert str(dts.STARTUP_STABLE_SECONDS) in watch
        assert dts.STARTUP_STABLE_SECONDS >= 15,             "shorter than the time a Python agent takes to fail on an import"

class TestDependenciesInstallFromTheProjectDirectory:
    """A requirements.txt may name things relative to itself — a local wheel,
    `-e .`, a nested `-r requirements-dev.txt`. pip ran from the login shell's
    home, so those resolved against /home/<user>:

        WARNING: Requirement './connectonion-1.5.2-py3-none-any.whl' looks like
        a filename, but the file does not exist
        ERROR: No such file or directory: '/home/co/connectonion-…whl'

    while the wheel sat in /srv/e2e-agent/ the whole time.
    """

    def test_pip_is_run_from_the_project_directory(self, tmp_path):
        commands = []

        def fake_ssh(target, command, timeout=300):
            commands.append(command)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        (tmp_path / "requirements.txt").write_text("./local-wheel.whl\n")

        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            dts._install_deps_if_changed("co@host", "my-agent", tmp_path)

        install = next(c for c in commands if "pip install" in c)
        assert f"cd {dts.SRV}/my-agent" in install
        assert "-r requirements.txt" in install, \
            "an absolute -r path does not help; the relative entries inside it are the problem"


class TestTheAgentCanFindItsOwnCommands:
    """`co call <address> co status` — the example in `co call`'s own help —
    answered "co: command not found" on a deployed agent. The unit set no PATH,
    so the process inherited systemd's default, and `co` lives in the project's
    venv. It reaches every command the agent shells out to, not just remote exec.
    """

    def test_the_unit_puts_the_project_venv_first_on_path(self):
        unit = dts._unit_text("my-agent", "agent.py")

        path = next(l for l in unit.splitlines() if l.startswith("Environment=PATH="))
        assert path.partition("PATH=")[2].split(":")[0] == f"{dts.SRV}/my-agent/.venv/bin"

    def test_the_system_directories_are_still_there(self):
        """Prepending, not replacing: the agent still needs git, ssh and the rest."""
        unit = dts._unit_text("my-agent", "agent.py")

        path = next(l for l in unit.splitlines() if l.startswith("Environment=PATH="))
        assert "/usr/bin" in path and "/bin" in path

    def test_the_hostname_is_still_set_alongside_it(self):
        unit = dts._unit_text("my-agent", "agent.py", "host.example.com")

        assert "Environment=AGENT_PUBLIC_DOMAIN=host.example.com" in unit
        assert "Environment=PATH=" in unit


class TestTheAgentDoesNotRunAsRoot:
    """`co call` runs whatever the admin sends, so the unit's user is the
    privilege the remote-exec path hands out. With no `User=` the agent ran as
    root — a superset of what the operator gets by sshing in themselves, on a
    machine where they log in as an ordinary user.

    It also gave the process HOME=/root, which is where the browser went looking
    for a cache it could never have.
    """

    def test_the_unit_runs_as_the_user_that_owns_the_files(self):
        unit = dts._unit_text("my-agent", "agent.py", user="co")
        assert "User=co" in unit

    def test_the_user_comes_from_the_ssh_target(self):
        written = {}

        def fake_ssh(target, command, timeout=300):
            if command.startswith("cat /etc/systemd"):
                return subprocess.CompletedProcess(args=[], returncode=0,
                                                   stdout="old", stderr="")
            written["script"] = command
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            dts._write_unit_if_changed("deployer@1.2.3.4", "my-agent", "agent.py")

        assert "User=deployer" in written["script"]

    def test_the_files_are_handed_to_that_user(self, tmp_path):
        """An agent that ran as root before left root-owned logs behind, and the
        first thing the unprivileged process does is fail to write its own log:

            PermissionError: [Errno 13] Permission denied: '.co/logs/oo.log'
        """
        written = {}

        def fake_ssh(target, command, timeout=300):
            if command.startswith("cat /etc/systemd"):
                return subprocess.CompletedProcess(args=[], returncode=0,
                                                   stdout="old", stderr="")
            written["script"] = command
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        commands = []

        def record(target, command, timeout=300):
            commands.append(command)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch.object(dts, "_ssh", side_effect=record), \
             patch.object(dts.subprocess, "run",
                          return_value=subprocess.CompletedProcess(args=[], returncode=0,
                                                                   stdout="", stderr="")):
            dts._sync_code("co@1.2.3.4", "my-agent", tmp_path)

        assert any(f"chown -R co: {dts.SRV}/my-agent" in c for c in commands), commands


class TestAMissingBinaryIsNotATraceback:
    """`co server add` has always checked for ssh. This path did not — and it is
    the one that runs after the server is already paid for, so the failure it
    produced was a raw FileNotFoundError traceback for the single problem a
    person can fix in one sentence. openonion/connectonion#377
    """

    def test_no_ssh_says_so_and_changes_nothing(self, capsys, project):
        with patch.object(dts.shutil, "which", side_effect=lambda b: None if b == "ssh" else "/usr/bin/rsync"), \
             patch.object(dts, "_ssh") as ssh:
            assert dts.handle_deploy_to("prod", project) is False

        ssh.assert_not_called()
        out = " ".join(capsys.readouterr().out.split())
        assert "No ssh binary found" in out

    def test_no_rsync_says_so_too(self, capsys, project):
        """The sync is rsync, not scp — a box with ssh but no rsync fails halfway."""
        with patch.object(dts.shutil, "which", side_effect=lambda b: None if b == "rsync" else "/usr/bin/ssh"), \
             patch.object(dts, "_ssh") as ssh:
            assert dts.handle_deploy_to("prod", project) is False

        ssh.assert_not_called()
        assert "No rsync binary found" in " ".join(capsys.readouterr().out.split())

    def test_both_present_proceeds(self, project):
        """The check must not become the thing that blocks a working deploy."""
        with patch.object(dts.shutil, "which", return_value="/usr/bin/x"), \
             patch.object(dts, "load_server", return_value=None):
            dts.handle_deploy_to("prod", project)  # falls through to the unknown-server path
