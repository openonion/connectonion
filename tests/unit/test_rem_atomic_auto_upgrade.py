"""Regression tests for #3363 & #3474: atomic daily auto-upgrade, resilient wrapper, and morning reader scheduler."""

import json
import plistlib
import subprocess
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from connectonion.rem import auto_upgrade


def test_detect_install_method_classifies_uv_tool_editable_venv_and_system(tmp_path):
    # Editable checkout (not in site-packages).
    checkout = tmp_path / "projects" / "connectonion" / "connectonion" / "__init__.py"
    checkout.parent.mkdir(parents=True)
    checkout.write_text("")
    info = auto_upgrade.detect_install_method(
        executable=str(tmp_path / "projects" / "connectonion" / ".venv" / "bin" / "python"),
        package_file=str(checkout),
    )
    assert info["method"] == "editable" and info["supported"] is False

    # uv tool installation (supported).
    uv_root = tmp_path / "uv" / "tools"
    uv_pkg = uv_root / "connectonion" / "lib" / "python3.12" / "site-packages" / "connectonion" / "__init__.py"
    uv_pkg.parent.mkdir(parents=True)
    uv_pkg.write_text("")
    uv_py = uv_root / "connectonion" / "bin" / "python"
    uv_py.parent.mkdir(parents=True)
    uv_py.write_text("")
    info_uv = auto_upgrade.detect_install_method(
        executable=str(uv_py),
        package_file=str(uv_pkg),
        uv_tool_dir=uv_root,
    )
    assert info_uv["method"] == "uv_tool" and info_uv["supported"] is True

    # Project venv (unsupported — never silently modify a project env).
    venv_pkg = tmp_path / "app" / ".venv" / "lib" / "python3.12" / "site-packages" / "connectonion" / "__init__.py"
    venv_pkg.parent.mkdir(parents=True)
    venv_pkg.write_text("")
    info_venv = auto_upgrade.detect_install_method(
        executable=str(tmp_path / "app" / ".venv" / "bin" / "python"),
        package_file=str(venv_pkg),
        uv_tool_dir=uv_root,
    )
    assert info_venv["method"] == "project_venv" and info_venv["supported"] is False


def test_latest_pypi_version_respects_stable_and_preview_channels():
    fake_pypi = {
        "releases": {
            "1.9.6": [{"yanked": False}],
            "1.9.7rc31": [{"yanked": False}],
            "1.9.7rc32": [{"yanked": False}],
            "1.9.7rc99": [{"yanked": True}],
            "1.9.8": [],  # empty release has no artifacts
        }
    }
    assert auto_upgrade.latest_pypi_version("stable", fetch=lambda url: fake_pypi) == "1.9.6"
    assert auto_upgrade.latest_pypi_version("preview", fetch=lambda url: fake_pypi) == "1.9.7rc32"


def test_failed_staged_upgrade_keeps_live_install_untouched_and_records_failure(tmp_path, monkeypatch):
    home = tmp_path / "home"
    co_dir = home / ".co"
    co_dir.mkdir(parents=True)
    uv_tools = tmp_path / "uv_tools"
    uv_bin = tmp_path / "uv_bin"
    live_tool = uv_tools / "connectonion"
    (live_tool / "bin").mkdir(parents=True)
    live_co = uv_bin / "co"
    uv_bin.mkdir(parents=True)
    live_co.write_text("#!/bin/sh\necho 1.9.7rc31\n")
    live_co.chmod(0o700)

    monkeypatch.setattr(auto_upgrade, "detect_install_method", lambda **kw: {
        "method": "uv_tool", "supported": True, "uv_tool_dir": str(uv_tools), "uv_bin_dir": str(uv_bin),
    })
    monkeypatch.setattr(auto_upgrade, "current_version", lambda: "1.9.7rc31")
    monkeypatch.setattr(auto_upgrade, "find_uv", lambda: "/usr/bin/uv")

    def failing_run(cmd, **kwargs):
        return CompletedProcess(cmd, 1, "", "network timeout downloading wheel")

    result = auto_upgrade.run_atomic_upgrade(
        home=home,
        root=co_dir / "rem",
        run=failing_run,
        fetch=lambda url: {"releases": {"1.9.7rc32": [{"yanked": False}]}},
    )
    assert result["outcome"] == "failed"
    assert "network timeout" in result["error"]
    # Live installation is completely untouched.
    assert live_co.is_file()
    assert live_tool.is_dir()
    state = auto_upgrade.read_upgrade_state(home)
    assert state["outcome"] == "failed"
    assert state["target"] == "1.9.7rc32"


