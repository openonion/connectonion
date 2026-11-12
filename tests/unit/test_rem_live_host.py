"""Explicit live opens own Host startup; snapshots never start an agent."""

import json
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
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
def startup(monkeypatch):
    """The identity folder is this test's own ~/.co, so a Host recorded there is
    one the per-test leak guard stops (tests/host_leak_guard.py)."""
    identity = Path(os.environ["HOME"]) / ".co"
    identity.mkdir(exist_ok=True)
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: identity)
    monkeypatch.setattr("connectonion.cli.co_ai.main._owner_invite_lock", lambda p: nullcontext())
    monkeypatch.setattr(live_host.time, "sleep", lambda seconds: None)
    return identity


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
    monkeypatch.setattr(live_host, "ensure_online", lambda address, **k: asked.append(address))
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

# A Host that does not go on SIGTERM: what the SIGKILL step is for.
DEAF = ("import runpy, signal, sys; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')")


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _answering(port):
    try:
        return httpx.get(f"http://127.0.0.1:{port}/info", timeout=1.0).status_code == 200
    except httpx.HTTPError:
        return False


def _stub(args, port):
    """The stub Host once it answers; None when it exited first (its port was taken meanwhile)."""
    process = subprocess.Popen(args, stdin=subprocess.DEVNULL)
    deadline = time.monotonic() + 20
    while not _answering(port):
        if process.poll() is not None:
            return None
        assert time.monotonic() < deadline, "the stub Host did not answer"
    return process


@pytest.fixture
def old_host(startup):
    """A process with the reader's Host command, recorded as this identity's Host,
    answering /info as `version`: what an upgrade leaves running. `python` is the
    interpreter it runs under (another install's, when it is not this one's)."""
    started = []

    def run(version="0.0.1", python=sys.executable, deaf=False, install=None):
        for _ in range(3):   # a port picked free can be taken before the stub binds it
            port = _free_port()
            args = [python, *(["-c", DEAF] if deaf else []), str(STUB), "owner", version,
                    "ai", "--port", str(port), "--no-listen", "--no-launch"]
            if process := _stub(args, port):
                break
        started.append(process)
        # No "install": a record a 1.9.5 Host wrote, the one an owner has after the upgrade.
        write_json(startup / "rem-live-host.json", {"address": "owner", "pid": process.pid, "port": port,
                                                    "command": " ".join(args[1:]),
                                                    **({"install": install} if install else {})})
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


@pytest.fixture
def untouchable(monkeypatch):
    """Nothing may be signalled and no Host started, until the test's own clean-up."""
    with monkeypatch.context() as patch:
        patch.setattr(live_host.os, "kill", lambda *a: pytest.fail("signalled a process"))
        patch.setattr(live_host, "_spawn", lambda *a, **k: pytest.fail("started a Host"))
        yield


def test_a_server_of_another_version_on_the_saved_port_is_not_the_reader(startup, monkeypatch):
    with serving("owner", "0.0.1") as port:
        monkeypatch.setattr(live_host, "DEFAULT_PORT", port)
        write_json(startup / "rem-live-host.json", {"address": "owner", "pid": 42, "port": port})
        assert live_host.local_reader("owner") is None
    with serving("owner", connectonion.__version__) as port:
        write_json(startup / "rem-live-host.json", {"address": "owner", "pid": 42, "port": port})
        assert live_host.local_reader("owner") == f"http://127.0.0.1:{port}"


def test_an_old_co_ai_on_the_default_port_is_not_used_signalled_or_joined(startup, untouchable, monkeypatch):
    """#2937: the recorded Host was dead and port 8000 was a co ai from fifty
    releases back with the same identity. It is not used, and no Host of ours is
    started beside it: its startup would mark that one's turns interrupted."""
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: True)   # the old one is on the relay
    with serving("owner", "0.0.1") as old:
        monkeypatch.setattr(live_host, "DEFAULT_PORT", old)
        url, notice = live_host.ensure_local("owner")
    assert url is None and isinstance(notice, live_host.Notice)
    assert f"port {old}" in notice and "version 0.0.1" in notice and "`" not in notice   # no command to copy


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
    assert saved["renewed_for"] == live_host.version_on_disk()      # the mark lives with the Host it names
    assert not (startup / "rem-live-host-renewed.json").exists()


def _other_interpreter(tmp_path):
    """This Python under another path, as ps shows a macOS framework Python (Python.app)."""
    other = tmp_path / "other-install" / "bin"
    other.mkdir(parents=True)
    (other / "python").symlink_to(sys.executable)
    return str(other / "python")


