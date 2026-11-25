"""`co` keeps the WTF Browser a person can click at the build it runs (#2932).

`co browser --engine wtf` downloads its pinned build under ~/.onionwright and
launches it from there. Nothing ever updated /Applications/WTF Browser.app, so
after an upgrade the copy a person double-clicks was months old and the server
refused it. The launch path now makes that copy the build it just started.

Every bundle here is a fake under tmp_path. Copying and the process list are
faked too, except in the two macOS-only tests at the bottom, which run the real
`ditto` and `ps` against tmp_path so the fakes cannot drift from the tools.
"""

import os
import plistlib
import shutil
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from connectonion.useful_tools.browser_tools import engine

NEW, OLD = "154.0.8037.100", "151.0.7922.222"
NEWER = "155.0.8100.12"     # what a `co` with a later pin already put in /Applications
OURS = "ai.openonion.browser"


def bundle(parent: Path, revision: str, channel: str = "production", bundle_id: str = OURS) -> Path:
    """A fake WTF Browser.app: the two files that identify it and a dummy executable."""
    app = parent / "WTF Browser.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir()
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": bundle_id,
        "CFBundleShortVersionString": revision,
    }))
    (app / "Contents" / "Resources" / "openonion-release-channel").write_text(channel + "\n")
    executable = app / "Contents" / "MacOS" / "WTF Browser"
    executable.write_text(f"#!/bin/sh\n# {bundle_id} {revision} {channel}\n")
    executable.chmod(0o755)
    return app


def revision_of(app: Path) -> str:
    return plistlib.loads((app / "Contents" / "Info.plist").read_bytes())["CFBundleShortVersionString"]


@pytest.fixture
def mac(monkeypatch, tmp_path):
    """A Mac made of tmp_path: Applications, Trash, and the runtime `co` launches."""
    applications = tmp_path / "Applications"
    applications.mkdir()
    runtime = tmp_path / "onionwright" / "runtimes" / "abc"
    runtime.mkdir(parents=True)
    here = SimpleNamespace(
        applications=applications,
        app=applications / "WTF Browser.app",
        trash=tmp_path / "Trash",
        executable=str(bundle(runtime, NEW) / "Contents" / "MacOS" / "WTF Browser"),
        copies=[],
        open_apps=set(),
        process_list_reads=[],
    )

    def copy(source, destination):
        here.copies.append((Path(source), Path(destination)))
        shutil.copytree(source, destination, symlinks=True)

    def is_running(app):
        here.process_list_reads.append(Path(app))
        return Path(app) in here.open_apps

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(engine, "_ditto", copy)
    monkeypatch.setattr(engine, "_app_is_running", is_running)
    return here


def refresh(mac):
    return engine.refresh_applications_app(mac.executable, mac.applications, mac.trash)


def test_no_app_in_applications_gets_the_launched_build(mac):
    said = refresh(mac)

    assert revision_of(mac.app) == NEW
    assert os.access(mac.app / "Contents" / "MacOS" / "WTF Browser", os.X_OK)
    assert len(mac.copies) == 1
    assert not mac.trash.exists()
    assert NEW in said
    assert [p.name for p in mac.applications.iterdir()] == ["WTF Browser.app"]  # nothing half-installed left


@pytest.mark.parametrize("old_revision, old_channel", [
    (OLD, "preview"),       # the Mac in #2932
    (NEW, "preview"),       # same revision, another channel: still not the build co runs
    ("154.0.8037.58", "production"),    # older, though "58" sorts after "100" as text
    (NEWER, "preview"),     # a higher revision of another channel is still not the build co runs
])
def test_an_older_copy_of_ours_goes_to_the_trash_and_the_launched_build_takes_its_place(
    mac, old_revision, old_channel
):
    bundle(mac.applications, old_revision, old_channel)

    said = refresh(mac)

    assert revision_of(mac.app) == NEW
    assert (mac.app / "Contents" / "Resources" / "openonion-release-channel").read_text().strip() == "production"
    [trashed] = mac.trash.iterdir()
    assert trashed.name.startswith(f"WTF Browser {old_revision} {date.today().isoformat()}")
    assert trashed.suffix == ".app"
    assert revision_of(trashed) == old_revision
    assert "Trash" in said and old_revision in said


