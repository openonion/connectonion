"""`co rem open` after an upgrade, with real co ai Hosts and the real CLI (#2937).

The reader's Host is started once and lives for days. The package under it is
upgraded; the process keeps the old code. Here the old Host is a real co ai
that reports an earlier version, exactly what an upgrade leaves behind, and
the open is the real command in its own process.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

import connectonion
from connectonion import address
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from tests import host_leak_guard

# co ai, started before the upgrade: it says the version it was started with.
OLD_CO_AI = '''
import runpy
import connectonion
connectonion.__version__ = "0.0.1"
runpy.run_module("connectonion.cli.main", run_name="__main__")
'''


def _info(port):
    try:
        return httpx.get(f"http://127.0.0.1:{port}/info", timeout=1.0).json()
    except (httpx.HTTPError, ValueError):
        return None


def _wait_for_replacement(co_dir: Path, seconds: float = 30.0) -> None:
    """Until no build or open is replacing this home's Host: the lock they hold
    while they do (co_ai.main._owner_invite_lock), taken and let go."""
    if os.name == "nt":  # nothing replaces a Host there (live_host._started_here)
        return
    import fcntl
    deadline = time.monotonic() + seconds
    with open(co_dir / "owner-invite.lock", "a+b") as lock:
        while True:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                assert time.monotonic() < deadline, f"a Host replacement under {co_dir} did not finish in {seconds:g}s"
                time.sleep(0.05)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@pytest.fixture
def upgraded(tmp_path, tmp_path_factory, monkeypatch):
    """(old Host process, its port, the identity's address, the record): a co ai
    that `co rem open` started and recorded, and the package upgraded under it."""
    home = Path(os.environ["HOME"])                 # this test's own home (conftest)
    identity = address.generate()
    address.save(identity, home / ".co")
    prepare(home / ".co/rem")
    Notebook(home / ".co/rem").write("people/alice-chen.md", "# Alice Chen\nWorks on Project Aurora.")
    monkeypatch.setenv("OPENONION_API_KEY", "test-key")
    monkeypatch.setenv("CONNECTONION_BACKEND_URL", "http://127.0.0.1:9")   # no relay: nothing leaves this machine
    script = tmp_path / "old_co_ai.py"
    script.write_text(OLD_CO_AI)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    args = [sys.executable, str(script), "ai", "--port", str(port), "--no-listen", "--no-launch"]
    with open(tmp_path / "old-host.log", "ab") as log:
        # The checkout under test, not whatever the interpreter has installed: a
        # script's own folder, not the current one, is first on its path.
        checkout = str(Path(connectonion.__file__).resolve().parents[1])
        old = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=True, env={**os.environ, "PYTHONPATH": checkout})
    try:
        deadline = time.monotonic() + 60
        while not (_info(port) or {}).get("version") == "0.0.1":
            assert old.poll() is None and time.monotonic() < deadline, (tmp_path / "old-host.log").read_text()
            time.sleep(0.2)
        record = home / ".co/rem-live-host.json"
        record.write_text(json.dumps({"address": identity["address"], "pid": old.pid, "port": port,
                                      "command": " ".join(args[1:])}))
        yield old, port, identity["address"], record
    finally:
        # The replacement is finished when its lock is free, not when the new Host
        # answers. The detached build holds the lock from the old Host's stop until
        # it has seen the new one answer (live_host._renew/_exits). This test can see
        # the answer first; stopping the Host then made the build read it as "exited
        # during startup" and start another on a fresh port, recorded after this
        # stop had run: the Host the leak guard found in five main runs (#2980).
        _wait_for_replacement(home / ".co")
        # The new Host is the one this home recorded; this test started it, so it stops it.
        host_leak_guard.stop_recorded(tmp_path_factory.getbasetemp(), str(home))
        old.kill()
        old.wait()


def test_open_after_an_upgrade_ends_on_a_host_of_the_installed_version(upgraded):
    old, port, owner, record = upgraded
    opened = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "rem", "open", "--no-launch"],
                            capture_output=True, text=True, timeout=50)   # under the suite's 60 s
    assert opened.returncode == 0, opened.stdout + opened.stderr
    assert old.poll() is not None, "the Host started before the upgrade is still running"
    saved = json.loads(record.read_text())
    assert saved["pid"] != old.pid and saved["port"] == port      # an open tab keeps its address
    assert f"http://127.0.0.1:{port}/rem?token=" in opened.stdout
    info = _info(port)
    assert info["address"] == owner and info["version"] == connectonion.__version__


def test_a_tab_open_before_the_upgrade_is_served_by_the_installed_version_with_no_command(upgraded):
    """Nobody runs `co rem open` here (D-60). The tab's own request makes the old
    Host start the page build, and the build, which is the installed code,
    replaces that Host on its port; the tab's cookie is still good there."""
    from connectonion.rem.live_host import reader_token
    old, port, owner, record = upgraded
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", follow_redirects=True, timeout=20) as tab:
        first = tab.get("/rem", params={"token": reader_token(record.parent)})
        assert first.status_code == 200 and "Alice Chen" in first.text
        deadline = time.monotonic() + 30   # under the suite's 60 s limit, so the failure is this sentence
        while (_info(port) or {}).get("version") != connectonion.__version__:
            assert time.monotonic() < deadline, "the old Host was not replaced"
            time.sleep(0.3)
        assert old.poll() is not None
        saved = json.loads(record.read_text())
        assert saved["pid"] != old.pid and saved["port"] == port
        reloaded = tab.get("/rem")                                  # one reload, the cookie it already had
        assert reloaded.status_code == 200 and "Alice Chen" in reloaded.text