def test_a_record_naming_this_install_is_ours_whatever_ps_shows_as_the_interpreter(startup, old_host, tmp_path, monkeypatch):
    """Homebrew and python.org Pythons re-exec Python.app, so ps never shows sys.executable."""
    process, port = old_host(python=_other_interpreter(tmp_path), install=live_host._install())
    monkeypatch.setattr(live_host, "_spawn", _new_host(port, []))
    assert live_host.start("owner") is None
    assert process.wait(timeout=10) is not None


def test_a_record_naming_another_install_is_not_ours_with_the_same_interpreter(startup, old_host, untouchable):
    process, port = old_host(install="/elsewhere/site-packages/connectonion")
    notice = live_host.start("owner")
    assert isinstance(notice, live_host.Notice) and f"port {port}" in notice and process.poll() is None


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


def test_a_host_another_install_started_is_never_signalled_or_used(startup, old_host, untouchable, tmp_path):
    """Two installs on one home share the record. The record's command leaves the
    interpreter out, so another install's Host looked like ours: each open stopped
    the other's. The interpreter ps shows is what tells them apart."""
    other = tmp_path / "other-install" / "bin"
    other.mkdir(parents=True)
    (other / "python").symlink_to(sys.executable)
    process, port = old_host(python=str(other / "python"))
    for opening in (live_host.start, live_host.ensure_online):
        notice = opening("owner")
        assert isinstance(notice, live_host.Notice) and f"port {port}" in notice
    live_host.renew_idle()
    assert process.poll() is None


@pytest.fixture
def unrelated():
    """Some other process of ours, which a recorded pid can come to name."""
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield process
    process.kill()
    process.wait()


def test_a_reused_pid_is_not_signalled_while_another_version_answers_on_its_port(startup, unrelated, untouchable):
    """The recorded pid is now some other process of ours, and an old co ai has the port."""
    with serving("owner", "0.0.1") as port:
        write_json(startup / "rem-live-host.json", {"address": "owner", "pid": unrelated.pid, "port": port,
                                                    "command": f"-m connectonion.cli.main ai --port {port} --no-listen --no-launch"})
        assert isinstance(live_host.start("owner"), live_host.Notice)
        live_host.renew_idle()
    assert unrelated.poll() is None


def test_a_host_that_ignores_sigterm_is_killed(startup, old_host, monkeypatch):
    monkeypatch.setattr(live_host, "STOP_SECONDS", 0.5)
    monkeypatch.setattr(live_host.time, "sleep", time.sleep)   # the waits between signals are real here
    process, port = old_host(deaf=True)
    monkeypatch.setattr(live_host, "_spawn", _new_host(port, []))
    live_host.start("owner")
    assert process.wait(timeout=10) == -signal.SIGKILL


def test_a_port_that_is_not_free_again_gets_the_new_host_elsewhere(startup, old_host, monkeypatch):
    process, port = old_host()
    spawned = []
    monkeypatch.setattr(live_host, "_spawn", _new_host(port, spawned))
    monkeypatch.setattr(live_host, "_free", lambda port: False)
    live_host.start("owner")
    assert process.wait(timeout=10) is not None and spawned == [None]


def test_a_new_host_that_does_not_come_up_on_the_port_is_tried_once_on_a_free_one(startup, old_host, monkeypatch):
    """The port was taken between the check and the bind: the new co ai exits."""
    process, port = old_host()
    tries = []

    def spawn(directory, port_wanted=None):
        tries.append(port_wanted)
        free = port_wanted or _free_port()
        return SimpleNamespace(pid=4240 + len(tries), poll=lambda: 1 if port_wanted else None,
                               args=["python", "-m", "connectonion.cli.main", "ai", "--port", str(free)])
    monkeypatch.setattr(live_host, "_spawn", spawn)
    live_host.renew_idle()
    assert process.wait(timeout=10) is not None
    assert tries == [port, None]                                    # once more, on a free port
    assert live_host.read_json(startup / "rem-live-host.json", {})["pid"] == 4242   # what started is recorded


