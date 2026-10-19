"""Successive rounds spend a separate week and preserve the record when a stage fails."""

from datetime import datetime, timedelta, timezone
from math import log2

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import depth, quota, runner, service
from connectonion.rem.config import default_config, prepare, read_config, validate
from connectonion.rem.files import Notebook, RemError, read_json, state_path, write_json

RECORD = "people/avery-lin.md"
PAGE = '# Avery Lin\n\nThey said “Keep the original words”. [1]\n\n## Sources\n- [1] gmail:aaaaaaaaaaaa\n'
TODAY = datetime(2026, 10, 20, tzinfo=timezone.utc)


@pytest.fixture
def root(tmp_path, monkeypatch):
    prepare(tmp_path)
    Notebook(tmp_path).write(RECORD, PAGE)
    monkeypatch.setattr(service, "now", lambda: TODAY)
    monkeypatch.setattr(runner, "ready", lambda config: ("", ""))
    monkeypatch.setattr(quota, "read", lambda config: {"unknown": "fixture"})
    return tmp_path


def mapped(root, people=(), projects=(), owner=None):
    write_json(state_path(root, "map.json"), {"people": list(people), "projects": list(projects), "owner": owner})


def round_row(**extra):
    return {"at": TODAY.isoformat(), "chars": [1, 2], "quotes": [1, 1], "sources": [1, 1],
            "insights": 0, **extra}


def test_candidates_rank_value_thinness_recency_and_rounds(root):
    thick, project = "people/thick.md", "projects/atlas.md"
    Notebook(root).write(thick, PAGE + '\n'.join(f'“Quote {n}”' for n in range(30)))
    Notebook(root).write(project, "# Atlas\n")
    mapped(root, people=[{"record": thick, "mails": 100}, {"record": RECORD, "mails": 100}],
           projects=[{"record": project, "sessions": 10, "last": "2026-10-15"}])
    rows = depth.candidates(root)
    assert [r["record"] for r in rows] == [project, RECORD, thick]
    expected = log2(102) / (1 + 1 / 3 + 1 / 10)
    assert rows[1]["priority"] == pytest.approx(expected)
    write_json(state_path(root, "depth.json"), {RECORD: [round_row()] * 2})
    row = next(r for r in depth.candidates(root) if r["record"] == RECORD)
    assert row["rounds"] == 2 and row["priority"] == pytest.approx(expected / 3)
    assert depth.page_metrics(PAGE) == {"chars": len(PAGE), "quotes": 1, "sources": 1}


@pytest.mark.parametrize("owner", [RECORD, {"record": RECORD}])
def test_candidates_skip_owner_automated_and_missing_records(root, owner):
    for name in ("owner", "automated"):
        Notebook(root).write(f"people/{name}.md", PAGE)
    mapped(root, people=[{"record": RECORD}, {"record": "people/owner.md", "classification": "account owner"},
                         {"record": "people/automated.md", "automated_hint": True},
                         {"record": "people/missing.md"}, {"name": "No record"}], owner=owner)
    assert depth.candidates(root) == []


def test_candidates_include_unmapped_pages_with_project_activity(root):
    notebook = Notebook(root)
    project = "projects/lantern-skills.md"
    text = "# Lantern Skills\n\n## Paths\n- Sessions: 14\n- Last seen: 2026-10-18\n"
    notebook.write(project, text)
    notebook.write("projects/quiet.md", "# Quiet\n")
    notebook.write("orgs/lantern.md", "# Lantern\n")
    mapped(root)
    rows = {row["record"]: row for row in depth.candidates(root)}
    assert set(rows) == {RECORD, project, "projects/quiet.md"}
    assert rows[project]["priority"] == pytest.approx(log2(16) * 2)
    assert rows["projects/quiet.md"]["priority"] == 1
    assert rows[RECORD]["priority"] == pytest.approx(1 / (1 + 1 / 3 + 1 / 10))
    mapped(root, projects=[{"record": project, "sessions": 2, "last": "2026-08-01"}])
    rows = {row["record"]: row for row in depth.candidates(root)}
    assert rows[project]["priority"] == log2(4)


def test_unmapped_project_sessions_come_only_from_paths(root):
    notebook = Notebook(root)
    notebook.write("projects/quiet.md", "# Quiet\n\n## Notes\n- Sessions: 99\n\n## Paths\n- /work/quiet\n")
    row = next(row for row in depth.candidates(root) if row["record"] == "projects/quiet.md")
    assert row["priority"] == 1


@pytest.mark.parametrize("age,changed,insights,rests", [
    (29, False, 0, True), (30, False, 0, False), (1, True, 0, False), (1, False, 1, False)])
def test_unchanged_round_rests_for_thirty_days(root, age, changed, insights, rests):
    mapped(root, people=[{"record": RECORD}])
    row = round_row(at=(TODAY - timedelta(days=age)).isoformat(), chars=[1, 2 if changed else 1], insights=insights)
    write_json(state_path(root, "depth.json"), {RECORD: [row]})
    assert bool(depth.candidates(root)) is not rests


