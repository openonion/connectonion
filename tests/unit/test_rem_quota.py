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


def test_status_with_an_unknown_meter_keeps_pages_running(tmp_path, monkeypatch):
    from rich.text import Text
    from connectonion.cli.commands import rem_status
    from connectonion.rem import service
    from connectonion.rem.config import prepare, read_config

    root = tmp_path / "rem"
    prepare(root)
    monkeypatch.setattr(quota, "read", lambda config: {
        "unknown": "Codex did not report its quota (RuntimeError: boom)"})
    bits = service._quota_status(read_config(root), [])
    assert "RuntimeError" not in bits["codex_week"]
    assert "unknown" in bits["codex_week"] or "unavailable" in bits["codex_week"]
    assert "pages still run" in bits["codex_week"]
    assert "within the daily call cap" in bits["codex_week"]
    assert "RuntimeError" in bits["quota"]["unknown"]

    value = {"root": str(root), "state": "Stopped", "configured": True, **bits}
    text = Text.from_markup(rem_status.dashboard(root, value, lambda args: "co rem " + " ".join(args))).plain
    assert "RuntimeError" not in text
    assert "pages still run" in text
    assert "within the daily call cap" in text


def _run(started, before, after, phase="daily-investigation", finished=None):
    return {"started_at": started, "finished_at": finished or started, "phase": phase,
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
                         if not any(key in line for key in ("investigation_quota_points", "quota_floor_percent", "workers")))
    (root / "config.yaml").write_text(stripped + "\n")
    prepare(root)
    limits = read_config(root)["limits"]
    assert limits["investigation_quota_points"] == 35 and limits["quota_floor_percent"] == 90
    assert limits["workers"] == 16
    assert (root / "config.yaml").read_text() == stripped + "\n"


def test_old_saved_defaults_upgrade_but_explicit_quota_choices_stay(tmp_path):
    from connectonion.rem.config import prepare, read_config, set_config
    root = tmp_path / "rem"
    prepare(root)
    path = root / "config.yaml"
    path.write_text(path.read_text().replace("investigation_quota_points: 35", "investigation_quota_points: 20")
                    .replace("quota_floor_percent: 90", "quota_floor_percent: 70"))
    assert read_config(root)["limits"]["investigation_quota_points"] == 35
    assert read_config(root)["limits"]["quota_floor_percent"] == 90
    set_config(root, ["limits.investigation_quota_points", "20", "limits.quota_floor_percent", "70"])
    assert read_config(root)["limits"]["investigation_quota_points"] == 20
    assert read_config(root)["limits"]["quota_floor_percent"] == 70


def test_the_daily_round_stops_at_the_floor_and_records_why(tmp_path, monkeypatch):
    from connectonion.rem.daily import run_daily
    root = _mapped_notebook(tmp_path)
    monkeypatch.setattr(quota, "read", lambda config, request=None: {
        "used_percent": 91, "window_minutes": WEEK, "resets_at": RESETS, "plan": "pro"})
    result = run_daily(root, scheduled=True, maintain=lambda root, scheduled: {"outcome": "no_change"},
                       investigate_one=lambda *a, **k: pytest.fail("investigated past the floor"))
    assert result["investigation"] is None
    assert "90%" in result["reason"]


def test_a_daily_investigation_records_the_meter_before_and_after(tmp_path, monkeypatch):
    from connectonion.rem.daily import run_daily
    root = _mapped_notebook(tmp_path)
    readings = iter([7, 9])
    monkeypatch.setattr(quota, "read", lambda config, request=None: {
        "used_percent": next(readings), "window_minutes": WEEK, "resets_at": RESETS, "plan": "pro"})
    result = run_daily(root, scheduled=True, maintain=lambda root, scheduled: {"outcome": "no_change"},
                       investigate_one=lambda *a, **k: {"usage": None, "changed": ["people/rowan.md"]})
    run = result["run"]
    assert (run["quota"]["before"]["used_percent"], run["quota"]["after"]["used_percent"]) == (7, 9)


