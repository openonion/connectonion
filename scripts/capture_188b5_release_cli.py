"""1.8.8b5's captures, each a live run of the released code — nothing replayed.

    python scripts/capture_188b5_release_cli.py

1. one conversation on two devices, through the production relay
2. `co browser close` on a daemon that has stopped answering
3. `co proxy diagnose`'s endpoint probe against a host the relay lists

Uses real model calls (cents), a real Chrome on a private socket and profile
(the machine's own browser is not touched) and the production relay.
"""
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_186a2_release_cli import page, shoot          # a2's renderer

RELAY = "wss://oo.openonion.ai"
OUT = ROOT / "docs/releases/assets/v1.8.8b5"


def run(argv, env=None, timeout=600):
    result = subprocess.run(argv, cwd=ROOT, env={**os.environ, "NO_COLOR": "1", "COLUMNS": "96",
                                                 "PYTHONPATH": str(ROOT), **(env or {})},
                            capture_output=True, text=True, timeout=timeout)
    return (result.stderr or "") + (result.stdout or ""), result.returncode


def two_devices():
    text, code = run([sys.executable, "scripts/two_device_acceptance.py", "--relay", RELAY])
    assert code == 0, text
    shown = "\n".join(line for line in text.splitlines() if line.strip())
    shoot(page("", [("python scripts/two_device_acceptance.py --relay wss://oo.openonion.ai", shown)]),
          OUT / "two-devices-through-the-relay.png")


def close_a_frozen_daemon():
    profile = Path(tempfile.mkdtemp(prefix="b5-close-")) / "profile"
    sock = "/tmp/co-b5-capture.sock"
    env = {"CO_BROWSER_SOCK": sock, "CO_BROWSER_PROFILE_DIR": str(profile)}
    co = [sys.executable, "-m", "connectonion.cli.main", "browser", "--engine", "system"]
    opened, code = run(co[:4] + ["--headless"] + co[4:] + ["go_to", "https://example.com"], env)
    assert code == 0, opened
    daemon = int(Path(sock + ".pid").read_text().split()[0])
    os.kill(daemon, signal.SIGSTOP)           # alive, holding its socket, never answering
    started = time.monotonic()
    closed, code = run(co + ["close"], env)
    took = time.monotonic() - started
    left = subprocess.run(["pgrep", "-f", str(profile)], capture_output=True, text=True).stdout.split()
    assert code == 1 and not left, (code, left, closed)
    body = closed.strip().split("\n\n💡")[0] + f"\n$ echo $?\n{code}\n$ pgrep -f <that profile> | wc -l\n{len(left)}"
    shoot(page("", [(f"co browser close      # its daemon frozen with SIGSTOP; returned after {took:.0f}s", body)]),
          OUT / "close-ends-what-it-owned.png")


def diagnose_names_the_endpoints():
    import asyncio
    import importlib

    import httpx

    from connectonion.cli.commands import proxy_commands
    from two_device_acceptance import HOST, PORT

    project = Path(tempfile.mkdtemp(prefix="b5-diagnose-"))
    (project / "host.py").write_text(HOST)
    host = subprocess.Popen([sys.executable, "host.py", RELAY], cwd=project,
                            env={**os.environ, "PYTHONPATH": str(ROOT)},
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        for _ in range(120):
            try:
                address = httpx.get(f"http://127.0.0.1:{PORT}/info", timeout=2).json()["address"]
                break
            except httpx.HTTPError:
                time.sleep(0.5)
        time.sleep(5)
        connect = importlib.import_module("connectonion.network.connect")
        reach = asyncio.run(connect.probe_endpoints(address, RELAY))
    finally:
        host.terminate()
        host.wait(10)
    assert reach["probes"], reach
    shoot(page("", [("co proxy diagnose 0x…      # the endpoint part, run against a live host",
                     proxy_commands._describe_reach(reach))]),
          OUT / "diagnose-names-the-endpoints.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    two_devices()
    close_a_frozen_daemon()
    diagnose_names_the_endpoints()
    print("wrote 3 captures into", OUT)