@pytest.mark.parametrize("newer", [NEWER, "154.0.10000.1"])    # the second is older as text
def test_a_newer_app_on_the_same_channel_is_never_replaced_by_an_older_build(mac, newer):
    # Several `co` installs with different pins share one Mac. The one with the
    # older pin must not put back the build the server refuses.
    bundle(mac.applications, newer)

    said = refresh(mac)

    assert revision_of(mac.app) == newer
    assert not mac.trash.exists()
    assert mac.copies == []
    assert said == f"{mac.applications} has {newer}, newer than the {NEW} co runs, so co left it"


def untouched(path: Path) -> tuple:
    """What a write, a replace or a copy changes, and a read does not.

    Not the whole stat: reading the file is the point of this check, and a read
    moves its access time on Linux (relatime does whenever atime is not after
    mtime, which is so for a file just written). Comparing atime failed main
    whenever bundle() wrote the plist across a second boundary (run 43215710328).
    """
    info = path.stat()
    return info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def test_an_identical_copy_is_left_untouched_and_costs_two_small_reads(mac):
    bundle(mac.applications, NEW)
    before = untouched(mac.app / "Contents" / "Info.plist")

    said = refresh(mac)

    assert said is None
    assert mac.copies == []                 # no 350 MB copy
    assert mac.process_list_reads == []     # not even a look at the process list
    assert untouched(mac.app / "Contents" / "Info.plist") == before
    assert not mac.trash.exists()


def test_an_open_app_is_left_alone_and_the_person_is_told(mac):
    bundle(mac.applications, OLD)
    mac.open_apps.add(mac.app)

    said = refresh(mac)

    assert revision_of(mac.app) == OLD
    assert mac.copies == []
    assert not mac.trash.exists()
    assert "open" in said and OLD in said


def test_an_app_opened_while_the_copy_ran_is_still_left_alone(mac, monkeypatch):
    bundle(mac.applications, OLD)

    def copy_while_the_person_opens_it(source, destination):
        shutil.copytree(source, destination, symlinks=True)
        mac.open_apps.add(mac.app)

    monkeypatch.setattr(engine, "_ditto", copy_while_the_person_opens_it)

    said = refresh(mac)

    assert revision_of(mac.app) == OLD
    assert not mac.trash.exists()
    assert "open" in said
    assert [p.name for p in mac.applications.iterdir()] == ["WTF Browser.app"]


def test_an_app_with_another_bundle_id_is_never_replaced(mac):
    bundle(mac.applications, OLD, bundle_id="com.example.someone-elses-browser")

    said = refresh(mac)

    assert revision_of(mac.app) == OLD
    assert mac.copies == []
    assert not mac.trash.exists()
    assert "not OpenOnion's" in said


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root can write anywhere")
def test_applications_that_cannot_be_written_is_left_alone(mac):
    bundle(mac.applications, OLD)
    mac.applications.chmod(0o555)
    try:
        said = refresh(mac)
    finally:
        mac.applications.chmod(0o755)

    assert revision_of(mac.app) == OLD
    assert mac.copies == []
    assert "cannot write" in said


def test_two_daemons_starting_together_take_turns_at_the_copy(mac):
    import fcntl

    runtime_plist = Path(mac.executable).parent.parent / "Info.plist"
    other = threading.Thread(target=refresh, args=(mac,), name="the-other-daemon")
    with open(runtime_plist, "rb") as the_first_daemon_is_copying:
        fcntl.flock(the_first_daemon_is_copying, fcntl.LOCK_EX)
        other.start()
        other.join(timeout=0.3)
        assert other.is_alive() and mac.copies == []    # waiting, not copying into the same place
    other.join(timeout=10)

    assert not other.is_alive()
    assert revision_of(mac.app) == NEW


def test_a_launched_browser_that_is_not_our_bundle_installs_nothing(mac, tmp_path):
    # Linux artifacts are a bare `chrome`, and test doubles are any path at all.
    said = engine.refresh_applications_app(str(tmp_path / "runtimes" / "abc" / "chrome"), mac.applications, mac.trash)

    assert said is None
    assert list(mac.applications.iterdir()) == []


# --- the launch path ---------------------------------------------------------


