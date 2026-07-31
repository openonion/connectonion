"""A hung ssh must read like a deploy failure, not like a crash.

subprocess.run(timeout=) raises TimeoutExpired, and nothing caught it. A resolver
that hangs or a box that stops answering mid-deploy therefore printed a Python
traceback — which tells the operator we crashed, when what happened is their
server did not answer.

The tests inject TimeoutExpired directly, so nothing here waits for a timeout.
"""

import subprocess

import pytest

from connectonion.cli.commands import deploy_to_server as dts
from connectonion.cli.commands import server_commands as sc


def _timeout(cmd="ssh", seconds=60):
    return subprocess.TimeoutExpired(cmd=cmd, timeout=seconds)


class TestDeployToServer:
    def test_a_timed_out_ssh_returns_a_failure_not_a_traceback(self, capsys):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(_timeout()))
            result = dts._ssh("co@1.2.3.4", "true", timeout=30)

        assert result.returncode != 0, "a timeout is not a success"

    def test_the_message_names_the_server_and_says_it_timed_out(self, capsys):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(_timeout()))
            result = dts._ssh("co@1.2.3.4", "true", timeout=30)

        combined = (result.stderr or "") + (result.stdout or "")
        assert "1.2.3.4" in combined
        assert "timed out" in combined.lower()

    def test_a_deploy_stops_cleanly_when_the_server_stops_answering(self, capsys, tmp_path):
        """The caller already treats a non-zero return as a failed step, so the
        existing error path does the reporting — this only has to stop the
        exception escaping."""
        (tmp_path / ".co").mkdir()
        (tmp_path / ".co" / "host.yaml").write_text("name: myagent\nentrypoint: agent.py\n")
        (tmp_path / "agent.py").write_text("from connectonion import host\nhost(None)\n")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sc, "load_server", lambda name: {"ssh": "co@1.2.3.4"})
            mp.setattr(dts, "load_server", lambda name: {"ssh": "co@1.2.3.4"})
            mp.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(_timeout()))
            assert dts.handle_deploy_to("prod", tmp_path) is False

        assert "Traceback" not in capsys.readouterr().out


class TestServerCommands:
    def test_a_timed_out_preflight_returns_a_failure(self):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(_timeout()))
            result = sc._ssh("co@1.2.3.4", "true")

        assert result.returncode != 0

    def test_server_check_reports_unreachable_rather_than_crashing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sc, "SERVERS_FILE", tmp_path / "servers.yaml")
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(subprocess, "run",
                       lambda *a, **k: subprocess.CompletedProcess([], 0, "ok", ""))
            sc.handle_server_add("prod", "co@1.2.3.4")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(_timeout()))
            assert sc.handle_server_check("prod") is False


class TestTheTimeoutIsStillDistinguishable:
    def test_a_timeout_does_not_look_like_a_command_that_failed(self):
        """An exit code alone cannot tell "the box said no" from "the box said
        nothing" — and the second is a connectivity problem, not a broken
        command."""
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(_timeout()))
            result = dts._ssh("co@1.2.3.4", "true", timeout=30)

        assert "timed out" in (result.stderr or "").lower()
