"""The Host leak guard reads real processes; these prove it on two known ones.

A guard that under-reads is worse than none: it reports a clean run. So it is
run against a process that must be listed and one that must not be.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from tests import host_leak_guard

STUB = Path(__file__).resolve().parents[1] / "rem_host_stub.py"


def _host(home: Path):
    """A process with the reader's Host command, started under `home`."""
    home.mkdir(parents=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen([sys.executable, str(STUB), "owner", "0.0.1", "ai", "--port", str(port),
                                "--no-listen", "--no-launch"], stdin=subprocess.DEVNULL,
                               env={**os.environ, "HOME": str(home)})
    deadline = time.monotonic() + 20
    while True:   # until it is the stub, not still the fork of this process
        assert process.poll() is None and time.monotonic() < deadline, "the stub Host did not answer"
        try:
            httpx.get(f"http://127.0.0.1:{port}/info", timeout=1.0)
            return process
        except httpx.HTTPError:
            pass


def test_only_a_host_under_this_runs_temp_directory_is_listed_and_stopped(tmp_path, request):
    run = tmp_path / "run"
    ours, theirs = _host(run / "home"), _host(tmp_path / "elsewhere")
    try:
        assert [(pid, home) for pid, home, _ in host_leak_guard.hosts_under(run)] == [(ours.pid, str(run / "home"))]
        assert request.node.name in host_leak_guard.hosts_under(run)[0][2]   # names the test that started it
        # Not under this run: neither listed nor signalled, even when asked by pid.
        host_leak_guard.stop(run, theirs.pid)
        assert theirs.poll() is None
        # The per-test teardown: the Host this test's own home recorded.
        for home, process in ((run / "home", ours), (tmp_path / "elsewhere", theirs)):
            (home / ".co").mkdir()
            (home / ".co/rem-live-host.json").write_text(json.dumps({"pid": process.pid}))
            host_leak_guard.stop_recorded(run, str(home))
        assert ours.wait(timeout=10) is not None
        assert theirs.poll() is None                 # a home outside this run is not even read
        assert host_leak_guard.hosts_under(run) == []
    finally:
        for process in (ours, theirs):
            process.kill()
            process.wait()


@pytest.mark.parametrize("returncode,stdout,stderr", [(1, "", "ps: illegal option"), (0, "", "")])
def test_a_ps_that_fails_or_lists_nothing_is_an_error_not_a_clean_run(tmp_path, monkeypatch, returncode, stdout, stderr):
    monkeypatch.setattr(host_leak_guard.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr))
    with pytest.raises(RuntimeError, match="ps could not list processes"):
        host_leak_guard.hosts_under(tmp_path)


def test_pids_that_have_all_exited_are_none_left(tmp_path):
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    assert host_leak_guard.hosts_under(tmp_path, [gone.pid]) == []
