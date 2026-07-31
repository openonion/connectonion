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

    def test_rsync_excludes_the_state_directory(self, project):
        with patch.object(dts.subprocess, "run", return_value=_ok()) as run:
            dts._sync_code("user@host", "myagent", project)

        argv = run.call_args.args[0]
        assert argv[0] == "rsync"
        # --exclude and its value are separate argv entries. The pattern is
        # `.co/*` rather than `.co/` so rsync still descends far enough for the
        # skills include to match — see the skills test below.
        pairs = [(argv[i], argv[i + 1]) for i in range(len(argv) - 1)]
        assert ("--exclude", ".co/*") in pairs

    def test_rsync_uses_delete_so_removed_code_goes_away(self, project):
        """--delete is wanted for code; the .co/ exclusion is what protects state.

        Without --delete a file deleted locally would linger on the server
        forever. The pairing of --delete with the exclusion is the whole design.
        """
        with patch.object(dts.subprocess, "run", return_value=_ok()) as run:
            dts._sync_code("user@host", "myagent", project)

        assert "--delete" in run.call_args.args[0]

    def test_skills_are_carried_but_the_rest_of_state_is_not(self, project):
        """Skills live in .co/skills/ — excluding all of .co/ shipped an agent
        with none of its skills.

        Found by review after the first version excluded `.co/` wholesale: the
        deploy succeeded and the agent ran without its skills, which is worse
        than failing. The rule is order-sensitive in rsync, so this asserts the
        exact sequence rather than mere membership.
        """
        with patch.object(dts.subprocess, "run", return_value=_ok()) as run:
            dts._sync_code("user@host", "myagent", project)

        argv = run.call_args.args[0]
        # rsync applies the first matching rule, so the includes must come
        # before the exclude that would otherwise swallow them, and `.co/`
        # itself must be included for rsync to descend into it.
        assert argv.index("--include") < argv.index("--exclude")
        pairs = [(argv[i], argv[i + 1]) for i in range(len(argv) - 1)]
        assert ("--include", ".co/") in pairs
        assert ("--include", ".co/skills/***") in pairs
        assert ("--exclude", ".co/*") in pairs

    def test_the_state_exclusion_is_not_a_blanket_co_exclusion(self, project):
        """`--exclude .co/` would prune the directory before the skills include
        could match. The exclusion has to be `.co/*` so rsync still descends."""
        with patch.object(dts.subprocess, "run", return_value=_ok()) as run:
            dts._sync_code("user@host", "myagent", project)

        argv = run.call_args.args[0]
        pairs = [(argv[i], argv[i + 1]) for i in range(len(argv) - 1)]
        assert ("--exclude", ".co/") not in pairs

    def test_rsync_also_excludes_the_venv_and_git(self, project):
        """The venv lives on the server and must not be overwritten by a local one."""
        with patch.object(dts.subprocess, "run", return_value=_ok()) as run:
            dts._sync_code("user@host", "myagent", project)

        argv = run.call_args.args[0]
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
        with patch.object(dts, "_ssh", return_value=_ok("{not json")):
            assert dts._read_provision("user@host", "myagent") == {"schema": 0}

    def test_a_valid_marker_is_parsed(self):
        with patch.object(dts, "_ssh", return_value=_ok(json.dumps({"schema": 1}))):
            assert dts._read_provision("user@host", "myagent")["schema"] == 1


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
        wanted = dts._unit_text("myagent", "agent.py")
        with patch.object(dts, "_ssh", return_value=_ok(wanted)) as ssh:
            assert dts._write_unit_if_changed("user@host", "myagent", "agent.py") is True

        assert ssh.call_count == 1  # the read only

    def test_a_changed_unit_is_written_and_reloaded(self):
        with patch.object(dts, "_ssh", side_effect=[_ok("old content"), _ok()]) as ssh:
            assert dts._write_unit_if_changed("user@host", "myagent", "agent.py") is True

        script = ssh.call_args_list[-1].args[1]
        assert "daemon-reload" in script
        assert "systemctl enable" in script


class TestRestart:
    def test_a_unit_that_dies_immediately_is_reported_as_failure(self):
        """systemctl restart returns 0 for a unit that starts and dies.

        Trusting the exit code would report a broken deploy as a success, which
        is the worst possible outcome for a deploy command.
        """
        with patch.object(dts, "_ssh", side_effect=[_ok(), _ok("failed"), _ok("traceback…")]):
            assert dts._restart("user@host", "myagent") is False

    def test_an_active_unit_passes(self):
        with patch.object(dts, "_ssh", side_effect=[_ok(), _ok("active")]):
            assert dts._restart("user@host", "myagent") is True

    def test_journal_is_shown_when_the_unit_does_not_come_up(self, capsys):
        """The traceback is what the operator needs, not an exit code."""
        with patch.object(dts, "_ssh",
                          side_effect=[_ok(), _ok("failed"), _ok("ModuleNotFoundError: no foo")]):
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
