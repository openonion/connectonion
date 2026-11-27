"""Regression tests for #3480 (updated 2026-11-27): 10-wave 22:00-02:30 overnight REM schedule with 03:00 cutoff."""

from datetime import datetime, timezone

import pytest

from connectonion.rem import codex_schedule
from connectonion.rem.config import PROFILES, PROFILE_WINDOW_ENDS, default_config, prepare, read_config, set_config
from connectonion.rem.files import RemError

EXPECTED_OVERNIGHT_STARTS = [
    "22:00", "22:30", "23:00", "23:30",
    "00:00", "00:30", "01:00", "01:30", "02:00", "02:30",
]

EXPECTED_OVERNIGHT_FIRES = [
    "00:00", "00:15", "00:30", "00:45",
    "01:00", "01:15", "01:30", "01:45",
    "02:00", "02:15", "02:30",
    "22:00", "22:15", "22:30", "22:45",
    "23:00", "23:15", "23:30", "23:45",
]


def test_overnight_profile_has_ten_starts_from_2200_to_0230_and_preserves_existing_profiles(tmp_path):
    assert "overnight" in PROFILES
    assert PROFILES["overnight"] == EXPECTED_OVERNIGHT_STARTS
    assert len(PROFILES["overnight"]) == 10
    assert "03:00" not in PROFILES["overnight"]
    assert PROFILE_WINDOW_ENDS["overnight"] == "02:30"

    # Existing default and dense schedules must remain untouched (no silent migration).
    defaults = default_config()
    assert defaults["schedule"]["profile"] == "default"
    assert len(defaults["schedule"]["times"]) == 12
    assert "17:00" in defaults["schedule"]["times"]
    assert len(PROFILES["dense"]) == 19
    assert "07:00" in PROFILES["dense"]

    # Opting into overnight activates the 10 overnight starts without touching other profiles.
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.profile", "overnight"])
    cfg = read_config(tmp_path)
    assert cfg["schedule"]["profile"] == "overnight"
    assert cfg["schedule"]["times"] == EXPECTED_OVERNIGHT_STARTS


def test_overnight_continuations_stop_at_0230_with_no_0245_0300_or_0530_spillover():
    cfg = default_config()
    cfg["schedule"]["profile"] = "overnight"
    cfg["schedule"]["times"] = list(PROFILES["overnight"])

    fired = codex_schedule.fire_times(cfg)
    assert fired == EXPECTED_OVERNIGHT_FIRES
    assert len(fired) == 19

    # 22:00..02:00 each get their single +15min continuation.
    for continuation in ("22:15", "22:45", "23:15", "23:45", "00:15", "00:45", "01:15", "01:45", "02:15"):
        assert continuation in fired

    # 02:30 has NO 02:45 continuation; never fires 02:45, 03:00, 03:30, or 05:30.
    for forbidden in ("02:45", "03:00", "03:15", "03:30", "05:30", "06:00", "08:00"):
        assert forbidden not in fired

    # Rolling 5-hour quota buffer: >= 5 clean hours between 03:00 window end and 08:00 daytime coding.
    daytime_fires = [t for t in fired if "02:31" <= t < "22:00"]
    assert daytime_fires == []


def test_default_and_dense_profile_fire_times_unchanged():
    cfg = default_config()
    fired = codex_schedule.fire_times(cfg)
    assert "06:00" in fired
    assert "07:00" in fired
    assert "09:00" in fired  # 06:00 + 3h continuation preserved for default profile

    dense_cfg = default_config()
    dense_cfg["schedule"]["profile"] = "dense"
    dense_cfg["schedule"]["times"] = list(PROFILES["dense"])
    dense_fired = codex_schedule.fire_times(dense_cfg)
    assert "07:00" in dense_fired
    assert "10:00" in dense_fired  # 07:00 + 3h continuation preserved for dense profile


def test_overnight_recurrence_uses_local_wall_clock_for_dst_and_omits_0245(monkeypatch):
    monkeypatch.setattr(codex_schedule, "desktop_timezone", lambda: "Australia/Melbourne")
    cfg = default_config()
    cfg["schedule"].update(
        profile="overnight",
        times=list(PROFILES["overnight"]),
        timezone="Australia/Melbourne",
    )
    rule = codex_schedule.recurrence(cfg)
    assert rule.startswith("FREQ=DAILY;BYHOUR=0,1,2,22,23;BYMINUTE=0,15,30,45;BYSECOND=0;BYSETPOS=")
    assert "TZID=" not in rule  # local wall clock handles DST cleanly
    # Grid is 5 hours x 4 minutes = 20 pairs; position 12 is (2, 45) and must be excluded.
    positions = [int(p) for p in rule.split("BYSETPOS=")[1].split(",")]
    assert len(positions) == 19
    assert 12 not in positions


def test_describe_schedule_window_exposes_10_starts_cutoffs_and_policy():
    cfg = default_config()
    cfg["schedule"].update(
        profile="overnight",
        times=list(PROFILES["overnight"]),
        timezone="Australia/Melbourne",
    )
    info = codex_schedule.describe_schedule_window(cfg)
    assert info["profile"] == "overnight"
    assert info["starts"] == 10
    assert info["times"] == EXPECTED_OVERNIGHT_STARTS
    assert info["timezone"] == "Australia/Melbourne"
    assert info["window_end"] == "03:00"
    assert info["latest_fire"] == "02:30"
    assert info["long_work_cutoff"] == "01:00"
    assert info["model_turn_cutoff"] == "02:40"
    assert info["policy"] == "no new work after 03:00 (in-flight turns finish cleanly)"
    assert info["continuation_step_minutes"] == 15
    assert info["fire_count"] == 19
    assert "10 starts" in info["summary"]
    assert "02:30" in info["summary"]
    assert "03:00" in info["summary"]
    assert "01:00" in info["summary"]
    assert "02:40" in info["summary"]
    assert "no new work after 03:00 (in-flight turns finish cleanly)" in info["summary"]


def test_invalid_schedule_profile_names_overnight_option(tmp_path):
    prepare(tmp_path)
    with pytest.raises(RemError, match="overnight"):
        set_config(tmp_path, ["schedule.profile", "not-a-profile"])
