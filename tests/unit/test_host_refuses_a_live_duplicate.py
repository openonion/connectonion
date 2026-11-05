"""A second Host must not split an address's sessions across working folders."""

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from connectonion import Agent, address
from connectonion.network.host import server


@pytest.fixture
def live_process(tmp_path):
    process = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"],
        stdin=subprocess.PIPE, cwd=tmp_path,
    )
    yield process
    process.stdin.close()
    process.wait(timeout=10)


@pytest.fixture
def recorded_host(tmp_path, monkeypatch, live_process):
    co_dir = Path.home() / ".co"
    address.save(address.generate(), co_dir)
    identity = address.load(co_dir)
    record = co_dir / "served_by.json"
    existing = {
        "address": identity["address"], "name": "cedar",
        "project": str(co_dir.parent), "pid": live_process.pid, "port": 8123,
    }
    record.write_text(json.dumps(existing))
    project = tmp_path / "maple"
    project.mkdir()
    monkeypatch.chdir(project)

    def no_listener(url, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx, "get", no_listener)
    return co_dir, identity, record, existing


@pytest.fixture
def answering_host(recorded_host, monkeypatch):
    _, identity, _, existing = recorded_host

    def info(url, *, timeout, trust_env):
        assert url == f"http://127.0.0.1:{existing['port']}/info"
        assert timeout == 1.0
        assert trust_env is False
        return httpx.Response(200, json={"address": identity["address"]})

    monkeypatch.setattr(httpx, "get", info)
    return recorded_host


@pytest.mark.parametrize("same_folder", [False, True])
def test_co_ai_refuses_another_live_host_on_its_global_identity(
        monkeypatch, answering_host, same_folder):
    co_dir, _, record, existing = answering_host
    key = co_dir / "keys" / "agent.key"
    original_key = key.read_bytes()
    if same_folder:
        monkeypatch.chdir(co_dir.parent)
    served = []
    monkeypatch.setattr(server.uvicorn, "run", lambda *a, **kw: served.append(kw))
    monkeypatch.setattr(server, "_print_host_banner", lambda **kw: served.append("banner"))

    with pytest.raises(SystemExit) as stopped:
        server.host(Agent("maple", model="co/gemini-3.7-flash", api_key="test-key",
                          quiet=True, log=False),
                    co_dir=co_dir, port=8124, relay_url=None)

    message = str(stopped.value.code)
    assert stopped.value.code != 0
    assert str(existing["pid"]) in message
    assert str(co_dir.parent) in message
    assert "8123" in message
    assert "cedar" in message
    assert f"kill {existing['pid']}" in message
    assert "address.save" not in message
    assert "address.generate" not in message
    assert served == []
    assert json.loads(record.read_text()) == existing
    assert key.read_bytes() == original_key


def test_a_dead_pid_is_replaced_quietly(recorded_host, live_process, capsys):
    co_dir, identity, record, _ = recorded_host
    live_process.stdin.close()
    live_process.wait(timeout=10)

    assert server.claim_identity(co_dir, identity, "maple", 8124) is None

    assert capsys.readouterr().out == ""
    assert json.loads(record.read_text()) == {
        "address": identity["address"], "name": "maple",
        "project": str(Path.cwd()), "pid": os.getpid(), "port": 8124,
    }


def test_a_live_unrelated_pid_with_no_answer_is_replaced_quietly(
        recorded_host, live_process, capsys):
    co_dir, identity, record, _ = recorded_host
    assert live_process.poll() is None

    assert server.claim_identity(co_dir, identity, "maple", 8124) is None

    assert capsys.readouterr().out == ""
    assert json.loads(record.read_text()) == {
        "address": identity["address"], "name": "maple",
        "project": str(Path.cwd()), "pid": os.getpid(), "port": 8124,
    }


def test_a_record_for_another_address_is_replaced(recorded_host):
    co_dir, identity, record, existing = recorded_host
    existing["address"] = address.generate()["address"]
    record.write_text(json.dumps(existing))

    assert server.claim_identity(co_dir, identity, "maple", 8124) is None
    assert json.loads(record.read_text())["address"] == identity["address"]


def test_the_same_process_can_refresh_its_claim(recorded_host):
    co_dir, identity, record, existing = recorded_host
    existing["pid"] = os.getpid()
    record.write_text(json.dumps(existing))

    assert server.claim_identity(co_dir, identity, "maple", 8124) is None
    assert json.loads(record.read_text())["name"] == "maple"
    assert server.claim_identity(co_dir, identity, "birch", 8124) is None
    assert json.loads(record.read_text())["name"] == "birch"


def test_a_legacy_record_without_a_pid_is_replaced(recorded_host):
    co_dir, identity, record, existing = recorded_host
    del existing["pid"]
    del existing["port"]
    record.write_text(json.dumps(existing))

    assert server.claim_identity(co_dir, identity, "maple", 8124) is None
    assert json.loads(record.read_text())["pid"] == os.getpid()


def test_a_taken_port_does_not_leave_a_live_claim(recorded_host, live_process, monkeypatch):
    co_dir, identity, record, existing = recorded_host
    live_process.stdin.close()
    live_process.wait(timeout=10)
    monkeypatch.setattr(server, "_port_in_use", lambda port: True)

    with pytest.raises(SystemExit, match="Port 8124 is already in use"):
        server.host(lambda: pytest.fail("must not extract metadata"),
                    co_dir=co_dir, port=8124, relay_url=None)

    assert json.loads(record.read_text()) == existing


@pytest.mark.parametrize("pid", [0, os.getpid()], ids=["no-pid", "own-pid"])
def test_an_answering_host_is_verified_regardless_of_pid(answering_host, pid):
    co_dir, identity, record, existing = answering_host
    existing["pid"] = pid
    record.write_text(json.dumps(existing))

    assert server.claim_identity(co_dir, identity, "maple", 8124)
    assert json.loads(record.read_text()) == existing


@pytest.mark.parametrize("reply", [
    httpx.ReadTimeout("timed out"),
    httpx.Response(200, json={"address": "0xanother-address"}),
    httpx.Response(200, json={}),
    httpx.Response(200, text="not JSON"),
    503,
])
def test_an_unverified_host_is_replaced_quietly(recorded_host, monkeypatch, capsys, reply):
    co_dir, identity, record, _ = recorded_host

    def info(url, **kwargs):
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            return httpx.Response(reply, json={"address": identity["address"]})
        return reply

    monkeypatch.setattr(httpx, "get", info)

    assert server.claim_identity(co_dir, identity, "maple", 8124) is None
    assert capsys.readouterr().out == ""
    assert json.loads(record.read_text())["name"] == "maple"


def test_claim_identity_does_not_check_port_availability(recorded_host, monkeypatch):
    co_dir, identity, _, _ = recorded_host
    monkeypatch.setattr(server, "_port_in_use", lambda port: pytest.fail("identity only"))

    assert server.claim_identity(co_dir, identity, "maple", 8124) is None
