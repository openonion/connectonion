"""Successive rounds spend a separate week and preserve the record when a stage fails."""

import json
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


def mapped(root, people=(), projects=(), orgs=(), owner=None):
    write_json(state_path(root, "map.json"), {"people": list(people), "projects": list(projects),
                                             "orgs": list(orgs), "owner": owner})


def round_row(**extra):
    return {"at": TODAY.isoformat(), "chars": [1, 2], "quotes": [1, 1], "sources": [1, 1],
            "insights": 0, "enrich": "completed", "muse": "completed", **extra}


def test_candidates_rank_value_thinness_recency_and_rounds(root):
    thick, project = "people/thick.md", "projects/atlas.md"
    Notebook(root).write(thick, PAGE + '\n'.join(f'“Quote {n}”' for n in range(30)))
    Notebook(root).write(project, "# Atlas\n")
    mapped(root, people=[{"record": thick, "mails": 100}, {"record": RECORD, "mails": 100}],
           projects=[{"record": project, "sessions": 20, "last": "2026-10-15"}])
    rows = depth.candidates(root)
    assert [r["record"] for r in rows] == [project, RECORD, thick]
    expected = log2(102) ** 2 / (1 + 1 / 3 + 1 / 10)
    assert rows[1]["priority"] == pytest.approx(expected)
    assert rows[0]["value"] == 20 and rows[0]["recent"] == 2
    assert rows[1]["value"] == 100 and rows[1]["recent"] == 1
    write_json(state_path(root, "depth.json"), {RECORD: [round_row(quotes=[1, 3])] * 2})
    row = next(r for r in depth.candidates(root) if r["record"] == RECORD)
    assert row["rounds"] == 2 and row["priority"] == pytest.approx(expected / 3)
    assert depth.page_metrics(PAGE) == {"chars": len(PAGE), "quotes": 1, "sources": 1}


def test_more_mail_outweighs_an_empty_page(root):
    """2026-10-20: 5 mails beat 30–55; the round gained one quote, 2,669 -> 2,660 chars."""
    empty = "people/robin.md"
    Notebook(root).write(empty, "# Robin\n")
    Notebook(root).write(RECORD, PAGE + '\n“Second quote” [2]\n“Third quote” [3]\n'
                         '- [2] gmail:bbbbbbbbbbbb\n- [3] gmail:cccccccccccc\n')
    mapped(root, people=[{"record": RECORD, "mails": 30}, {"record": empty, "mails": 5}])
    rows = depth.candidates(root)
    assert [row["record"] for row in rows] == [RECORD, empty]
    assert rows[0]["quotes"] == 3 and rows[0]["sources"] == 3


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
    assert set(rows) == {RECORD, project, "projects/quiet.md", "orgs/lantern.md"}
    assert rows["orgs/lantern.md"]["value"] == 0 and rows["orgs/lantern.md"]["recent"] == 1
    assert rows[project]["priority"] == pytest.approx(log2(16) ** 2 * 2)
    assert rows["projects/quiet.md"]["priority"] == 1
    assert rows[RECORD]["priority"] == pytest.approx(1 / (1 + 1 / 3 + 1 / 10))
    mapped(root, projects=[{"record": project, "sessions": 2, "last": "2026-08-01"}])
    rows = {row["record"]: row for row in depth.candidates(root)}
    assert rows[project]["priority"] == log2(4) ** 2


def test_unmapped_project_sessions_come_only_from_paths(root):
    notebook = Notebook(root)
    notebook.write("projects/quiet.md", "# Quiet\n\n## Notes\n- Sessions: 99\n\n## Paths\n- /work/quiet\n")
    row = next(row for row in depth.candidates(root) if row["record"] == "projects/quiet.md")
    assert row["priority"] == 1