def test_priority_ties_sort_by_record(root):
    other = "people/avery-other.md"
    Notebook(root).write(other, PAGE)
    mapped(root, people=[{"record": other}, {"record": RECORD}])
    assert [r["record"] for r in depth.candidates(root)] == sorted([other, RECORD])


def test_deepen_records_metrics_insights_losses_and_points(root):
    calls = []
    enriched = PAGE + '\n“Enrich quote” [2]\n- [2] gmail:cccccccccccc\n'
    after = PAGE.replace('“Keep the original words”', 'New finding') + '\n“Another quote” [2]\n- [2] gmail:bbbbbbbbbbbb\n'

    def stage(path, record, name):
        calls.append(name)
        Notebook(path).write(record, enriched if name == "enrich" else after)
        return {"insights": 2, "usage": {"input_tokens": 6_500_000, "cached_input_tokens": 500_000}}

    row = depth.deepen(root, RECORD, stage=stage)
    assert calls == ["enrich", "muse"]
    assert row == {"record": RECORD, "round": 1, "at": TODAY.isoformat(), "chars": [len(PAGE), len(after)],
                   "quotes": [1, 1], "sources": [1, 2], "insights": 2, "lost_quotes": 1,
                   "after_enrich": {"chars": len(enriched), "quotes": 2, "sources": 2},
                   "enrich": "completed", "muse": "completed", "points": 2}
    assert read_json(state_path(root, "depth.json"), {})[RECORD] == [{k: v for k, v in row.items() if k != "record"}]
    assert depth.deepen(root, RECORD, stage=stage)["round"] == 2


@pytest.mark.parametrize("message,outcome", [("review rejected", "refused"), ("x" * 250, "failed: " + "x" * 200)])
def test_failed_enrich_still_runs_muse_and_counts_failed_usage(root, message, outcome):
    calls = []

    def stage(path, record, name):
        calls.append(name)
        if name == "enrich":
            raise runner.RunFailed(message, {"output_tokens": 3_000_000})
        return {"outcome": "no_change", "insights": 0}

    row = depth.deepen(root, RECORD, stage=stage)
    assert calls == ["enrich", "muse"]
    assert row["enrich"] == outcome and row["muse"] == "no_change" and row["points"] == 0.5
    assert row["after_enrich"] == depth.page_metrics(PAGE)


def test_failed_muse_is_recorded_without_usage(root):
    def stage(path, record, name):
        if name == "muse":
            raise RemError("no session")
        return {}
    assert depth.deepen(root, RECORD, stage=stage)["muse"] == "failed: no session"


def test_default_stage_calls_enrich_then_muse(root, monkeypatch):
    calls = []
    for name in ("enrich", "muse"):
        monkeypatch.setattr(depth.muse, name, lambda *a, name=name: calls.append(name) or {})
    depth.deepen(root, RECORD)
    assert calls == ["enrich", "muse"]


def test_slot_respects_pages_and_announces_round(root):
    Notebook(root).write("projects/atlas.md", "# Atlas\n")
    mapped(root, people=[{"record": RECORD}], projects=[{"record": "projects/atlas.md"}])
    said = []
    result = depth.slot(root, pages=1, stage=lambda *a: {}, say=said.append)
    assert len(result["rounds"]) == 1 and result["left"] == 1 and result["stopped"] == ""
    assert said == [f"Deepening {result['rounds'][0]['record']} (round 1)…"]


@pytest.mark.parametrize("explicit", [False, True])
def test_slot_checks_budget_before_each_page(root, monkeypatch, explicit):
    Notebook(root).write("projects/atlas.md", "# Atlas\n")
    mapped(root, people=[{"record": RECORD}], projects=[{"record": "projects/atlas.md"}])
    meter = {"used_percent": 40, "window_minutes": 10080, "resets_at": int((TODAY + timedelta(days=1)).timestamp())}
    monkeypatch.setattr(quota, "read", lambda config: meter)
    logs = []
    monkeypatch.setattr(service, "run_logs", lambda root: logs)

    def stage(path, record, name):
        logs.append({"phase": name, "started_at": TODAY.isoformat(), "usage": {"input_tokens": 180_000_000}})
        return {"usage": {"input_tokens": 180_000_000}}

    result = depth.slot(root, records=[RECORD, "projects/atlas.md"] if explicit else None, stage=stage)
    assert len(result["rounds"]) == 1 and result["left"] == 1
    assert result["stopped"] == "deepening has used 30 of its 30-point weekly budget"


