"""Regression tests for rc33: #3480 late-wave task gating + DST/tz handling & #3317 macOS Aqua LaunchAgent."""

from __future__ import annotations

import json
import os
import plistlib
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app as cli_app
from connectonion.rem import auto_upgrade, live_host, native_round, schedule
from connectonion.rem.config import PROFILES, default_config, prepare, set_config
from connectonion.rem.files import write_json


# ---------------------------------------------------------------------------
# #3480: overnight_wave_policy & native_round task gating + DST / timezone
# ---------------------------------------------------------------------------


def _overnight_config(tz: str = "Australia/Melbourne") -> dict:
    cfg = default_config()
    cfg["schedule"].update(
        profile="overnight",
        times=list(PROFILES["overnight"]),
        timezone=tz,
    )
    return cfg


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (21, 59, "stop"),
        (22, 0, "full"),
        (22, 30, "full"),
        (23, 45, "full"),
        (0, 0, "full"),
        (0, 59, "full"),
        (1, 0, "light_only"),
        (1, 30, "light_only"),
        (2, 30, "light_only"),
        (2, 39, "light_only"),
        (2, 40, "stop"),
        (2, 59, "stop"),
        (3, 0, "stop"),
        (5, 30, "stop"),
        (8, 0, "stop"),
        (14, 0, "stop"),
    ],
)
def test_overnight_wave_policy_boundaries_in_local_timezone(hour, minute, expected):
    tz = "Australia/Melbourne"
    cfg = _overnight_config(tz)
    local_dt = datetime(2026, 11, 27, hour, minute, tzinfo=ZoneInfo(tz))
    # Verify both local-aware and UTC-converted datetimes yield the exact same policy.
    assert native_round.overnight_wave_policy(cfg, now=local_dt) == expected
    assert native_round.overnight_wave_policy(cfg, now=local_dt.astimezone(timezone.utc)) == expected


def test_overnight_wave_policy_leaves_default_and_dense_untouched():
    for profile in ("default", "dense"):
        cfg = default_config()
        cfg["schedule"]["profile"] = profile
        cfg["schedule"]["times"] = list(PROFILES[profile])
        cfg["schedule"]["timezone"] = "Australia/Melbourne"
        for hour, minute in ((1, 30), (2, 45), (3, 0), (10, 0), (22, 0)):
            dt = datetime(2026, 11, 27, hour, minute, tzinfo=ZoneInfo("Australia/Melbourne"))
            assert native_round.overnight_wave_policy(cfg, now=dt) == "full"


def test_overnight_wave_policy_handles_dst_spring_forward_and_fall_back():
    # Australia/Melbourne spring forward: 2026-10-04 02:00 AEST -> 03:00 AEDT
    tz = ZoneInfo("Australia/Melbourne")
    cfg = _overnight_config("Australia/Melbourne")

    # 01:59 AEST (UTC+10) is 15:59 UTC on 2026-10-03 -> still light_only.
    before_jump = datetime(2026, 10, 3, 15, 59, tzinfo=timezone.utc)
    assert before_jump.astimezone(tz).strftime("%H:%M") == "01:59"
    assert native_round.overnight_wave_policy(cfg, now=before_jump) == "light_only"

    # 1 minute later: 03:00 AEDT (UTC+11) -> immediately "stop", zero spillover past 03:00!
    after_jump = datetime(2026, 10, 3, 16, 0, tzinfo=timezone.utc)
    assert after_jump.astimezone(tz).strftime("%H:%M") == "03:00"
    assert native_round.overnight_wave_policy(cfg, now=after_jump) == "stop"

    # Australia/Melbourne fall back: 2026-04-05 03:00 AEDT -> 02:00 AEST
    # 02:45 AEDT (15:45 UTC) -> stop; 02:15 AEST (16:15 UTC) -> light_only; 02:45 AEST (16:45 UTC) -> stop.
    assert native_round.overnight_wave_policy(cfg, now=datetime(2026, 4, 4, 15, 45, tzinfo=timezone.utc)) == "stop"
    assert native_round.overnight_wave_policy(cfg, now=datetime(2026, 4, 4, 16, 15, tzinfo=timezone.utc)) == "light_only"
    assert native_round.overnight_wave_policy(cfg, now=datetime(2026, 4, 4, 16, 45, tzinfo=timezone.utc)) == "stop"