@pytest.mark.parametrize("last,recent", [("2026-10-18", 2), ("2026-08-01", 1), (None, 1)])
def test_org_value_and_recency_come_from_its_people(root, last, recent):
    org = "orgs/acme.md"
    Notebook(root).write(org, "# Acme\n")
    mapped(root, people=[{"record": RECORD, "mails": 7, "last": last},
                         {"record": "people/other.md", "mails": 11, "last": "2026-07-01"},
                         {"record": "people/unrelated.md", "mails": 100, "last": "2026-10-20"}],
           orgs=[{"record": org, "people": ["people/other.md", RECORD], "mails": 999, "last": "2026-10-20"}])
    row = next(row for row in depth.candidates(root) if row["record"] == org)
    assert row["value"] == 18 and row["recent"] == recent
    assert row["priority"] == pytest.approx(log2(20) ** 2 * recent)


def test_notification_only_and_empty_orgs_are_skipped_but_mixed_org_is_kept(root):
    """2026-10-20: the first org picked was an event domain with one one-way person."""
    orgs = {"one-way": ["people/notice.md"], "automated": ["people/bot.md"], "empty": [],
            "notifications": ["people/notice.md", "people/bot.md"],
            "mixed": ["people/notice.md", RECORD]}
    for name in orgs:
        Notebook(root).write(f"orgs/{name}.md", f"# {name}\n")
    mapped(root, people=[{"record": RECORD, "automated_hint": False, "one_way": False},
                         {"record": "people/notice.md", "automated_hint": False, "one_way": True},
                         {"record": "people/bot.md", "automated_hint": True, "one_way": False}],
           orgs=[{"record": f"orgs/{name}.md", "people": people} for name, people in orgs.items()])
    assert {row["record"] for row in depth.candidates(root)} == {RECORD, "orgs/mixed.md"}


@pytest.mark.parametrize("age,changed,insights,rests", [
    (29, False, 0, True), (30, False, 0, False), (1, True, 0, False), (1, False, 1, False)])
def test_unchanged_round_rests_for_thirty_days(root, age, changed, insights, rests):
    mapped(root, people=[{"record": RECORD}])
    row = round_row(at=(TODAY - timedelta(days=age)).isoformat(), chars=[1, 2 if changed else 1], insights=insights)
    write_json(state_path(root, "depth.json"), {RECORD: [row]})
    assert bool(depth.candidates(root)) is not rests


@pytest.mark.parametrize("change", [
    {"quotes": [1, 3]}, {"sources": [1, 3]}, {"insights": 2},
    {"quotes": [1, 2], "sources": [1, 2]}, {"quotes": [1, 2], "insights": 1},
    {"chars": [1000, 1600]}, {"chars": [1000, 400]}])
@pytest.mark.parametrize("position", [0, 1])
def test_plateau_does_not_rest_when_either_round_gained(root, change, position):
    rounds = [round_row(chars=[1000, 1350]), round_row(chars=[1350, 1949])]
    rounds[position].update(change)
    write_json(state_path(root, "depth.json"), {RECORD: rounds})
    assert depth.candidates(root)


@pytest.mark.parametrize("count,age,rests", [(1, 1, False), (2, 29, True), (2, 30, False)])
def test_two_small_rounds_rest_from_the_last_round(root, count, age, rests):
    rounds = [round_row(at=(TODAY - timedelta(days=age + 2)).isoformat(), chars=[1000, 1350]),
              round_row(at=(TODAY - timedelta(days=age)).isoformat(), chars=[1350, 751], quotes=[1, 2])]
    write_json(state_path(root, "depth.json"), {RECORD: rounds[-count:]})
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
    choice = depth.candidates(root)[0]
    result = depth.slot(root, pages=1, stage=lambda *a: {}, say=said.append)
    assert len(result["rounds"]) == 1 and result["left"] == 1 and result["stopped"] == ""
    assert said == [f"Deepening {result['rounds'][0]['record']} (round 1)…"]
    assert result["picked"] == [{key: choice[key] for key in
                                 ("record", "priority", "value", "recent", "quotes", "sources", "rounds")}]


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
    assert [row["record"] for row in result["picked"]] == [result["rounds"][0]["record"]]
    assert result["stopped"] == "deepening has used 30 of its 30-point weekly budget"


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("limit", [5, 60])
@pytest.mark.parametrize("offset,completed", [(-1, 2), (0, 2), (1, 1)])
def test_slot_checks_wall_time_before_starting_another_page(root, monkeypatch, explicit, limit, offset, completed):
    project = "projects/atlas.md"
    Notebook(root).write(project, "# Atlas\n")
    config = read_config(root)
    config["limits"]["depth_slot_minutes"] = limit
    monkeypatch.setattr(depth, "read_config", lambda root: config)
    clock = iter([100, 100 + (limit + offset) * 60])
    monkeypatch.setattr(depth.time, "monotonic", lambda: next(clock))
    calls = []
    result = depth.slot(root, records=[RECORD, project] if explicit else None,
                        stage=lambda path, record, name: calls.append((record, name)) or {})
    assert len(result["rounds"]) == completed and result["left"] == 2 - completed
    assert calls == [(row["record"], name) for row in result["rounds"] for name in ("enrich", "muse")]
    assert len(result["picked"]) == completed
    assert result["stopped"] == (f"the slot has run {limit + offset} of its {limit} minutes" if completed == 1 else "")


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
    assert [row["record"] for row in result["picked"]] == records
    assert [row["rounds"] for row in result["picked"]] == [0, 2, 0]
    assert result["picked"][1]["quotes"] == 1 and result["picked"][1]["sources"] == 1
    assert said == [f"Deepening {record} (round {number})…" for record, number in zip(records, [1, 3, 1])]
    assert result["left"] == 0 and result["stopped"] == ""