def _mapped_notebook(tmp_path):
    from connectonion.rem.config import prepare
    from connectonion.rem.files import Notebook
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).stub_person("people/rowan.md", "Rowan Ashdown", handles=["rowan@example.com"])
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
    assert quota.points_spent([unmoved, unread, measured, maintenance], now) == 2.1


@pytest.mark.parametrize("speed, tokens", [("standard", "12,000,000"), ("fast", "6,000,000")])
def test_status_says_what_a_point_is(tmp_path, monkeypatch, speed, tokens):
    from connectonion.cli.commands import rem_status
    from connectonion.rem.config import prepare, set_config
    prepare(tmp_path)
    set_config(tmp_path, ["speed", speed])
    for name in ("_notebook", "_today", "_mailboxes", "_archive"):
        monkeypatch.setattr(rem_status, name, lambda *a, **k: [])
    monkeypatch.setattr(rem_status, "_header", lambda *a: ["co rem"])
    monkeypatch.setattr(rem_status, "notebook", lambda *a: {})
    monkeypatch.setattr(rem_status, "_last_run", lambda *a: "none")
    monkeypatch.setattr(rem_status, "_zone", lambda root: None)
    value = {"investigation_quota": {"spent_points": 0.6, "budget_points": 10}, "codex_week": "29% used on pro"}
    from rich.text import Text
    # What a point is goes with --verbose: the budget is two lines (UI audit, 2026-10-15).
    text = Text.from_markup(rem_status.dashboard(tmp_path, value, lambda arguments: "co rem " + " ".join(arguments),
                                                 verbose=True)).plain
    assert "0.6 of 10 investigation points" in text
    assert "1% of your Codex week" in text and f"{tokens} tokens a point" in text


def test_a_category_runs_own_budget_counts_its_runs_tokens_when_the_meter_stays_flat():
    """#1990: `investigate all --budget 10` read the meter alone, which never moved."""
    week = {"window_minutes": WEEK, "resets_at": RESETS}
    start, now = {**week, "used_percent": 29}, {**week, "used_percent": 29}
    began = "2026-09-30T00:00:00+00:00"
    earlier = {**_run("2026-09-29T23:00:00+00:00", 29, 29, phase="investigate"), "usage": {"input_tokens": 9_000_000}}
    mine = [{**_run(f"2026-09-30T0{n}:00:00+00:00", 29, 29, phase="investigate"),
             "usage": {"input_tokens": 14_400_000, "cached_input_tokens": 2_400_000}} for n in (1, 2)]
    assert quota.run_spent(start, now, [earlier, *mine], began) == 2
    assert quota.run_spent(start, {**week, "used_percent": 34}, mine, began) == 5   # the meter, when it says more


