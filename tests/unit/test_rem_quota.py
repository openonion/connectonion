"""co rem reads Codex's own weekly meter and budgets investigation on it (#1843).

Before this the notebook budgeted in calls and characters and could not say
what share of the owner's Codex plan it used; `docs/cli/rem.md` called the
percentage limits unimplemented for want of a meter. Codex has one:
`codex app-server` answers `account/rateLimits/read` without a model turn.
"""

import pytest

from connectonion.rem import quota

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
    from connectonion.rem.config import prepare, read_config
    root = tmp_path / "rem"
    prepare(root)
    text = (root / "config.yaml").read_text()
    stripped = "\n".join(line for line in text.splitlines()
                         if "investigation_quota_points" not in line and "quota_floor_percent" not in line)
    (root / "config.yaml").write_text(stripped + "\n")
    limits = read_config(root)["limits"]
    assert limits["investigation_quota_points"] == 10 and limits["quota_floor_percent"] == 70


def test_the_daily_round_stops_at_the_floor_and_records_why(tmp_path, monkeypatch):
    from connectonion.rem.daily import run_daily
    root = _mapped_notebook(tmp_path)
    monkeypatch.setattr(quota, "read", lambda config, request=None: {
        "used_percent": 71, "window_minutes": WEEK, "resets_at": RESETS, "plan": "pro"})
    result = run_daily(root, scheduled=True, maintain=lambda root, scheduled: {"outcome": "no_change"},
                       investigate_one=lambda *a, **k: pytest.fail("investigated past the floor"))
    assert result["investigation"] is None
    assert "70%" in result["reason"]


def test_a_daily_investigation_records_the_meter_before_and_after(tmp_path, monkeypatch):
    from connectonion.rem.daily import run_daily
    root = _mapped_notebook(tmp_path)
    readings = iter([7, 9])
    monkeypatch.setattr(quota, "read", lambda config, request=None: {
        "used_percent": next(readings), "window_minutes": WEEK, "resets_at": RESETS, "plan": "pro"})
    result = run_daily(root, scheduled=True, maintain=lambda root, scheduled: {"outcome": "no_change"},
                       investigate_one=lambda *a, **k: {"usage": None, "changed": ["people/vern.md"]})
    run = result["run"]
    assert (run["quota"]["before"]["used_percent"], run["quota"]["after"]["used_percent"]) == (7, 9)


def _mapped_notebook(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).stub_person("people/vern.md", "Vern Chan", handles=["vern@example.com"])
    return root


# ------------------------------------------- the 1.9.0a7 acceptance run (#1990)


def test_runs_the_whole_percent_meter_cannot_see_are_counted_from_their_tokens():
    """#1990: the week read 29% before and after every run, 3.4M input tokens in
    all, and status said "0 of 10 investigation points" all week."""
    now = {"used_percent": 29, "window_minutes": WEEK, "resets_at": RESETS}
    unmoved = {**_run("2026-09-30T01:00:00+00:00", 29, 29, phase="investigate"),
               "usage": {"input_tokens": 1_500_000, "cached_input_tokens": 1_000_000, "output_tokens": 100_000}}
    unread = {"started_at": "2026-09-30T02:00:00+00:00", "phase": "projects write",
              "quota": {"before": {"unknown": "x"}, "after": {"unknown": "x"}},
              "usage": {"input_tokens": 900_000, "output_tokens": 0}}
    measured = {**_run("2026-09-30T03:00:00+00:00", 29, 31, phase="daily-update"),
                "usage": {"input_tokens": 100_000}}   # the meter moved: it, not the tokens, counts
    maintenance = {**_run("2026-09-30T04:00:00+00:00", 29, 29, phase=None),
                   "usage": {"input_tokens": 9_000_000}}
    assert quota.points_spent([unmoved, unread, measured, maintenance], now) == 3.5


def test_status_says_what_a_point_is(tmp_path, monkeypatch):
    from connectonion.cli.commands import rem_status
    for name in ("_notebook", "_today", "_mailboxes", "_archive"):
        monkeypatch.setattr(rem_status, name, lambda *a, **k: [])
    monkeypatch.setattr(rem_status, "_header", lambda *a: ["co rem"])
    monkeypatch.setattr(rem_status, "notebook", lambda root: {})
    monkeypatch.setattr(rem_status, "_last_run", lambda *a: "none")
    monkeypatch.setattr(rem_status, "_zone", lambda root: None)
    value = {"investigation_quota": {"spent_points": 0.6, "budget_points": 10}, "codex_week": "29% used on pro"}
    from rich.text import Text
    text = Text.from_markup(rem_status.dashboard(tmp_path, value, lambda arguments: "co rem " + " ".join(arguments))).plain
    assert "0.6 of 10 investigation points" in text
    assert "1% of your Codex week" in text and "1,000,000 tokens" in text


def test_a_category_runs_own_budget_counts_its_runs_tokens_when_the_meter_stays_flat():
    """#1990: `investigate all --budget 10` read the meter alone, which never moved."""
    week = {"window_minutes": WEEK, "resets_at": RESETS}
    start, now = {**week, "used_percent": 29}, {**week, "used_percent": 29}
    began = "2026-09-30T00:00:00+00:00"
    earlier = {**_run("2026-09-29T23:00:00+00:00", 29, 29, phase="investigate"), "usage": {"input_tokens": 9_000_000}}
    mine = [{**_run(f"2026-09-30T0{n}:00:00+00:00", 29, 29, phase="investigate"),
             "usage": {"input_tokens": 1_200_000, "cached_input_tokens": 200_000}} for n in (1, 2)]
    assert quota.run_spent(start, now, [earlier, *mine], began) == 2
    assert quota.run_spent(start, {**week, "used_percent": 34}, mine, began) == 5   # the meter, when it says more