def ready_resolution(executable: str):
    prepared = SimpleNamespace(
        ready=True,
        executable=executable,
        capability=SimpleNamespace(
            reason="ready",
            next_action="start",
            artifact=SimpleNamespace(artifact_id="chrome/154.0.8037.100/darwin-x86_64.tar.zst"),
        ),
    )
    client = SimpleNamespace(client_version=engine.MIN_ONIONWRIGHT_VERSION, prepare=lambda revision: prepared)
    return engine.resolve(engine.ONION, token_loader=lambda: "token", client_factory=lambda token, home: client)


def finish_the_copy():
    """The copy runs beside the launch; wait for it the way process exit does."""
    for thread in threading.enumerate():
        if thread.name == "wtf-browser-app":
            thread.join(timeout=10)
            assert not thread.is_alive()


def test_launching_the_wtf_browser_replaces_the_stale_app(mac, monkeypatch):
    bundle(mac.applications, OLD, "preview")
    monkeypatch.setattr(engine, "APPLICATIONS", mac.applications)
    monkeypatch.setitem(sys.modules, "onionwright", SimpleNamespace(launch_paid=lambda *a, **k: "paid-run"))

    launched = engine.launch(ready_resolution(mac.executable), "playwright", "key")
    finish_the_copy()

    assert launched == "paid-run"
    assert revision_of(mac.app) == NEW
    [trashed] = (Path.home() / ".Trash").iterdir()      # conftest gives every test its own home
    assert revision_of(trashed) == OLD


@pytest.mark.asyncio
async def test_the_async_launch_the_daemon_uses_installs_the_app_too(mac, monkeypatch):
    monkeypatch.setattr(engine, "APPLICATIONS", mac.applications)

    async def fake_launch(*args, **kwargs):
        return "async-paid-run"

    monkeypatch.setitem(sys.modules, "onionwright", SimpleNamespace(launch_paid_async=fake_launch))

    launched = await engine.launch_async(ready_resolution(mac.executable), "playwright", "key")
    finish_the_copy()

    assert launched == "async-paid-run"
    assert revision_of(mac.app) == NEW


def test_a_copy_that_fails_cannot_fail_the_launch(mac, monkeypatch):
    bundle(mac.applications, OLD)
    monkeypatch.setattr(engine, "APPLICATIONS", mac.applications)
    monkeypatch.setitem(sys.modules, "onionwright", SimpleNamespace(launch_paid=lambda *a, **k: "paid-run"))
    reported = []
    monkeypatch.setattr(threading, "excepthook", lambda args: reported.append(args.exc_value))

    def disk_full(source, destination):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(engine, "_ditto", disk_full)

    launched = engine.launch(ready_resolution(mac.executable), "playwright", "key")
    finish_the_copy()

    assert launched == "paid-run"                       # the paid session is up and handed back
    assert revision_of(mac.app) == OLD                  # the old app was not moved before the copy existed
    assert [type(error) for error in reported] == [OSError]     # and the failure was shown, not swallowed


