"""One address, one Host on this computer.

Every local Host — `co ai`, a project's `co host`, the background service and
the `co ai` that `co rem open` starts — serves ~/.co's key. Two at once both
announce it, and the relay sends each call to whichever re-announced last:
measured on 1.9.3rc39 with two Hosts on ports 8711 and 8712, the relay's entry
flipped between them on every heartbeat for four minutes (#2750). So the second
is refused, saying where the first one is, and `co host --stop` and `co status`
find the first one from any folder.

These start real Host processes; the lock is only real across processes.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX signals and paths")

ROOT = Path(__file__).resolve().parents[2]

AGENT = """
from connectonion import Agent, host
def ping() -> str:
    \"\"\"Answer.\"\"\"
    return "pong"
host(Agent("{name}", tools=[ping], model="gpt-4o-mini"), relay_url=None, trust="open")
"""


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def machine(tmp_path):
    """A home with one key and two projects that have none, as `co create` makes them."""
    from connectonion import address
    home = tmp_path / "home"
    (home / ".co").mkdir(parents=True)
    address.save(address.generate(), home / ".co")
    projects = []
    for name in ("first", "second"):
        project = tmp_path / name
        (project / ".co").mkdir(parents=True)
        (project / "agent.py").write_text(AGENT.format(name=name))
        projects.append(project)
    env = {**os.environ, "HOME": str(home), "PYTHONPATH": str(ROOT), "OPENAI_API_KEY": "sk-test",
           "AGENT_CONFIG_PATH": str(home / ".co")}
    env.pop("XPC_SERVICE_NAME", None)
    return home, projects, env


def _start(project, env, port):
    return subprocess.Popen([sys.executable, "agent.py"], cwd=project,
                            env={**env, "AGENT_PORT": str(port)},
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _co(project, env, *args):
    return subprocess.run([sys.executable, "-m", "connectonion.cli.main", *args], cwd=project,
                          env=env, capture_output=True, text=True, timeout=60)


def _wait_serving(home, timeout=30):
    record = home / ".co" / "host.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if record.is_file() and record.read_text():
            return json.loads(record.read_text())
        time.sleep(.2)
    raise AssertionError("the first Host never recorded itself")


def test_a_second_host_on_the_same_address_is_refused_and_told_where_the_first_is(machine):
    home, (first, second), env = machine
    one = _start(first, env, _free_port())
    try:
        _wait_serving(home)
        two = _start(second, env, _free_port())
        output, _ = two.communicate(timeout=60)

        assert two.returncode != 0, output
        assert "already served on this computer" in output, output
        assert str(first) in output and "co host --stop" in output, output
        assert one.poll() is None, "refusing the second must leave the first serving"
    finally:
        one.kill()
        one.wait()


def test_once_the_first_is_gone_the_address_is_free_again(machine):
    """The OS drops the lock with the process: a crash leaves no stale claim."""
    home, (first, second), env = machine
    one = _start(first, env, _free_port())
    _wait_serving(home)
    one.kill()
    one.wait()

    two = _start(second, env, _free_port())
    try:
        record = _wait_serving(home)
        deadline = time.monotonic() + 30
        while record.get("pid") != two.pid and time.monotonic() < deadline:
            time.sleep(.2)
            record = json.loads((home / ".co" / "host.json").read_text())
        assert record["pid"] == two.pid and record["project"] == str(second)
    finally:
        two.kill()
        two.wait()


def test_status_and_stop_find_the_host_from_another_folder(machine, tmp_path):
    home, (first, _), env = machine
    port = _free_port()
    one = _start(first, env, port)
    try:
        _wait_serving(home)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()

        status = _co(elsewhere, env, "host", "--status")
        serving = json.loads(status.stdout)["serving"]
        assert serving["pid"] == one.pid and serving["port"] == port, status.stdout + status.stderr

        stopped = _co(elsewhere, env, "host", "--stop")
        assert stopped.returncode == 0, stopped.stdout + stopped.stderr
        one.wait(timeout=15)
        assert json.loads(_co(elsewhere, env, "host", "--status").stdout)["serving"] is None
    finally:
        if one.poll() is None:
            one.kill()
            one.wait()