def test_slot_explicit_records_bypass_candidates_and_page_limit_in_order(root, monkeypatch):
    records = ["projects/lantern.md", RECORD, "projects/quiet.md"]
    for record in (records[0], records[2]):
        Notebook(root).write(record, "# Project\n")
    write_json(state_path(root, "depth.json"), {RECORD: [round_row(chars=[1, 1])] * 2})
    monkeypatch.setattr(depth, "candidates", lambda root: pytest.fail("ranked explicit pages"))
    said = []
    result = depth.slot(root, records=records, pages=1, stage=lambda *a: {}, say=said.append)
    assert [row["record"] for row in result["rounds"]] == records
    assert [row["round"] for row in result["rounds"]] == [1, 3, 1]
    assert said == [f"Deepening {record} (round {number})…" for record, number in zip(records, [1, 3, 1])]
    assert result["left"] == 0 and result["stopped"] == ""


def test_slot_explicit_empty_records_does_not_select_candidates(root):
    assert depth.slot(root, records=[], stage=lambda *a: pytest.fail("started a page")) == {
        "rounds": [], "stopped": "", "left": 0}


@pytest.mark.parametrize("blocked", ["floor", "budget", "runner"])
def test_slot_stops_before_starting(root, monkeypatch, blocked):
    mapped(root, people=[{"record": RECORD}])
    if blocked == "runner":
        monkeypatch.setattr(runner, "ready", lambda config: ("Codex is not signed in", "codex login"))
    elif blocked == "floor":
        monkeypatch.setattr(quota, "read", lambda config: {"used_percent": 90})
    else:
        monkeypatch.setattr(service, "run_logs", lambda root: [
            {"phase": "muse", "started_at": TODAY.isoformat(), "usage": {"input_tokens": 360_000_000}}])
    result = depth.slot(root, stage=lambda *a: pytest.fail("started while blocked"))
    assert result["rounds"] == [] and result["left"] == 1 and result["stopped"]


def test_depth_limits_merge_and_validate(root):
    limits = default_config()["limits"]
    assert limits["depth_quota_points"] == 30 and limits["depth_pages_per_slot"] == 2
    path = root / "config.yaml"
    path.write_text('\n'.join(line for line in path.read_text().splitlines() if 'depth_' not in line))
    assert read_config(root)["limits"] == limits
    config = read_config(root)
    config["limits"]["depth_quota_points"] = 101
    with pytest.raises(RemError, match="1 to 100"):
        validate(config)


def test_deepen_cli_logs_both_stages_and_prints_round_table(root, monkeypatch):
    mapped(root, people=[{"record": RECORD}])
    for name in ("enrich", "muse"):
        monkeypatch.setattr(depth.muse, name, lambda *a, **kw: {"insights": 1, "usage": {"output_tokens": 10}})
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "deepen", "--pages", "1"])
    assert result.exit_code == 0, result.output
    assert RECORD in result.stdout and "insights" in result.stdout and "Left: 0" in result.stdout
    assert {run["phase"] for run in service.run_logs(root)} == {"enrich", "muse"}


def test_deepen_cli_prints_failed_stage_messages_verbatim(root, monkeypatch):
    mapped(root, people=[{"record": RECORD}])

    def fail(*args, **kwargs):
        raise runner.RunFailed("audit failed [/claim]", {"output_tokens": 10})

    monkeypatch.setattr(depth.muse, "enrich", fail)
    monkeypatch.setattr(depth.muse, "muse", lambda *a, **kw: {})
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "deepen"])
    assert result.exit_code == 0, result.output
    assert "failed: audit failed [/claim] / completed" in result.stdout


def test_deepen_cli_resolves_explicit_pages_in_order(root, monkeypatch):
    project = "projects/lantern-skills.md"
    Notebook(root).write(project, "# Lantern Skills\n")
    calls = []
    for name in ("enrich", "muse"):
        monkeypatch.setattr(depth.muse, name, lambda path, record, name=name, **kw: calls.append((record, name)) or {})
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "deepen", "Lantern Skills", "avery-lin",
                                      "--pages", "1"])
    assert result.exit_code == 0, result.output
    assert calls == [(record, name) for record in (project, RECORD) for name in ("enrich", "muse")]
    assert "Left: 0" in result.stdout


@pytest.mark.parametrize("scheduled,outcome,called", [(True, "completed", True), (False, "completed", False),
                                                     (True, "partial", False), (True, None, False)])
def test_only_due_completed_scheduled_sync_deepens(root, monkeypatch, scheduled, outcome, called):
    from connectonion.rem import daily
    calls = []
    monkeypatch.setattr(daily, "run_daily", lambda *a, **kw: None if outcome is None else {
        "outcome": outcome, "maintenance": {"items": 0}, "investigation": None})
    monkeypatch.setattr(depth, "slot", lambda *a, **kw: calls.append(kw) or {
        "rounds": [], "stopped": "fixture floor", "left": 1})
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "sync", *(["--scheduled"] if scheduled else [])])
    assert result.exit_code == (1 if outcome == "partial" else 0), result.output
    assert bool(calls) is called
    if called:
        assert callable(calls[0]["stage"]) and callable(calls[0]["say"])
        assert "Deepened 0 pages; stopped: fixture floor" in result.stdout