def test_off_macos_the_launch_starts_no_copy(mac, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(engine, "APPLICATIONS", mac.applications)
    monkeypatch.setitem(sys.modules, "onionwright", SimpleNamespace(launch_paid=lambda *a, **k: "paid-run"))
    threads_before = set(threading.enumerate())

    launched = engine.launch(ready_resolution(mac.executable), "playwright", "key")

    assert launched == "paid-run"
    assert set(threading.enumerate()) == threads_before
    assert list(mac.applications.iterdir()) == []
    assert mac.copies == [] and mac.process_list_reads == []


# --- what `co browser status` says -------------------------------------------


def status_line(mac, executable=None):
    return engine.applications_app_line(executable, mac.applications)


def test_status_says_there_is_no_app_yet(mac):
    line = status_line(mac)

    assert line.startswith("WTF Browser app: none in ")
    assert "next time" in line


def test_status_says_the_app_is_the_build_co_runs(mac):
    bundle(mac.applications, NEW)

    assert f"has {NEW}, the build co runs" in status_line(mac, mac.executable)


def test_status_names_only_the_revisions_when_the_channel_is_the_same(mac):
    bundle(mac.applications, OLD)

    line = status_line(mac, mac.executable)

    assert f"has {OLD}, co runs {NEW} — " in line
    assert "production" not in line        # a word that tells a person nothing here


def test_status_names_the_channels_too_when_they_differ(mac):
    bundle(mac.applications, OLD, "preview")

    line = status_line(mac, mac.executable)

    assert f"has {OLD} preview" in line
    assert f"co runs {NEW} production" in line
    assert "next time" in line


def test_status_compares_against_the_pinned_revision_before_any_wtf_launch(mac, monkeypatch):
    # A daemon on the free engine has no runtime to read; the pin is what co would run.
    monkeypatch.setattr(engine, "BROWSER_REVISION", NEW)
    bundle(mac.applications, OLD)

    assert f"co runs {NEW}" in status_line(mac)

    shutil.rmtree(mac.app)
    bundle(mac.applications, NEW)

    assert "the build co runs" in status_line(mac)


def test_status_says_a_newer_app_is_left_alone(mac):
    bundle(mac.applications, NEWER)

    assert status_line(mac, mac.executable) == (
        f"WTF Browser app: {mac.applications} has {NEWER}, newer than the {NEW} co runs, so co leaves it"
    )


def test_status_says_a_stale_app_was_left_because_it_is_open(mac):
    bundle(mac.applications, OLD)
    mac.open_apps.add(mac.app)

    line = status_line(mac, mac.executable)

    assert "it is open" in line and OLD in line


def test_status_says_a_foreign_app_is_left_alone(mac):
    bundle(mac.applications, OLD, bundle_id="com.example.someone-elses-browser")

    assert "not OpenOnion's" in status_line(mac, mac.executable)


def test_status_has_no_such_line_off_macos(mac, monkeypatch):
    bundle(mac.applications, OLD)
    monkeypatch.setattr(sys, "platform", "linux")

    assert status_line(mac, mac.executable) is None


class _PaidBrowser:
    _headless = False
    _tab_meta = {}

    def __init__(self, executable):
        self._executable = executable

    def _context_is_alive(self):
        return True

    def tab_status(self):
        return "Tabs (1):\n  *[main]"

    def engine_status(self):
        return {
            "requested_engine": "onion",
            "resolved_engine": "onion",
            "reason": "onion_ready",
            "artifact_id": "chrome/154.0.8037.100/darwin-x86_64.tar.zst",
            "executable": self._executable,
        }


@pytest.mark.asyncio
async def test_co_browser_status_carries_the_line(mac, monkeypatch):
    from connectonion.cli.browser_agent import daemon as mod

    bundle(mac.applications, OLD, "preview")
    monkeypatch.setattr(engine, "APPLICATIONS", mac.applications)
    monkeypatch.setattr(mod, "driver_stealth_status", lambda: ("ok", "1.61.2", "stealth patches present"))
    instance = mod.BrowserDaemon.__new__(mod.BrowserDaemon)
    instance.browser = _PaidBrowser(mac.executable)
    instance.last_command = None

    ok, text = await instance._status_async()

    assert ok is True
    [line] = [line for line in text.splitlines() if line.startswith("WTF Browser app:")]
    assert f"has {OLD} preview" in line and f"co runs {NEW} production" in line


def test_the_suite_never_points_at_the_real_applications():
    # tests/conftest.py moves it for every test, so a launch or a status in any
    # other test file cannot read or replace the operator's real app.
    assert engine.APPLICATIONS != Path("/Applications")
    assert not engine.APPLICATIONS.exists()


# --- the real tools, on macOS only, against tmp_path --------------------------

on_a_mac = pytest.mark.skipif(sys.platform != "darwin", reason="ditto and macOS ps exist only on macOS")


@on_a_mac
def test_real_ditto_copies_a_bundle_with_its_modes_and_symlinks(tmp_path):
    source = bundle(tmp_path / "runtime", NEW)
    (source / "Contents" / "Current").symlink_to("MacOS")

    engine._ditto(source, tmp_path / "Applications" / "WTF Browser.app")

    copied = tmp_path / "Applications" / "WTF Browser.app"
    assert revision_of(copied) == NEW
    assert os.access(copied / "Contents" / "MacOS" / "WTF Browser", os.X_OK)
    assert (copied / "Contents" / "Current").is_symlink()


@on_a_mac
def test_real_process_list_sees_a_process_started_from_inside_the_bundle(tmp_path):
    app = bundle(tmp_path, NEW)
    program = app / "Contents" / "MacOS" / "WTF Browser"

    assert engine._app_is_running(app) is False

    # macOS kills a copied system binary, so sleep runs under the app's name, as ps will show it.
    running = subprocess.Popen([str(program), "30"], executable="/bin/sleep")
    try:
        assert engine._app_is_running(app) is True
    finally:
        running.kill()
        running.wait()