def _minimal_cursor() -> dict:
    return {
        "phase": "daily-update",
        "started_at": "2026-11-27T00:00:00+11:00",
        "slot": "2026-11-27T01:30:00+11:00",
        "batch": {"done": False, "record": {"extracted": False}, "items": [{"text": "mail"}], "leads": [None], "progress_before": {}},
        "batch_index": 0,
        "summaries": [{"key": "sess-1", "record": "projects/demo.md"}],
        "jobs": [{"record": "people/alice.md", "kind": "person"}],
        "job_index": 0,
        "current": None,
        "changed": [],
        "same_left": 3,
        "same_new_left": 10,
        "translations": [],
        "translated": 0,
        "run": {"id": "run_00000000000000000000000000000001"},
    }


def test_prepare_task_stops_all_new_model_turns_after_0240_on_overnight(tmp_path, monkeypatch):
    prepare(tmp_path)
    cfg = _overnight_config("Australia/Melbourne")
    cursor = _minimal_cursor()
    monkeypatch.setattr(
        native_round.service,
        "now",
        lambda: datetime(2026, 11, 27, 2, 40, tzinfo=ZoneInfo("Australia/Melbourne")),
    )
    # Fail loudly if any task builder were called after 02:40.
    monkeypatch.setattr(native_round, "prepare_batch", lambda *a, **k: pytest.fail("batch called after 02:40"))
    monkeypatch.setattr(native_round, "_job_turn", lambda *a, **k: pytest.fail("investigation called after 02:40"))
    monkeypatch.setattr(native_round, "_summary_turn", lambda *a, **k: pytest.fail("summary called after 02:40"))

    result = native_round.prepare_task(tmp_path, cursor, cfg, tmp_path / "taskdir")
    assert isinstance(result, dict) and "stop" in result
    assert "02:40" in result["stop"] or "03:00" in result["stop"]


