"""The wiki reads Codex's own weekly meter and budgets investigation on it (#1843).

Before this the notebook budgeted in calls and characters and could not say
what share of the owner's Codex plan it used; `docs/cli/wiki.md` called the
percentage limits unimplemented for want of a meter. Codex has one:
`codex app-server` answers `account/rateLimits/read` without a model turn.
"""

import pytest

from connectonion.wiki import quota

WEEK = 10080
RESETS = 1_791_067_743  # 2026-10-04, a week after the runs below
WINDOW_START = RESETS - WEEK * 60

PAYLOAD = {"ordinaryUsageAllowed": True,
           "rateLimits": {"limitId": "codex", "primary": {"usedPercent": 5, "windowDurationMins": WEEK,
                                                          "resetsAt": RESETS},
                          "secondary": None, "planType": "pro"}}


def _signed_in(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "auth.json").write_text("{}")


def test_a_reading_is_the_weekly_window_codex_reports(monkeypatch, tmp_path):
    _signed_in(monkeypatch, tmp_path)
    calls = []
    reading = quota.read({"runner": "codex"}, request=lambda method, params: calls.append(method) or PAYLOAD)
    assert calls == ["account/rateLimits/read"]
    assert reading == {"used_percent": 5, "window_minutes": WEEK, "resets_at": RESETS, "plan": "pro"}


def test_another_runner_has_no_meter_and_nothing_is_started(monkeypatch, tmp_path):
    _signed_in(monkeypatch, tmp_path)
    reading = quota.read({"runner": "claude-code"}, request=lambda *a: pytest.fail("started app-server"))
    assert "claude-code" in reading["unknown"]


def test_codex_not_signed_in_is_unknown_without_starting_it(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))  # no auth.json
    reading = quota.read({"runner": "codex"}, request=lambda *a: pytest.fail("started app-server"))
    assert "not signed in" in reading["unknown"]


def test_a_failed_read_says_why_and_does_not_raise(monkeypatch, tmp_path):
    _signed_in(monkeypatch, tmp_path)

    def broken(method, params):
        raise RuntimeError("method not found")
    reading = quota.read({"runner": "codex"}, request=broken)
    assert "method not found" in reading["unknown"]


def _run(started, before, after, phase="daily-investigation"):
    return {"started_at": started, "phase": phase,
            "quota": {"before": {"used_percent": before, "resets_at": RESETS, "window_minutes": WEEK},
                      "after": {"used_percent": after, "resets_at": RESETS, "window_minutes": WEEK}}}


def test_points_spent_count_only_this_windows_investigations():
    now = {"used_percent": 30, "window_minutes": WEEK, "resets_at": RESETS}
    logs = [_run("2026-09-28T01:00:00+00:00", 5, 8),                    # 3, counts
            _run("2026-09-29T01:00:00+00:00", 8, 9),                    # 1, counts
            _run("2026-09-29T02:00:00+00:00", 9, 20, phase=None),       # maintenance, not counted
            _run("2026-09-20T01:00:00+00:00", 1, 9),                    # last week's window
            _run("2026-09-30T01:00:00+00:00", 12, 11),                  # a reset mid-run: not negative
            {"started_at": "2026-09-30T02:00:00+00:00", "phase": "daily-investigation",
             "quota": {"before": {"unknown": "x"}, "after": {"unknown": "x"}}}]
    assert quota.points_spent(logs, now) == 4


def test_the_budget_and_the_floor_stop_a_new_investigation():
    limits = {"investigation_quota_points": 10, "quota_floor_percent": 70}
    week = {"window_minutes": WEEK, "resets_at": RESETS}
    assert quota.blocks({**week, "used_percent": 40}, 9, limits) == ""
    assert "budget" in quota.blocks({**week, "used_percent": 40}, 10, limits)
    assert "70%" in quota.blocks({**week, "used_percent": 70}, 0, limits)
    # No meter: the call cap is the only bound, as before this change.
    assert quota.blocks({"unknown": "no meter"}, 99, limits) == ""


def test_old_notebooks_get_the_new_limits_without_rewriting_config(tmp_path):
    from connectonion.wiki.config import prepare, read_config
    root = tmp_path / "wiki"
    prepare(root)
    text = (root / "config.yaml").read_text()
    stripped = "\n".join(line for line in text.splitlines()
                         if "investigation_quota_points" not in line and "quota_floor_percent" not in line)
    (root / "config.yaml").write_text(stripped + "\n")
    limits = read_config(root)["limits"]
    assert limits["investigation_quota_points"] == 10 and limits["quota_floor_percent"] == 70


def test_the_daily_round_stops_at_the_floor_and_records_why(tmp_path, monkeypatch):
    from connectonion.wiki.daily import run_daily
    root = _mapped_notebook(tmp_path)
    monkeypatch.setattr(quota, "read", lambda config, request=None: {
        "used_percent": 71, "window_minutes": WEEK, "resets_at": RESETS, "plan": "pro"})
    result = run_daily(root, scheduled=True, maintain=lambda root, scheduled: {"outcome": "no_change"},
                       investigate_one=lambda *a, **k: pytest.fail("investigated past the floor"))
    assert result["investigation"] is None
    assert "70%" in result["reason"]


def test_a_daily_investigation_records_the_meter_before_and_after(tmp_path, monkeypatch):
    from connectonion.wiki.daily import run_daily
    root = _mapped_notebook(tmp_path)
    readings = iter([7, 9])
    monkeypatch.setattr(quota, "read", lambda config, request=None: {
        "used_percent": next(readings), "window_minutes": WEEK, "resets_at": RESETS, "plan": "pro"})
    result = run_daily(root, scheduled=True, maintain=lambda root, scheduled: {"outcome": "no_change"},
                       investigate_one=lambda *a, **k: {"usage": None, "changed": ["people/vern.md"]})
    run = result["run"]
    assert (run["quota"]["before"]["used_percent"], run["quota"]["after"]["used_percent"]) == (7, 9)


def _mapped_notebook(tmp_path):
    from connectonion.wiki.config import prepare
    from connectonion.wiki.files import Notebook
    root = tmp_path / "wiki"
    prepare(root)
    Notebook(root).stub_person("people/vern.md", "Vern Chan", handles=["vern@example.com"])
    return root