def test_a_host_that_does_not_stop_ends_in_the_snapshot(startup, old_host, monkeypatch):
    from connectonion.rem.config import prepare
    prepare(startup / "notebook")
    monkeypatch.setattr(live_host, "STOP_SECONDS", 0.2)
    monkeypatch.setattr(live_host, "_spawn", lambda *a, **k: pytest.fail("started a Host beside it"))
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: True)
    process, _ = old_host()
    with monkeypatch.context() as patch:
        patch.setattr(live_host.os, "kill", lambda *a: None)       # the signal does nothing
        result = reader.live_or_snapshot(startup / "notebook", "owner", live=True, launch=False)
    assert result["link"].startswith("file://") and "did not stop" in result["live"]
    assert process.poll() is None


def _unfinished(startup, status="running", age=0.0, prompt="Summarise the week"):
    """A session row the Host wrote `age` seconds ago and has not finished."""
    from connectonion.network.host.session import Session
    moment = time.time() - age
    with open(startup / "session_results.jsonl", "a", encoding="utf-8") as rows:
        rows.write(Session(session_id="s1", status=status, prompt=prompt, created=moment,
                           updated_at=moment).model_dump_json() + "\n")


@pytest.mark.parametrize("status", ["running", "waiting_approval"])
@pytest.mark.parametrize("opening", ["start", "ensure_online", "live_or_snapshot"])
def test_an_explicit_open_leaves_a_busy_old_host_running(startup, old_host, untouchable, monkeypatch, opening, status):
    """A turn, or an approval being waited for, in the Host from before the upgrade
    is not cut off by `co rem open`: the snapshot, and one sentence."""
    monkeypatch.setattr(reader, "host_online", lambda *a, **k: True)
    process, _ = old_host()
    _unfinished(startup, status)
    if opening == "live_or_snapshot":
        from connectonion.rem.config import prepare
        prepare(startup / "notebook")
        said = reader.live_or_snapshot(startup / "notebook", "owner", live=True, launch=False)["live"]
    else:
        said = getattr(live_host, opening)("owner")
    assert said == live_host.BUSY and process.poll() is None


def test_a_scheduled_command_in_flight_keeps_the_old_host(startup, old_host, untouchable):
    """An `exec:` entry writes no session row: only schedule-state.json says it runs."""
    process, _ = old_host()
    (startup / "schedule-state.json").write_text(json.dumps({"nightly-export": {
        "last_run": datetime.now(timezone.utc).isoformat(), "status": "running", "session_id": None}}))
    live_host.renew_idle()
    assert live_host.start("owner") == live_host.BUSY and process.poll() is None


def test_unfinished_work_of_any_age_keeps_the_old_host(startup, old_host, untouchable):
    """The Host marks an earlier Host's unfinished rows interrupted when it starts, so
    an unfinished row is this Host's: an approval waiting overnight, a long turn."""
    process, _ = old_host()
    _unfinished(startup, "waiting_approval", age=2 * 86400)
    live_host.renew_idle()
    assert live_host.start("owner") == live_host.BUSY and process.poll() is None


def test_a_stop_that_failed_does_not_spend_the_one_replacement(startup, old_host, monkeypatch):
    monkeypatch.setattr(live_host, "STOP_SECONDS", 0.2)
    process, port = old_host()
    with monkeypatch.context() as patch:
        patch.setattr(live_host.os, "kill", lambda *a: None)
        with pytest.raises(OSError, match="did not stop"):
            live_host.start("owner")
    monkeypatch.setattr(live_host, "_spawn", _new_host(port, []))
    assert live_host.start("owner") is None
    assert process.wait(timeout=10) is not None


def test_an_explicit_open_does_not_move_a_new_host_that_is_slow_but_running(startup, old_host, monkeypatch):
    process, port = old_host()
    tries = []

    def spawn(directory, port_wanted=None):
        tries.append(port_wanted)
        return SimpleNamespace(pid=4242, poll=lambda: None, terminate=lambda: None, wait=lambda **k: 0,
                               args=["python", "-m", "connectonion.cli.main", "ai", "--port", str(port_wanted)])
    monkeypatch.setattr(live_host, "_spawn", spawn)
    assert "did not become reachable" in live_host.ensure_online("owner", timeout=0.5)
    assert tries == [port]                              # an open tab's address is kept


def test_the_page_build_replaces_an_old_host_only_when_it_is_idle(startup, old_host, monkeypatch):
    """A tab opened before the upgrade is served by the old Host, and the owner
    types nothing: the page build that Host starts is the installed code, so it
    is what replaces it. A turn in flight is never cut off for that."""
    from connectonion.network.host.session import Session, SessionStorage
    process, port = old_host()
    spawned = []
    sessions = SessionStorage(startup / "session_results.jsonl")
    sessions.save(Session(session_id="s1", status="running", prompt="Summarise the week"))
    with ExitStack() as running:
        monkeypatch.setattr(live_host, "_spawn", _new_host(port, spawned, running))
        live_host.renew_idle()
        assert process.poll() is None and spawned == []
        sessions.save(Session(session_id="s1", status="done", prompt="Summarise the week", result="Done."))
        live_host.renew_idle()
    assert process.wait(timeout=10) is not None and spawned == [port]