def test_prepare_task_light_only_blocks_long_work_and_allows_bounded_light_tasks(tmp_path, monkeypatch):
    prepare(tmp_path)
    cfg = _overnight_config("Australia/Melbourne")
    monkeypatch.setattr(
        native_round.service,
        "now",
        lambda: datetime(2026, 11, 27, 1, 30, tzinfo=ZoneInfo("Australia/Melbourne")),
    )

    # Long stages MUST NOT be invoked during 01:00-02:40 light_only window.
    monkeypatch.setattr(native_round, "prepare_batch", lambda *a, **k: pytest.fail("prepare_batch must be blocked"))
    monkeypatch.setattr(native_round, "_job_turn", lambda *a, **k: pytest.fail("investigation must be blocked"))
    monkeypatch.setattr(native_round, "prepare_abstract", lambda *a, **k: pytest.fail("abstract must be blocked"))
    monkeypatch.setattr(native_round, "_closing_tags", lambda *a, **k: pytest.fail("tags must be blocked"))
    monkeypatch.setattr(native_round, "prepare_tag_node", lambda *a, **k: pytest.fail("tag-node must be blocked"))
    monkeypatch.setattr("connectonion.rem.tasks.auto_dispatch", lambda *a, **k: pytest.fail("auto_dispatch must be blocked"))
    monkeypatch.setattr("connectonion.rem.same_person.candidates", lambda *a, **k: [])
    monkeypatch.setattr("connectonion.rem.night.prepare", lambda *a, **k: [])

    # 1) Session summary IS allowed in light_only.
    cursor = _minimal_cursor()
    monkeypatch.setattr(
        native_round,
        "_summary_turn",
        lambda *a, **k: {"handler": "sessions", "stage": "sessions-summary", "task": {}},
    )
    res_summary = native_round.prepare_task(tmp_path, cursor, cfg, tmp_path / "t1")
    assert res_summary["stage"] == "sessions-summary"

    # 2) Translation IS allowed when summaries are done.
    cursor = _minimal_cursor()
    monkeypatch.setattr(native_round, "_summary_turn", lambda *a, **k: None)
    monkeypatch.setattr(
        native_round,
        "_closing_translation",
        lambda *a, **k: {"handler": "translate", "stage": "translate", "task": {}},
    )
    res_tr = native_round.prepare_task(tmp_path, cursor, cfg, tmp_path / "t2")
    assert res_tr["stage"] == "translate"

    # 3) Reply draft IS allowed.
    cursor = _minimal_cursor()
    monkeypatch.setattr("connectonion.rem.night.prepare", lambda *a, **k: [{"id": "mail-1"}])
    monkeypatch.setattr("connectonion.rem.drafts.prepare", lambda *a, **k: {"prompt": "draft"})
    res_draft = native_round.prepare_task(tmp_path, cursor, cfg, tmp_path / "t3")
    assert res_draft["stage"] == "reply-draft"

    # 4) Same-person check IS allowed.
    cursor = _minimal_cursor()
    monkeypatch.setattr("connectonion.rem.night.prepare", lambda *a, **k: [])
    monkeypatch.setattr("connectonion.rem.same_person.candidates", lambda *a, **k: [("people/a.md", "people/b.md")])
    monkeypatch.setattr("connectonion.rem.same_person.prepare", lambda *a, **k: {"prompt": "same"})
    res_same = native_round.prepare_task(tmp_path, cursor, cfg, tmp_path / "t4")
    assert res_same["stage"] == "same-person"

    # 5) When no light tasks wait, stops cleanly WITHOUT marking queued investigations done.
    cursor = _minimal_cursor()
    monkeypatch.setattr("connectonion.rem.same_person.candidates", lambda *a, **k: [])
    monkeypatch.setattr(native_round, "_summary_turn", lambda *a, **k: None)
    monkeypatch.setattr(native_round, "_closing_translation", lambda *a, **k: None)
    res_idle = native_round.prepare_task(tmp_path, cursor, cfg, tmp_path / "t5")
    assert "stop" in res_idle
    assert not cursor.get("done")


def test_deepening_slot_is_blocked_after_0100_on_overnight(tmp_path, monkeypatch):
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.profile", "overnight", "schedule.timezone", "Australia/Melbourne"])
    monkeypatch.setattr(
        native_round.service,
        "now",
        lambda: datetime(2026, 11, 27, 1, 15, tzinfo=ZoneInfo("Australia/Melbourne")),
    )
    monkeypatch.setattr(schedule, "deepen_round", lambda *a, **k: pytest.fail("deepen started after 01:00"))
    assert schedule._depth_slot(tmp_path, lambda root, cursor: True) is None


# ---------------------------------------------------------------------------
# #3317: macOS gui/$UID LaunchAgent for REM live Host, auto_upgrade, stop, doctor
# ---------------------------------------------------------------------------


def test_install_kickstart_and_uninstall_host_agent_plist_in_gui_domain(tmp_path):
    co_dir = tmp_path / ".co"
    agents_dir = tmp_path / "Library" / "LaunchAgents"
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:2] == ["launchctl", "print"]:
            return CompletedProcess(cmd, 0, "gui/501/ai.openonion.rem-host = {\n\tpid = 42424\n\tstate = running\n}\n", "")
        return CompletedProcess(cmd, 0, "", "")

    installed = live_host.install_host_agent(
        co_dir,
        port=18765,
        python_bin="/Users/owner/.local/share/uv/tools/connectonion/bin/python",
        agents_dir=agents_dir,
        uid=501,
        run=fake_run,
        platform="darwin",
    )
    assert installed["installed"] is True
    assert installed["bootstrapped"] is True
    assert installed["label"] == "ai.openonion.rem-host"
    assert installed["domain"] == "gui/501"
    plist_path = Path(installed["plist"])
    assert plist_path == agents_dir / "ai.openonion.rem-host.plist"
    assert plist_path.stat().st_mode & 0o777 == 0o600

    data = plistlib.loads(plist_path.read_bytes())
    assert data["Label"] == "ai.openonion.rem-host"
    assert data["LimitLoadToSessionType"] == "Aqua"
    assert data["ProcessType"] == "Interactive"
    assert data["ProgramArguments"][0] == "/Users/owner/.local/share/uv/tools/connectonion/bin/python"
    assert "--port" in data["ProgramArguments"] and "18765" in data["ProgramArguments"]
    assert ["launchctl", "bootstrap", "gui/501", str(plist_path)] in calls

    kicked = live_host.kickstart_host_agent(uid=501, agents_dir=agents_dir, run=fake_run, platform="darwin")
    assert kicked["ok"] is True
    assert kicked["pid"] == 42424
    assert ["launchctl", "kickstart", "-k", "gui/501/ai.openonion.rem-host"] in calls

    removed = live_host.uninstall_host_agent(uid=501, agents_dir=agents_dir, run=fake_run, platform="darwin")
    assert removed is True
    assert not plist_path.exists()
    assert ["launchctl", "bootout", "gui/501/ai.openonion.rem-host"] in calls