@pytest.mark.parametrize("known", [True, False])
def test_depth_points_only_counts_enrich_and_muse_in_its_week(monkeypatch, known):
    from datetime import datetime, timezone
    from connectonion.rem import service
    today = datetime(2026, 10, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(service, "now", lambda: today)
    meter = {"resets_at": int(today.timestamp()), "window_minutes": WEEK} if known else {"unknown": "fixture"}
    logs = [{"phase": phase, "started_at": date + "T00:00:00+00:00", "usage": {"input_tokens": 12_000_000}}
            for phase, date in [("enrich", "2026-10-19"), ("muse", "2026-10-18"),
                                ("investigate", "2026-10-19"), ("enrich", "2026-10-12")]]
    assert quota.depth_points(logs, meter) == 2
    if not known:
        assert quota.points_spent(logs, meter) == 0


def test_points_spent_accepts_a_phase_filter():
    now = {"used_percent": 30, "window_minutes": WEEK, "resets_at": RESETS}
    logs = [_run("2026-09-28T01:00:00+00:00", 5, 8, phase="enrich"),
            _run("2026-09-28T02:00:00+00:00", 8, 10)]
    assert quota.points_spent(logs, now, phases=quota.DEPTH_PHASES) == 3


def test_overlapping_runs_count_the_batchs_meter_movement_once():
    began = "2026-09-30T01:00:00+00:00"
    runs = [_run(began, 40, 50, finished="2026-09-30T02:00:00+00:00") for _ in range(16)]
    now = {"used_percent": 50, "window_minutes": WEEK, "resets_at": RESETS}
    assert quota.points_spent(runs, now) == 10
    assert quota.run_spent({**now, "used_percent": 40}, now, runs, began) == 10


def test_separate_overlapping_groups_leave_out_the_owners_coding_between_them():
    runs = [_run("2026-09-30T01:00:00+00:00", 40, 42, finished="2026-09-30T02:00:00+00:00"),
            _run("2026-09-30T01:30:00+00:00", 40, 42, finished="2026-09-30T02:30:00+00:00"),
            _run("2026-09-30T03:00:00+00:00", 45, 47, finished="2026-09-30T04:00:00+00:00"),
            _run("2026-09-30T03:30:00+00:00", 45, 47, finished="2026-09-30T04:30:00+00:00")]
    now = {"used_percent": 47, "window_minutes": WEEK, "resets_at": RESETS}
    assert quota.points_spent(list(reversed(runs)), now) == 4


def test_groups_join_transitively_and_running_runs_only_join_at_their_start():
    first = _run("2026-09-30T01:00:00+00:00", 40, 41, finished="2026-09-30T02:00:00+00:00")
    middle = _run("2026-09-30T01:30:00+00:00", 40, 42, finished="2026-09-30T03:00:00+00:00")
    last = _run("2026-09-30T02:30:00+00:00", 41, 43, finished="2026-09-30T04:00:00+00:00")
    inside = _run("2026-09-30T01:45:00+00:00", 40, 40)
    outside = _run("2026-09-30T05:00:00+00:00", 43, 43)
    for run in (inside, outside):
        run.pop("finished_at")
    assert list(quota._groups([outside, last, inside, middle, first])) == [[first, middle, inside, last], [outside]]


@pytest.mark.parametrize("unknown", [False, True])
def test_a_flat_or_unknown_overlapping_group_counts_fresh_tokens_at_each_runs_speed(unknown):
    standard = {**_run("2026-09-30T01:00:00+00:00", 40, 40, finished="2026-09-30T02:00:00+00:00"),
                "usage": {"input_tokens": 15_000_000, "cached_input_tokens": 4_000_000,
                          "output_tokens": 1_000_000}}
    if unknown:
        standard["quota"] = {"before": {"unknown": "unavailable"}, "after": {"unknown": "unavailable"}}
    fast = {**standard, "speed": "fast"}
    assert quota.run_points(standard) == 1
    assert quota.run_points({**standard, "speed": "standard"}) == 1
    assert quota.run_points(fast) == 2
    now = {"used_percent": 40, "window_minutes": WEEK, "resets_at": RESETS}
    assert quota.points_spent([standard, fast], now) == 3
    assert quota.run_spent(now, now, [standard, fast], standard["started_at"]) == 3


@pytest.mark.parametrize("after", [2, 95])
def test_a_group_crossing_a_weekly_reset_counts_tokens_even_if_the_meter_ends_higher(after):
    run = {**_run("2026-09-30T01:00:00+00:00", 90, after, finished="2026-09-30T02:00:00+00:00"),
           "usage": {"input_tokens": 12_000_000}}
    run["quota"]["after"]["resets_at"] += WEEK * 60
    assert quota.run_points(run) == 1
    assert quota.group_points([run, run]) == 2


def test_group_readings_allow_reset_timestamp_jitter_but_not_drift():
    runs = [_run("2026-09-30T01:00:00+00:00", 40, 42, finished="2026-09-30T02:00:00+00:00")
            for _ in range(2)]
    runs[1]["quota"]["after"]["resets_at"] += 1
    assert quota.group_points(runs) == 2
    runs[1]["quota"]["after"]["resets_at"] += 3600
    assert quota.group_points(runs) == 0