def test_successful_atomic_upgrade_stages_verifies_swaps_and_prewarms_html(tmp_path, monkeypatch):
    home = tmp_path / "home"
    co_dir = home / ".co"
    rem_root = co_dir / "rem"
    rem_root.mkdir(parents=True)
    (rem_root / "config.yaml").write_text("version: 1\n")
    uv_tools = tmp_path / "uv_tools"
    uv_bin = tmp_path / "uv_bin"
    (uv_tools / "connectonion" / "bin").mkdir(parents=True)
    uv_bin.mkdir(parents=True)
    (uv_bin / "co").write_text("#!/bin/sh\necho old\n")

    monkeypatch.setattr(auto_upgrade, "detect_install_method", lambda **kw: {
        "method": "uv_tool", "supported": True, "uv_tool_dir": str(uv_tools), "uv_bin_dir": str(uv_bin),
    })
    monkeypatch.setattr(auto_upgrade, "current_version", lambda: "1.9.7rc31")
    monkeypatch.setattr(auto_upgrade, "find_uv", lambda: "/usr/bin/uv")

    monkeypatch.setenv("UV_INDEX", "https://alternate.invalid/simple")
    monkeypatch.setenv("UV_FIND_LINKS", "/alternate/wheels")
    prewarmed = []
    monkeypatch.setattr(auto_upgrade, "prewarm_reader", lambda root, python_bin, **kw: prewarmed.append((root, python_bin)) or "ready")

    commands = []

    def fake_run(cmd, **kwargs):
        commands.append((list(cmd), dict(kwargs.get("env") or {})))
        env = kwargs.get("env") or {}
        if cmd[:3] == ["/usr/bin/uv", "tool", "install"]:
            tdir = Path(env["UV_TOOL_DIR"]) / "connectonion" / "bin"
            bdir = Path(env["UV_TOOL_BIN_DIR"])
            tdir.mkdir(parents=True, exist_ok=True)
            bdir.mkdir(parents=True, exist_ok=True)
            (tdir / "python").write_text("#!/bin/sh\nexit 0\n")
            (bdir / "co").write_text("#!/bin/sh\necho 1.9.7rc32\n")
            return CompletedProcess(cmd, 0, "Installed connectonion==1.9.7rc32", "")
        return CompletedProcess(cmd, 0, "1.9.7rc32\n", "")

    result = auto_upgrade.run_atomic_upgrade(
        home=home,
        root=rem_root,
        run=fake_run,
        fetch=lambda url: {"releases": {"1.9.7rc32": [{"yanked": False}]}},
    )
    assert result["outcome"] == "upgraded"
    assert result["from"] == "1.9.7rc31"
    assert result["to"] == "1.9.7rc32"
    assert result["prewarmed"] is True
    assert len(prewarmed) == 1
    # First uv tool install targeted a staging dir, NOT the live uv_tools dir.
    first_uv_env = next(env for cmd, env in commands if cmd[:3] == ["/usr/bin/uv", "tool", "install"])
    assert Path(first_uv_env["UV_TOOL_DIR"]) != uv_tools
    for cmd, env in commands:
        if cmd[:3] == ["/usr/bin/uv", "tool", "install"]:
            assert "--no-config" in cmd
            assert cmd[cmd.index("--default-index") + 1] == "https://pypi.org/simple"
            assert cmd[-1] == "connectonion==1.9.7rc32"
            assert "UV_INDEX" not in env and "UV_FIND_LINKS" not in env



def test_atomic_upgrade_respects_pin_and_active_rem_lock(tmp_path, monkeypatch):
    home = tmp_path / "home"
    co_dir = home / ".co"
    co_dir.mkdir(parents=True)
    auto_upgrade.write_upgrade_config(
        {**auto_upgrade.default_upgrade_config(), "channel": "pinned", "pinned_version": "1.9.7rc31"},
        home=home,
    )
    monkeypatch.setattr(auto_upgrade, "detect_install_method", lambda **kw: {"method": "uv_tool", "supported": True})
    monkeypatch.setattr(auto_upgrade, "current_version", lambda: "1.9.7rc31")
    res_pin = auto_upgrade.run_atomic_upgrade(home=home, root=co_dir / "rem")
    assert res_pin["outcome"] == "pinned"

    # Unpin and simulate active REM exec-turn.lock -> deferred cleanly.
    auto_upgrade.write_upgrade_config(
        {**auto_upgrade.default_upgrade_config(), "channel": "preview", "pinned_version": None},
        home=home,
    )
    monkeypatch.setattr(auto_upgrade, "rem_turn_active", lambda root: True)
    res_busy = auto_upgrade.run_atomic_upgrade(
        home=home,
        root=co_dir / "rem",
        fetch=lambda url: {"releases": {"1.9.7rc32": [{"yanked": False}]}},
    )
    assert res_busy["outcome"] == "deferred_busy"


def test_resilient_wrapper_skips_cleanly_without_traceback_when_connectonion_missing(tmp_path):
    log = tmp_path / "launchd.log"
    cmd = auto_upgrade.resilient_shell_command(
        ["/nonexistent/bin/co", "rem", "sync", "--scheduled"],
        log_path=log,
    )
    done = subprocess.run(cmd, capture_output=True, text=True)
    assert done.returncode == 0
    assert "Traceback" not in done.stderr and "Traceback" not in done.stdout
    assert "skipping" in log.read_text(encoding="utf-8").lower()


