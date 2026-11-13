"""`co deploy --to` says an agent started only when the restarted unit is up and answers /info (#3016).

A deploy ended with "order-agent did not start." while systemd showed the
unit active with NRestarts=0, a clean journal, and /info answering; the next
deploy passed. "did not start" was the fallback for a watch that returned no
verdict at all: the ssh call carrying it had failed, and its error was thrown
away. The watch also never asked whether the active unit was the one the
restart started, or whether the agent answered.

The scripts run for real in bash here, against a fake systemctl and a fake
/info probe on PATH. No server is touched.
"""

import os
import subprocess

import pytest

from connectonion.cli.commands import deploy_to_server as dts

SYSTEMCTL = """#!/bin/sh
# systemctl show -p NAME --value UNIT | systemctl is-active UNIT | systemctl restart UNIT
state="$FAKE/state"
case "$1" in
  restart) cp "$FAKE/after" "$state"; exit 0 ;;
  is-active) . "$state"; echo "$ActiveState"; exit 0 ;;
  show) . "$state"; eval echo "\\$$3"; exit 0 ;;
esac
"""
SUDO = '#!/bin/sh\nexec "$@"\n'
# The probe is python3 on the server: the agent's own runtime, so it is always there.
PYTHON = '#!/bin/sh\n[ -f "$FAKE/info" ] && exit 0\necho "URLError: Connection refused" >&2\nexit 1\n'


@pytest.fixture
def server(tmp_path, monkeypatch):
    """A fake box: `before` is the unit as the restart finds it, `after` as the restart leaves it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, text in (("systemctl", SYSTEMCTL), ("sudo", SUDO), ("python3", PYTHON)):
        (bin_dir / name).write_text(text)
        (bin_dir / name).chmod(0o755)
    unit = {"ActiveState": "active", "NRestarts": "0", "ActiveEnterTimestampMonotonic": "1000"}
    (tmp_path / "state").write_text("".join(f"{key}={value}\n" for key, value in unit.items()))
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE": str(tmp_path)}
    calls = []

    def ssh(target, command, timeout=300):
        calls.append(command)
        if "journalctl" in command:
            return subprocess.CompletedProcess([], 0, "host banner\n", "")
        return subprocess.run(["sh", "-c", command], capture_output=True, text=True, env=env, timeout=timeout)

    monkeypatch.setattr(dts, "_ssh", ssh)
    monkeypatch.setattr(dts, "STARTUP_STABLE_SECONDS", 1)
    monkeypatch.setattr(dts, "STARTUP_TIMEOUT_SECONDS", 3)

    def after(answers_info=True, **changes):
        state = {**unit, **changes}
        (tmp_path / "after").write_text("".join(f"{key}={value}\n" for key, value in state.items()))
        (tmp_path / "info").write_text("ok") if answers_info else (tmp_path / "info").unlink(missing_ok=True)
    after.calls = calls
    return after


def test_a_restarted_unit_that_is_up_and_answers_info_is_a_started_agent(server):
    server(ActiveEnterTimestampMonotonic="2000")
    assert dts._restart("co@host", "order-agent", 8000) is True


def test_the_unit_from_before_the_restart_is_not_taken_for_the_new_one(server, capsys):
    """Active, NRestarts=0, but entered active before the restart: not this deploy's agent."""
    server(ActiveEnterTimestampMonotonic="1000")
    assert dts._restart("co@host", "order-agent", 8000) is False
    out = " ".join(capsys.readouterr().out.split())  # the console wraps at 80 columns
    assert "never came up within 3 s" in out and "not restarted" in out, out


def test_an_agent_that_does_not_answer_info_is_not_reported_as_started(server, capsys):
    server(ActiveEnterTimestampMonotonic="2000", answers_info=False)
    assert dts._restart("co@host", "order-agent", 8000) is False
    out = " ".join(capsys.readouterr().out.split())  # the console wraps at 80 columns
    assert "never came up within 3 s" in out and "/info on port 8000 did not answer" in out, out
    assert "active" in out, out


def test_the_info_probe_asks_the_agents_own_port(server):
    server(ActiveEnterTimestampMonotonic="2000")
    dts._restart("co@host", "order-agent", 8123)
    assert any("127.0.0.1:8123/info" in command for command in server.calls)


def test_a_watch_whose_ssh_dropped_is_asked_again_not_called_a_failed_start(server, monkeypatch):
    server(ActiveEnterTimestampMonotonic="2000")
    real, dropped = dts._ssh, []

    def drop_once(target, command, timeout=300):
        if "verdict=" in command and not dropped:
            dropped.append(command)
            return subprocess.CompletedProcess([], 255, "", "Connection to host closed by remote host.\n")
        return real(target, command, timeout)
    monkeypatch.setattr(dts, "_ssh", drop_once)
    assert dts._restart("co@host", "order-agent", 8000) is True


def test_a_watch_that_cannot_reach_the_server_says_so_with_the_ssh_error(server, monkeypatch, capsys):
    server(ActiveEnterTimestampMonotonic="2000")
    real = dts._ssh

    def unreachable(target, command, timeout=300):
        if "verdict=" in command:
            return subprocess.CompletedProcess([], 255, "", "ssh: connect to host 203.0.113.9 port 22: Connection refused\n")
        return real(target, command, timeout)
    monkeypatch.setattr(dts, "_ssh", unreachable)
    assert dts._restart("co@host", "order-agent", 8000) is False
    out = " ".join(capsys.readouterr().out.split())  # the console wraps at 80 columns
    assert "did not start" not in out, out
    assert "could not watch order-agent start" in out and "Connection refused" in out, out


def test_a_crash_after_the_restart_is_still_a_crash(server, capsys):
    server(ActiveEnterTimestampMonotonic="2000", NRestarts="2", ActiveState="activating")
    assert dts._restart("co@host", "order-agent", 8000) is False
    assert "crashed and is being restarted (2 time(s) so far)" in " ".join(capsys.readouterr().out.split())


def test_the_watch_is_bounded(server):
    """Whatever the box does, the deploy gives up within the timeout plus one probe."""
    import time
    server(ActiveEnterTimestampMonotonic="1000")
    began = time.monotonic()
    dts._restart("co@host", "order-agent", 8000)
    assert time.monotonic() - began < dts.STARTUP_TIMEOUT_SECONDS + 5