def test_slot_explicit_empty_records_does_not_select_candidates(root):
    assert depth.slot(root, records=[], stage=lambda *a: pytest.fail("started a page")) == {
        "rounds": [], "picked": [], "stopped": "", "left": 0}


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
    assert result["picked"] == []


def test_depth_limits_merge_and_validate(root):
    limits = default_config()["limits"]
    assert limits["depth_quota_points"] == 30 and limits["depth_pages_per_slot"] == 2
    assert limits["depth_slot_minutes"] == 60
    path = root / "config.yaml"
    path.write_text('\n'.join(line for line in path.read_text().splitlines() if 'depth_' not in line))
    assert read_config(root)["limits"] == limits
    config = read_config(root)
    config["limits"]["depth_quota_points"] = 101
    with pytest.raises(RemError, match="1 to 100"):
        validate(config)


@pytest.mark.parametrize("value", [0, -1, 1.5, True, "60"])
def test_slot_minutes_must_be_a_positive_integer(root, value):
    config = read_config(root)
    config["limits"]["depth_slot_minutes"] = value
    with pytest.raises(RemError, match="positive integers"):
        validate(config)


def test_deepen_cli_logs_both_stages_and_prints_round_table(root, monkeypatch):
    mapped(root, people=[{"record": RECORD}])
    for name in ("enrich", "muse"):
        monkeypatch.setattr(depth.muse, name, lambda *a, **kw: {"insights": 1, "usage": {"output_tokens": 10}})
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "deepen", "--pages", "1"])
    assert result.exit_code == 0, result.output
    assert RECORD in result.stdout and "insights" in result.stdout and "Left: 0" in result.stdout
    assert f"picked {RECORD}: value 0, recent ×1, 1 quotes, 1 sources, round 1" in result.stdout
    assert {run["phase"] for run in service.run_logs(root)} == {"enrich", "muse"}


def test_deepen_cli_json_exposes_why_each_page_was_picked(root, monkeypatch):
    mapped(root, people=[{"record": RECORD, "mails": 7, "last": "2026-10-18"}])
    for name in ("enrich", "muse"):
        monkeypatch.setattr(depth.muse, name, lambda *a, **kw: {})
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "deepen"])
    assert result.exit_code == 0, result.output
    picked = json.loads(result.stdout)["data"]["picked"]
    assert picked == [{"record": RECORD, "priority": pytest.approx(log2(9) ** 2 * 2 / (1 + 1 / 3 + 1 / 10)),
                       "value": 7, "recent": 2, "quotes": 1, "sources": 1, "rounds": 0}]


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


def test_a_refused_round_does_not_rest_the_page(root):
    mapped(root, people=[{"record": RECORD}])
    row = round_row(chars=[1, 1], enrich="refused", muse="refused")
    write_json(state_path(root, "depth.json"), {RECORD: [row]})
    assert [r["record"] for r in depth.candidates(root)] == [RECORD]
