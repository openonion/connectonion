"""Explicit live opens own Host startup; snapshots never start an agent."""

import socket
import subprocess
import sys
from contextlib import ExitStack, nullcontext
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import connectonion
from connectonion.rem import live_host, reader
from connectonion.rem.files import write_json
from tests.rem_host_stub import serving

STUB = Path(__file__).resolve().parents[1] / "rem_host_stub.py"


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
    monkeypatch.setattr(live_host, "_spawn", lambda directory, port=None: spawned.append(directory) or process)
    assert live_host.ensure_online("owner") is None
    assert spawned == [startup]
    assert live_host.read_json(startup / "rem-live-host.json", {})["pid"] == 42


def test_online_host_is_reused(startup, monkeypatch):
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: True)
    monkeypatch.setattr(live_host, "_spawn", lambda *a: pytest.fail("duplicate Host"))
    assert live_host.ensure_online("owner") is None


def test_another_open_reuses_host_that_is_still_starting(startup, monkeypatch):
    write_json(startup / "rem-live-host.json", {"address": "owner", "pid": 42})
    monkeypatch.setattr(live_host, "_alive", lambda pid: True)
    answers = iter([False, True])
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: next(answers))
    monkeypatch.setattr(live_host, "_spawn", lambda *a: pytest.fail("duplicate Host"))
    assert live_host.ensure_online("owner") is None


def test_failed_process_names_local_log(startup, monkeypatch):
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: False)
    monkeypatch.setattr(live_host, "_spawn", lambda p, port=None: SimpleNamespace(pid=42, args=["python", "-m", "connectonion.cli.main", "ai"], poll=lambda: 1))
    failure = live_host.ensure_online("owner")
    assert "exited" in failure and str(startup / "rem-live-host.log") in failure


def test_timeout_stops_only_the_process_started_by_this_open(startup, monkeypatch):
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: False)
    stopped = []
    process = SimpleNamespace(pid=42, args=["python", "-m", "connectonion.cli.main", "ai"], poll=lambda: None,
                              terminate=lambda: stopped.append(True), wait=lambda **k: 0)
    monkeypatch.setattr(live_host, "_spawn", lambda p, port=None: process)
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
    if live_host.os.name != "nt":
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
    monkeypatch.setattr(live_host.os, "getuid", lambda: 501, raising=False)
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
    monkeypatch.setattr(live_host, "_spawn", lambda p, port=None: process)
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(live_host, "write_json", fail)
    with pytest.raises(OSError, match="disk full"):
        live_host.ensure_online("owner")
    assert stopped == [True]


# --- After an upgrade the reader is served by the installed version (#2937) ---
# A server is told apart by what its /info says. tests/rem_host_stub.py answers
# it; "0.0.1" stands for whatever was installed before.

def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _answering(port):
    try:
        return httpx.get(f"http://127.0.0.1:{port}/info", timeout=1.0).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture
def old_host(startup):
    """A process with the reader's Host command, recorded as this identity's Host,
    answering /info as `version`: what an upgrade leaves running."""
    started = []

    def run(version="0.0.1"):
        port = _free_port()
        args = [sys.executable, str(STUB), "owner", version, "ai", "--port", str(port), "--no-listen", "--no-launch"]
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL)
        started.append(process)
        while not _answering(port):
            assert process.poll() is None, "the stub Host exited"
        write_json(startup / "rem-live-host.json", {"address": "owner", "pid": process.pid, "port": port,
                                                    "command": " ".join(args[1:])})
        return process, port
    yield run
    for process in started:
        process.kill()
        process.wait()


def _new_host(port, spawned, running=None):
    """Stands for live_host._spawn: notes the port asked for; with `running` (an
    ExitStack), a Host of the installed version then answers on it."""
    def spawn(directory, port_wanted=None):
        spawned.append(port_wanted)
        if running is not None:
            running.enter_context(serving("owner", connectonion.__version__, port=port_wanted or port))
        return SimpleNamespace(pid=4242, poll=lambda: None,
                               args=["python", "-m", "connectonion.cli.main", "ai", "--port", str(port_wanted or port)])
    return spawn


def test_a_server_of_another_version_on_the_saved_port_is_not_the_reader(startup, monkeypatch):
    with serving("owner", "0.0.1") as port:
        monkeypatch.setattr(live_host, "DEFAULT_PORT", port)
        write_json(startup / "rem-live-host.json", {"address": "owner", "pid": 42, "port": port})
        assert live_host.local_reader("owner") is None
    with serving("owner", connectonion.__version__) as port:
        write_json(startup / "rem-live-host.json", {"address": "owner", "pid": 42, "port": port})
        assert live_host.local_reader("owner") == f"http://127.0.0.1:{port}"


