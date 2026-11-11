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

import connectonion
from connectonion import address
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook

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


def test_open_after_an_upgrade_ends_on_a_host_of_the_installed_version(tmp_path, monkeypatch):
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
        old = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                               start_new_session=True)
    try:
        deadline = time.monotonic() + 60
        while not (_info(port) or {}).get("version") == "0.0.1":
            assert old.poll() is None and time.monotonic() < deadline, (tmp_path / "old-host.log").read_text()
            time.sleep(0.2)
        record = home / ".co/rem-live-host.json"
        record.write_text(json.dumps({"address": identity["address"], "pid": old.pid, "port": port,
                                      "command": " ".join(args[1:])}))

        opened = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "rem", "open", "--no-launch"],
                                capture_output=True, text=True, timeout=120)

        assert opened.returncode == 0, opened.stdout + opened.stderr
        assert old.poll() is not None, "the Host started before the upgrade is still running"
        saved = json.loads(record.read_text())
        assert saved["pid"] != old.pid and saved["port"] == port      # an open tab keeps its address
        assert f"http://127.0.0.1:{port}/rem?token=" in opened.stdout
        info = _info(port)
        assert info["address"] == identity["address"] and info["version"] == connectonion.__version__
    finally:
        # The new Host is the one this home recorded: conftest stops it. The old one is this test's.
        old.kill()
        old.wait()