def test_kickstart_bootstraps_and_retries_when_plist_not_yet_loaded(tmp_path):
    agents_dir = tmp_path / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True)
    plist_path = agents_dir / f"{live_host.REM_HOST_LABEL}.plist"
    plist_path.write_text("<plist/>", encoding="utf-8")

    attempts = {"kickstart": 0}
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(list(cmd))
        if cmd[:2] == ["launchctl", "kickstart"]:
            attempts["kickstart"] += 1
            return CompletedProcess(cmd, 113 if attempts["kickstart"] == 1 else 0, "", "Could not find service")
        if cmd[:2] == ["launchctl", "print"]:
            return CompletedProcess(cmd, 0, "pid = 7777\n", "")
        return CompletedProcess(cmd, 0, "", "")

    res = live_host.kickstart_host_agent(uid=501, agents_dir=agents_dir, run=fake_run, platform="darwin")
    assert res["ok"] is True
    assert res["pid"] == 7777
    assert ["launchctl", "bootstrap", "gui/501", str(plist_path)] in seen
    assert attempts["kickstart"] == 2


def test_launch_and_renew_use_host_agent_in_aqua_and_fallback_when_launchctl_unavailable(tmp_path, monkeypatch):
    co_dir = tmp_path / ".co"
    co_dir.mkdir(parents=True)
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: co_dir)
    monkeypatch.setattr("connectonion.cli.co_ai.main._owner_invite_lock", lambda p: nullcontext())
    monkeypatch.setattr(live_host, "_use_host_agent", lambda: True)
    monkeypatch.setattr(live_host, "launch_session", lambda: "Background")  # caller is a Background shell!

    installed_ports: list[int | None] = []
    monkeypatch.setattr(
        live_host,
        "install_host_agent",
        lambda directory, port=None, **kw: installed_ports.append(port) or {
            "installed": True,
            "bootstrapped": True,
            "label": live_host.REM_HOST_LABEL,
            "domain": "gui/501",
            "plist": str(tmp_path / "ai.openonion.rem-host.plist"),
            "port": port or 18765,
            "command": ["/bin/py", "-m", "connectonion.cli.main", "ai", "--port", str(port or 18765), "--no-listen", "--no-launch"],
        },
    )
    monkeypatch.setattr(
        live_host,
        "kickstart_host_agent",
        lambda **kw: {"ok": True, "pid": 9090, "target": "gui/501/ai.openonion.rem-host"},
    )
    monkeypatch.setattr(live_host, "_spawn", lambda *a, **k: pytest.fail("should use LaunchAgent, not direct _spawn"))

    proc = live_host._launch(co_dir, "0xowner", port=18765)
    assert proc.pid == 9090
    saved = live_host.read_json(co_dir / "rem-live-host.json", {})
    assert saved["session"] == "Aqua"
    assert saved["via_launch_agent"] is True
    assert saved["label"] == "ai.openonion.rem-host"
    assert saved["port"] == 18765

    # Now simulate launchctl kickstart failing -> graceful fallback to direct _spawn!
    monkeypatch.setattr(live_host, "kickstart_host_agent", lambda **kw: {"ok": False, "error": "no gui domain"})
    fallback_calls = []
    monkeypatch.setattr(
        live_host,
        "_spawn",
        lambda d, port=None: fallback_calls.append(port) or SimpleNamespace(
            pid=5555, args=["python", "-m", "connectonion.cli.main", "ai", "--port", str(port or 18765)], poll=lambda: None
        ),
    )
    proc_fb = live_host._launch(co_dir, "0xowner", port=18765)
    assert proc_fb.pid == 5555
    assert fallback_calls == [18765]
    saved_fb = live_host.read_json(co_dir / "rem-live-host.json", {})
    assert saved_fb["session"] == "Background"
    assert "via_launch_agent" not in saved_fb


