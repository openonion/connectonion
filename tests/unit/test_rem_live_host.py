"""Explicit live opens own Host startup; snapshots never start an agent."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from connectonion.rem import live_host, reader
from connectonion.rem.files import write_json


@pytest.fixture
def startup(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: tmp_path)
    monkeypatch.setattr("connectonion.cli.co_ai.main._owner_invite_lock", lambda p: nullcontext())
    monkeypatch.setattr(live_host.time, "sleep", lambda seconds: None)
    return tmp_path


def test_offline_host_is_started_and_waited_for(startup, monkeypatch):
    answers = iter([False, False, True])
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: next(answers))
    spawned = []
    process = SimpleNamespace(pid=42, args=["python", "-m", "connectonion.cli.main", "ai"], poll=lambda: None)
    monkeypatch.setattr(live_host, "_spawn", lambda directory: spawned.append(directory) or process)
    assert live_host.ensure_online("owner") is None
    assert spawned == [startup]
    assert live_host.read_json(startup / "rem-live-host.json", {})["pid"] == 42


def test_online_host_is_reused(startup, monkeypatch):
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: True)
    monkeypatch.setattr(live_host, "_spawn", lambda p: pytest.fail("duplicate Host"))
    assert live_host.ensure_online("owner") is None


def test_another_open_reuses_host_that_is_still_starting(startup, monkeypatch):
    write_json(startup / "rem-live-host.json", {"address": "owner", "pid": 42})
    monkeypatch.setattr(live_host, "_alive", lambda pid: True)
    answers = iter([False, True])
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: next(answers))
    monkeypatch.setattr(live_host, "_spawn", lambda p: pytest.fail("duplicate Host"))
    assert live_host.ensure_online("owner") is None


def test_failed_process_names_local_log(startup, monkeypatch):
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: False)
    monkeypatch.setattr(live_host, "_spawn", lambda p: SimpleNamespace(pid=42, args=["python", "-m", "connectonion.cli.main", "ai"], poll=lambda: 1))
    failure = live_host.ensure_online("owner")
    assert "exited" in failure and str(startup / "rem-live-host.log") in failure


def test_timeout_stops_only_the_process_started_by_this_open(startup, monkeypatch):
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: False)
    stopped = []
    process = SimpleNamespace(pid=42, args=["python", "-m", "connectonion.cli.main", "ai"], poll=lambda: None,
                              terminate=lambda: stopped.append(True), wait=lambda **k: 0)
    monkeypatch.setattr(live_host, "_spawn", lambda p: process)
    assert "did not become reachable" in live_host.ensure_online("owner", timeout=0)
    assert stopped == [True]


def test_spawn_uses_selected_environment_and_disables_extra_effects(startup, monkeypatch):
    selected = startup / "chosen.env"
    monkeypatch.setattr("connectonion.environment.explicit_env_file", lambda: selected)
    called = {}
    def popen(command, **kwargs):
        called.update(command=command, **kwargs)
        return SimpleNamespace(pid=42)
    monkeypatch.setattr(live_host.subprocess, "Popen", popen)
    live_host._spawn(startup)
    assert called["command"][:5] == [live_host.sys.executable, "-m", "connectonion.cli.main", "--env-file", str(selected)]
    assert called["command"][-2:] == ["--no-listen", "--no-launch"]
    assert called["start_new_session"] is True
    assert (startup / "rem-live-host.log").stat().st_mode & 0o777 == 0o600


def test_live_open_starts_host_before_returning_url(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, "host_online", lambda address: False)
    asked = []
    monkeypatch.setattr(live_host, "ensure_online", lambda address: asked.append(address))
    result = reader.live_or_snapshot(tmp_path, "owner", live=True, launch=False)
    assert asked == ["owner"]
    assert result["link"] == reader.LIVE_REM_URL.format(address="owner")
    assert result["launched"] is False


def test_reused_pid_with_different_command_is_not_our_host(monkeypatch):
    monkeypatch.setattr(live_host.os, "getuid", lambda: 501)
    monkeypatch.setattr(live_host.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout="501 unrelated-server"))
    assert not live_host._alive({"pid": 42, "command": "-m connectonion.cli.main ai --port 8000 --no-listen --no-launch"})


def test_invalid_startup_state_is_preserved_and_falls_back(startup, monkeypatch):
    from connectonion.rem.config import prepare
    root = startup / "notebook"
    prepare(root)
    state = startup / "rem-live-host.json"
    state.write_text("{invalid")
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: False)
    result = reader.live_or_snapshot(root, "owner", live=True, launch=False)
    assert result["live_startup_failed"] is True
    assert result["link"].startswith("file://")
    assert state.read_text() == "{invalid"


def test_failed_state_write_reaps_the_new_child(startup, monkeypatch):
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: False)
    stopped = []
    process = SimpleNamespace(pid=42, args=["python", "-m", "connectonion.cli.main"],
                              poll=lambda: None, terminate=lambda: stopped.append(True),
                              wait=lambda **k: 0)
    monkeypatch.setattr(live_host, "_spawn", lambda p: process)
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(live_host, "write_json", fail)
    with pytest.raises(OSError, match="disk full"):
        live_host.ensure_online("owner")
    assert stopped == [True]
