"""Regression tests for #3480: five-start overnight REM schedule for rolling 5h agent quotas."""

import pytest

from connectonion.rem import codex_schedule
from connectonion.rem.config import PROFILES, default_config, prepare, read_config, set_config
from connectonion.rem.files import RemError


def test_overnight_profile_has_five_starts_in_00_to_03_and_preserves_existing_profiles(tmp_path):
    assert "overnight" in PROFILES
    assert PROFILES["overnight"] == ["00:00", "00:45", "01:30", "02:15", "03:00"]
    assert len(PROFILES["overnight"]) == 5

    # Existing default schedule must remain untouched (no silent migration).
    defaults = default_config()
    assert defaults["schedule"]["profile"] == "default"
    assert len(defaults["schedule"]["times"]) == 12
    assert "17:00" in defaults["schedule"]["times"]

    # Opting into overnight activates the five overnight starts without touching other profiles.
    prepare(tmp_path)
    set_config(tmp_path, ["schedule.profile", "overnight"])
    cfg = read_config(tmp_path)
    assert cfg["schedule"]["profile"] == "overnight"
    assert cfg["schedule"]["times"] == ["00:00", "00:45", "01:30", "02:15", "03:00"]


def test_overnight_continuations_hard_stop_at_0330_leaving_five_clean_hours_before_daytime():
    cfg = default_config()
    cfg["schedule"]["profile"] = "overnight"
    cfg["schedule"]["times"] = list(PROFILES["overnight"])

    fired = codex_schedule.fire_times(cfg)
    assert fired == [
        "00:00", "00:15", "00:30",
        "00:45", "01:00", "01:15",
        "01:30", "01:45", "02:00",
        "02:15", "02:30", "02:45",
        "03:00", "03:15", "03:30",
    ]
    # Zero daytime spillover past 03:30 so 08:30+ coding starts with a fresh 5h rolling window.
    assert all(t <= "03:30" for t in fired)
    assert "03:45" not in fired
    assert "06:00" not in fired


def test_default_profile_fire_times_unchanged():
    cfg = default_config()
    fired = codex_schedule.fire_times(cfg)
    assert "06:00" in fired
    assert "07:00" in fired
    assert "09:00" in fired  # 06:00 + 3h continuation preserved for default profile


def test_overnight_recurrence_uses_local_wall_clock_for_dst_and_stays_within_codex_limits(monkeypatch):
    monkeypatch.setattr(codex_schedule, "desktop_timezone", lambda: "Australia/Melbourne")
    cfg = default_config()
    cfg["schedule"].update(
        profile="overnight",
        times=list(PROFILES["overnight"]),
        timezone="Australia/Melbourne",
    )
    rule = codex_schedule.recurrence(cfg)
    assert rule.startswith("FREQ=DAILY;BYHOUR=0,1,2,3;BYMINUTE=0,15,30,45;BYSECOND=0")
    assert "TZID=" not in rule  # local wall clock handles DST cleanly


def test_describe_schedule_window_exposes_starts_timezone_and_cutoff():
    cfg = default_config()
    cfg["schedule"].update(
        profile="overnight",
        times=list(PROFILES["overnight"]),
        timezone="Australia/Melbourne",
    )
    info = codex_schedule.describe_schedule_window(cfg)
    assert info["profile"] == "overnight"
    assert info["times"] == ["00:00", "00:45", "01:30", "02:15", "03:00"]
    assert info["timezone"] == "Australia/Melbourne"
    assert info["window_end"] == "03:30"
    assert info["latest_fire"] == "03:30"
    assert info["continuation_step_minutes"] == 15
    assert info["fire_count"] == 15
    assert "03:30" in info["summary"]


def test_invalid_schedule_profile_names_overnight_option(tmp_path):
    prepare(tmp_path)
    with pytest.raises(RemError, match="overnight"):
        set_config(tmp_path, ["schedule.profile", "not-a-profile"])