def test_renew_idle_restarts_host_inside_aqua_via_launch_agent(tmp_path, monkeypatch):
    co_dir = tmp_path / ".co"
    co_dir.mkdir(parents=True)
    write_json(co_dir / "rem-live-host.json", {
        "address": "0xowner", "pid": 1111, "port": 18765,
        "command": "-m connectonion.cli.main ai --port 18765 --no-listen --no-launch",
        "install": live_host._install(), "session": "Background",
    })
    monkeypatch.setattr("connectonion.project.selected_identity_dir", lambda: co_dir)
    monkeypatch.setattr("connectonion.cli.co_ai.main._owner_invite_lock", lambda p: nullcontext())
    monkeypatch.setattr(live_host, "_use_host_agent", lambda: True)
    monkeypatch.setattr(live_host, "launch_session", lambda: "Background")
    monkeypatch.setattr(live_host, "_upgrade", lambda *a, **k: live_host.REPLACE)
    retired = []
    monkeypatch.setattr(live_host, "_retire", lambda saved: retired.append(saved["pid"]))
    monkeypatch.setattr(live_host, "_free", lambda port: True)
    monkeypatch.setattr(live_host, "_exits", lambda proc, addr, wait: False)
    kicks = []
    monkeypatch.setattr(
        live_host,
        "install_host_agent",
        lambda directory, port=None, **kw: {
            "installed": True,
            "bootstrapped": True,
            "label": live_host.REM_HOST_LABEL,
            "domain": "gui/501",
            "plist": str(tmp_path / "ai.openonion.rem-host.plist"),
            "port": port or 18765,
            "command": ["/bin/py", "-m", "connectonion.cli.main", "ai", "--port", str(port or 18765), "--no-listen", "--no-launch"],
        },
    )
    monkeypatch.setattr(
        live_host,
        "kickstart_host_agent",
        lambda **kw: kicks.append(True) or {"ok": True, "pid": 9999, "target": "gui/501/ai.openonion.rem-host"},
    )
    monkeypatch.setattr(live_host, "_spawn", lambda *a, **k: pytest.fail("renew_idle should use LaunchAgent"))

    # Second call to due() inside lock returns saved once, then None on next check if needed:
    calls = iter([live_host.REPLACE, live_host.REPLACE])
    monkeypatch.setattr(live_host, "_upgrade", lambda *a, **k: next(calls, None))

    live_host.renew_idle()
    assert retired == [1111]
    assert kicks == [True]
    saved = live_host.read_json(co_dir / "rem-live-host.json", {})
    assert saved["pid"] == 9999
    assert saved["session"] == "Aqua"
    assert saved["via_launch_agent"] is True
    assert saved["renewed_for"] == live_host.version_on_disk()