def test_daily_upgrade_and_morning_schedulers_are_independent_idempotent_and_respect_no_fake_habit(tmp_path):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        return CompletedProcess(cmd, 0, "", "")

    up = auto_upgrade.DailyUpgradeScheduler(agents_dir=tmp_path / "agents", uid=501, run=fake_run,
                                            command=["/bin/co"], platform="darwin")
    info = up.install(hour=1, minute=0)
    assert info["installed"] is True
    assert info["time"] == "01:00"
    plist = plistlib.loads(Path(info["plist"]).read_bytes())
    assert plist["StartCalendarInterval"] == {"Hour": 1, "Minute": 0}
    # Idempotent re-install produces zero duplicates.
    up.install(hour=1, minute=0)
    assert len(list((tmp_path / "agents").glob(f"{auto_upgrade.UPGRADE_LABEL}*.plist"))) == 1
    assert up.uninstall() is True
    assert not Path(info["plist"]).exists()

    # Morning scheduler refuses to pretend a default time is a learned habit.
    cfg = auto_upgrade.default_upgrade_config()
    assert cfg["morning_open"]["time"] is None
    assert cfg["morning_open"]["source"] == "none"

    morning = auto_upgrade.MorningReaderScheduler(agents_dir=tmp_path / "agents", uid=501, run=fake_run,
                                                  command=["/bin/co"], platform="darwin")
    minfo = morning.install(hour=8, minute=45)
    assert minfo["installed"] is True
    assert minfo["time"] == "08:45"
    assert morning.uninstall() is True


def test_installed_reader_failure_is_reported_and_retried_without_reinstall(tmp_path, monkeypatch):
    root = tmp_path / ".co" / "rem"
    root.mkdir(parents=True)
    (root / "config.yaml").touch()
    monkeypatch.setattr(auto_upgrade, "detect_install_method", lambda: {
        "supported": True, "uv_tool_dir": str(tmp_path / "tools"),
    })
    monkeypatch.setattr(auto_upgrade, "current_version", lambda: "1.9.7rc33")
    previous = auto_upgrade._upgrade_result("1.9.7rc32", "1.9.7rc33", "preview", root)
    auto_upgrade.write_upgrade_state({**previous, "phase": "reader"}, tmp_path)
    fetch = lambda url: {"releases": {"1.9.7rc33": [{"yanked": False}]}}

    def worker(cmd, **kwargs):
        assert cmd[1:3] == ["-I", "-c"]
        assert cmd[-2:] == [str(root), str(root.parent)]
        return CompletedProcess(cmd, 1, "", "sqlite error: cannot rebuild index")

    failed = auto_upgrade.run_atomic_upgrade(home=tmp_path, run=worker, fetch=fetch)
    assert failed["outcome"] == "failed" and failed["phase"] == "reader"
    assert "cannot rebuild index" in failed["error"]
    assert auto_upgrade.read_upgrade_state(tmp_path) == failed

    ready = auto_upgrade.run_atomic_upgrade(home=tmp_path, fetch=fetch,
        run=lambda cmd, **kw: CompletedProcess(cmd, 0, "restarted\n", ""))
    assert ready["outcome"] == "upgraded" and ready["reader"] == "restarted"


def test_scheduled_upgrade_obeys_opt_out_before_network_or_install(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_upgrade, "current_version", lambda: "1.9.7rc33")
    monkeypatch.setattr(auto_upgrade, "detect_install_method", lambda: pytest.fail("probed installation"))
    auto_upgrade.write_upgrade_config({**auto_upgrade.default_upgrade_config(), "enabled": False}, tmp_path)
    assert auto_upgrade.run_atomic_upgrade(home=tmp_path, scheduled=True)["outcome"] == "disabled"


def test_prewarm_considers_host_only_after_successful_reader_preparation(tmp_path, monkeypatch):
    from connectonion.rem import live_host, reader

    monkeypatch.setattr(live_host, "renew_idle", lambda **kw: pytest.fail("restarted during reader preparation"))
    monkeypatch.setattr(reader, "refresh", lambda root: False)
    assert auto_upgrade._prewarm_installed_reader(tmp_path, tmp_path) == "build_busy"

    def fail_refresh(root):
        raise auto_upgrade.RemError("index migration failed")

    monkeypatch.setattr(reader, "refresh", fail_refresh)
    with pytest.raises(auto_upgrade.RemError, match="index migration failed"):
        auto_upgrade._prewarm_installed_reader(tmp_path, tmp_path)


def test_nightly_waits_for_the_active_notebook_turn(tmp_path, monkeypatch):
    active = iter((True, True, False))
    sleeps = []
    monkeypatch.setattr(auto_upgrade, "rem_turn_active", lambda root: next(active))
    monkeypatch.setattr(auto_upgrade.time, "sleep", sleeps.append)
    assert auto_upgrade._wait_for_idle_notebook(tmp_path, scheduled=True)
    assert sleeps == [5, 5]