def test_a_host_still_another_version_after_one_replacement_is_not_replaced_again(startup, old_host, monkeypatch):
    """`python -m` run in a checkout of another version imports that checkout, so its
    replacement is another version again: once per installed version (#1878)."""
    first, port = old_host()
    replacements = []

    def spawn(directory, port_wanted=None):   # what comes up is the old version again
        args = [sys.executable, str(STUB), "owner", "0.0.1", "ai", "--port", str(port_wanted),
                "--no-listen", "--no-launch"]
        replacements.append(_stub(args, port_wanted))
        return replacements[-1]
    monkeypatch.setattr(live_host, "_spawn", spawn)
    try:
        assert live_host.start("owner") is None
        assert first.wait(timeout=10) is not None
        with monkeypatch.context() as patch:
            patch.setattr(live_host.os, "kill", lambda *a: pytest.fail("replaced twice"))
            patch.setattr(live_host, "_spawn", lambda *a, **k: pytest.fail("replaced twice"))
            notice = live_host.start("owner")
            live_host.renew_idle()
        assert isinstance(notice, live_host.Notice) and "not replaced again" in notice
        assert replacements[0].poll() is None
    finally:
        for process in replacements:
            process.kill()
            process.wait()


# A Host's turn that runs `co rem open` (useful_skills/rem-use/SKILL.md): the turn's
# shell is a child of the Host, in a session of its own as useful_tools/bash.py starts it.
INSIDE = '''
import json, subprocess, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
port = int(sys.argv[sys.argv.index("--port") + 1])
class Info(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"address": "owner", "version": "0.0.1"}).encode()
        self.send_response(200); self.send_header("content-length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
Thread(target=HTTPServer(("127.0.0.1", port), Info).serve_forever, daemon=True).start()
sys.stdin.readline()   # once the test has recorded this process as the Host
turn = subprocess.run([sys.executable, sys.argv[1]], start_new_session=True, capture_output=True, text=True)
print(turn.stdout + turn.stderr, flush=True)
'''
OPEN = '''
from contextlib import nullcontext
from pathlib import Path
import connectonion.project, connectonion.cli.co_ai.main as co_ai
from connectonion.rem import live_host
connectonion.project.selected_identity_dir = lambda: Path(%r)
co_ai._owner_invite_lock = lambda p: nullcontext()
live_host._spawn = lambda *a, **k: print("started a Host")
print("said:", live_host.start("owner"))
'''


def test_a_turn_inside_the_old_host_that_runs_co_rem_open_does_not_stop_its_own_host(startup, tmp_path):
    script, opening = tmp_path / "host.py", tmp_path / "open.py"
    script.write_text(INSIDE)
    opening.write_text(OPEN % str(startup))
    port = _free_port()
    args = [sys.executable, str(script), str(opening), "ai", "--port", str(port), "--no-listen", "--no-launch"]
    host = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2])})
    try:
        write_json(startup / "rem-live-host.json", {"address": "owner", "pid": host.pid, "port": port,
                                                    "command": " ".join(args[1:])})
        output = host.communicate("recorded\n", timeout=30)[0]
        assert f"said: {live_host.BUSY}" in output, output
        assert host.returncode == 0            # it ran to the end: nothing stopped it
    finally:
        host.kill()
        host.wait()


def test_on_windows_an_old_host_is_reported_and_nothing_runs_ps(startup, old_host, untouchable, monkeypatch):
    """No ps there, so whether a pid is still our Host cannot be checked
    (live_host._started_here): an old Host is named, never replaced."""
    process, port = old_host()
    with monkeypatch.context() as patch:
        patch.setattr(live_host, "NO_PS", True)        # os.name == "nt"
        patch.setattr(live_host.subprocess, "run", lambda *a, **k: pytest.fail("ran ps"))
        live_host.renew_idle()
        notice = live_host.start("owner")
    assert isinstance(notice, live_host.Notice) and f"port {port}" in notice and process.poll() is None
    assert "did not start" not in notice and "Windows" in notice     # it may well be ours: say what is true