def test_auto_upgrade_leaves_busy_aqua_host_running(tmp_path, monkeypatch):
    home = tmp_path / "home"
    co_dir = home / ".co"
    rem_root = co_dir / "rem"
    rem_root.mkdir(parents=True)
    (rem_root / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    agents_dir = home / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True)
    plist_path = agents_dir / f"{live_host.REM_HOST_LABEL}.plist"
    plist_path.write_bytes(plistlib.dumps({"Label": live_host.REM_HOST_LABEL, "ProgramArguments": ["/old/python"]}))
    write_json(co_dir / "rem-live-host.json", {"address": "0xowner", "pid": 111, "port": 18765, "session": "Background"})

    uv_tools = tmp_path / "uv_tools"
    uv_bin = tmp_path / "uv_bin"
    (uv_tools / "connectonion" / "bin").mkdir(parents=True)
    uv_bin.mkdir(parents=True)
    (uv_bin / "co").write_text("#!/bin/sh\necho old\n", encoding="utf-8")

    monkeypatch.setattr(auto_upgrade, "detect_install_method", lambda **kw: {
        "method": "uv_tool", "supported": True, "uv_tool_dir": str(uv_tools), "uv_bin_dir": str(uv_bin),
    })
    monkeypatch.setattr(auto_upgrade, "current_version", lambda: "1.9.7rc32")
    monkeypatch.setattr(auto_upgrade, "find_uv", lambda: "/usr/bin/uv")
    monkeypatch.setattr(auto_upgrade, "prewarm_reader", lambda root, py, **kw: "busy")
    monkeypatch.setattr(auto_upgrade.sys, "platform", "darwin")

    launchctl_calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        if cmd[0] == "launchctl":
            launchctl_calls.append(list(cmd))
            if cmd[1] == "print":
                return CompletedProcess(cmd, 0, "pid = 8888\nstate = running\n", "")
            return CompletedProcess(cmd, 0, "", "")
        env = kwargs.get("env") or {}
        if cmd[:3] == ["/usr/bin/uv", "tool", "install"]:
            tdir = Path(env["UV_TOOL_DIR"]) / "connectonion" / "bin"
            bdir = Path(env["UV_TOOL_BIN_DIR"])
            tdir.mkdir(parents=True, exist_ok=True)
            bdir.mkdir(parents=True, exist_ok=True)
            (tdir / "python").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (bdir / "co").write_text("#!/bin/sh\necho 1.9.7rc33\n", encoding="utf-8")
            return CompletedProcess(cmd, 0, "Installed", "")
        return CompletedProcess(cmd, 0, "1.9.7rc33\n", "")

    result = auto_upgrade.run_atomic_upgrade(
        home=home,
        root=rem_root,
        run=fake_run,
        fetch=lambda url: {"releases": {"1.9.7rc33": [{"yanked": False}]}},
    )
    assert result["outcome"] == "upgraded"
    assert result["reader"] == "busy"
    assert result["prewarmed"] is True
    assert launchctl_calls == []
    assert plistlib.loads(plist_path.read_bytes())["ProgramArguments"] == ["/old/python"]
    assert live_host.read_json(co_dir / "rem-live-host.json", {})["pid"] == 111


def test_host_session_info_reports_aqua_background_and_non_macos(tmp_path, monkeypatch):
    co_dir = tmp_path / ".co"
    co_dir.mkdir(parents=True)
    agents_dir = tmp_path / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True)

    # 1) macOS Host stuck in Background -> warning + recovery command.
    write_json(co_dir / "rem-live-host.json", {"address": "0xowner", "pid": 31337, "port": 18765,
                                               "command": "-m connectonion.cli.main ai", "session": "Background"})
    monkeypatch.setattr(live_host, "_alive", lambda saved: True)
    no_agent_run = lambda cmd, **kw: CompletedProcess(cmd, 113, "", "not loaded")
    bg = live_host.host_session_info(co_dir, uid=501, agents_dir=agents_dir, run=no_agent_run, platform="darwin")
    assert bg["session"] == "Background"
    assert bg["stuck_in_background"] is True
    assert bg["ok"] is False
    assert "co rem open --live" in bg["recovery_command"]

    # If LaunchAgent plist is installed, recovery command points directly to launchctl kickstart -k.
    (agents_dir / f"{live_host.REM_HOST_LABEL}.plist").write_text("<plist/>", encoding="utf-8")
    bg_with_plist = live_host.host_session_info(co_dir, uid=501, agents_dir=agents_dir, run=no_agent_run, platform="darwin")
    assert bg_with_plist["recovery_command"] == "launchctl kickstart -k gui/501/ai.openonion.rem-host"

    # 2) macOS Host running via LaunchAgent in Aqua -> healthy!
    aqua_run = lambda cmd, **kw: CompletedProcess(cmd, 0, "pid = 31337\nstate = running\n", "")
    aqua = live_host.host_session_info(co_dir, uid=501, agents_dir=agents_dir, run=aqua_run, platform="darwin")
    assert aqua["session"] == "Aqua"
    assert aqua["launch_agent_loaded"] is True
    assert aqua["stuck_in_background"] is False
    assert aqua["ok"] is True
    assert aqua["recovery_command"] == ""

    # 3) Non-macOS platform -> non-macOS, ok.
    linux = live_host.host_session_info(co_dir, uid=1000, agents_dir=agents_dir, run=no_agent_run, platform="linux")
    assert linux["session"] == "non-macOS"
    assert linux["ok"] is True