def test_an_old_co_ai_on_the_default_port_is_left_alone_and_ours_is_started(startup, monkeypatch):
    """#2937: the recorded Host was dead and port 8000 was a co ai from fifty
    releases back with the same identity. `co rem open` sent the owner there, and
    every page was "Internal Server Error"."""
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: True)   # the old one is on the relay
    monkeypatch.setattr(live_host.os, "kill", lambda *a: pytest.fail("signalled a server that is not ours"))
    spawned = []
    with serving("owner", "0.0.1") as old, serving("owner", connectonion.__version__) as ours:
        monkeypatch.setattr(live_host, "DEFAULT_PORT", old)
        monkeypatch.setattr(live_host, "_spawn", _new_host(ours, spawned))
        url, failure = live_host.ensure_local("owner")
    assert failure is None and url.startswith(f"http://127.0.0.1:{ours}/rem?token=")
    assert spawned == [None]


def test_a_hand_run_co_ai_of_the_installed_version_is_still_the_reader(startup, monkeypatch):
    monkeypatch.setattr(live_host, "_spawn", lambda *a, **k: pytest.fail("started a second Host"))
    with serving("owner", connectonion.__version__) as port:
        monkeypatch.setattr(live_host, "DEFAULT_PORT", port)
        url, failure = live_host.ensure_local("owner")
    assert failure is None and url.startswith(f"http://127.0.0.1:{port}/rem?token=")


@pytest.mark.parametrize("opening", ["start", "ensure_online"])
def test_our_own_host_of_another_version_is_stopped_and_replaced_on_its_port(startup, old_host, monkeypatch, opening):
    """The reader's Host outlives an upgrade: started under 1.9.5, it was still
    serving two days and two releases later, every page marked "Updating…"."""
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: True)   # it announced itself when it started
    process, port = old_host()
    spawned = []
    with ExitStack() as running:
        monkeypatch.setattr(live_host, "_spawn", _new_host(port, spawned, running))
        assert getattr(live_host, opening)("owner") is None   # ensure_online waits for the new one on that port
    assert process.wait(timeout=10) is not None     # stopped: it is the pid the record named
    assert spawned == [port]                        # an open tab keeps its address
    saved = live_host.read_json(startup / "rem-live-host.json", {})
    assert (saved["pid"], saved["port"]) == (4242, port)


def test_a_live_open_replaces_our_own_old_host_although_it_is_online(startup, old_host, monkeypatch):
    """`co rem open --live` asked only whether the identity was online, and the
    Host from before the upgrade was what made it so."""
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: True)
    process, port = old_host()
    with ExitStack() as running:
        monkeypatch.setattr(live_host, "_spawn", _new_host(port, [], running))
        result = reader.live_or_snapshot(startup / "notebook", "owner", live=True, launch=False)
    assert result["link"] == reader.LIVE_REM_URL.format(address="owner")
    assert process.wait(timeout=10) is not None


def test_our_own_host_of_the_installed_version_is_kept(startup, old_host, monkeypatch):
    monkeypatch.setattr(live_host, "_spawn", lambda *a, **k: pytest.fail("replaced a current Host"))
    process, port = old_host(connectonion.__version__)
    assert live_host.start("owner") is None
    assert process.poll() is None and live_host.local_reader("owner") == f"http://127.0.0.1:{port}"


def test_the_page_build_replaces_an_old_host_only_when_it_is_idle(startup, old_host, monkeypatch):
    """A tab opened before the upgrade is served by the old Host, and the owner
    types nothing: the page build that Host starts is the installed code, so it
    is what replaces it. A turn in flight is never cut off for that."""
    from connectonion.network.host.session import Session, SessionStorage
    process, port = old_host()
    spawned = []
    monkeypatch.setattr(live_host, "_spawn", _new_host(port, spawned))
    sessions = SessionStorage(startup / "session_results.jsonl")
    sessions.save(Session(session_id="s1", status="running", prompt="Summarise the week"))
    live_host.renew_idle()
    assert process.poll() is None and spawned == []
    sessions.save(Session(session_id="s1", status="done", prompt="Summarise the week", result="Done."))
    live_host.renew_idle()
    assert process.wait(timeout=10) is not None and spawned == [port]