def test_co_rem_stop_unloads_rem_host_launch_agent_reversibly(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    agents_dir = Path(os.environ["HOME"]) / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = agents_dir / f"{live_host.REM_HOST_LABEL}.plist"
    plist_path.write_text("<plist/>", encoding="utf-8")

    uninstalled = []
    monkeypatch.setattr(live_host, "uninstall_host_agent", lambda **kw: uninstalled.append(True) or (plist_path.unlink(missing_ok=True) or True))
    monkeypatch.setattr("connectonion.rem.schedule.default_scheduler", lambda *a, **k: SimpleNamespace(uninstall=lambda p: False))

    result = CliRunner().invoke(cli_app, ["rem", "--root", str(root), "--json", "stop"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)["data"]
    assert payload.get("host_agent_unloaded") is True
    assert uninstalled == [True]
    assert not plist_path.exists()


def test_co_rem_doctor_reports_aqua_and_warns_when_stuck_in_background(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)

    # Case A: Stuck in Background on macOS -> check fails with actionable recovery fix.
    monkeypatch.setattr(
        live_host,
        "host_session_info",
        lambda **kw: {
            "platform": "darwin",
            "running": True,
            "pid": 4321,
            "port": 18765,
            "session": "Background",
            "launch_agent_label": live_host.REM_HOST_LABEL,
            "launch_agent_installed": True,
            "launch_agent_loaded": False,
            "launch_agent_pid": None,
            "stuck_in_background": True,
            "ok": False,
            "recovery_command": "launchctl kickstart -k gui/501/ai.openonion.rem-host",
        },
    )
    res_bg = CliRunner().invoke(cli_app, ["rem", "--root", str(root), "--json", "doctor"])
    assert res_bg.exit_code == 0, res_bg.output
    checks_bg = json.loads(res_bg.output)["data"]
    host_check = next(c for c in checks_bg if c["check"] == "REM live host session")
    assert host_check["ok"] is False
    assert "Background" in host_check["detail"]
    assert "Aqua" in host_check["detail"]
    assert host_check["fix"] == "launchctl kickstart -k gui/501/ai.openonion.rem-host"

    # Case B: Running in Aqua via LaunchAgent -> check passes.
    monkeypatch.setattr(
        live_host,
        "host_session_info",
        lambda **kw: {
            "platform": "darwin",
            "running": True,
            "pid": 4322,
            "port": 18765,
            "session": "Aqua",
            "launch_agent_label": live_host.REM_HOST_LABEL,
            "launch_agent_installed": True,
            "launch_agent_loaded": True,
            "launch_agent_pid": 4322,
            "stuck_in_background": False,
            "ok": True,
            "recovery_command": "",
        },
    )
    res_aqua = CliRunner().invoke(cli_app, ["rem", "--root", str(root), "--json", "doctor"])
    assert res_aqua.exit_code == 0, res_aqua.output
    checks_aqua = json.loads(res_aqua.output)["data"]
    host_check_aqua = next(c for c in checks_aqua if c["check"] == "REM live host session")
    assert host_check_aqua["ok"] is True
    assert "Aqua" in host_check_aqua["detail"]
    assert "LaunchAgent" in host_check_aqua["detail"]
