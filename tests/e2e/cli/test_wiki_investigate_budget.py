"""The first pass after init, and every manual investigation, on the Codex week (#1842).

`init` maps the notebook and stops; investigating it was one page or one
category at a time, bounded by a page count. On the owner's notebook that left
725 of 938 pages empty. `investigate all --budget N` works one queue over
people, projects and organisations until N points of the Codex week are spent,
and manual runs count toward investigation's weekly budget like the round does.
"""

import json
import time

from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook, state_path, write_json

WEEK = 10080


def invoke(root, *args):
    return CliRunner().invoke(app, ["wiki", "--root", str(root), *args])


def _queue(monkeypatch, rows):
    monkeypatch.setattr("connectonion.wiki.queue.order", lambda root, category, today=None: [
        {"path": path, "recent": False, "weight": weight, "unknown": 1, "last_investigated": None}
        for path, weight in rows.get(category, [])])


def _meter(monkeypatch, state):
    """A Codex week that each investigated page moves by state['per_page'] points."""
    resets = int(time.time()) + 3 * 86400
    monkeypatch.setattr("connectonion.wiki.quota.read", lambda config, request=None: {
        "used_percent": state["used"], "window_minutes": WEEK, "resets_at": resets, "plan": "pro"}
        if state.get("used") is not None else {"unknown": "no meter"})

    def investigate(root, record, *a, **kw):
        state["done"].append(record)
        if state.get("used") is not None:
            state["used"] += state.get("per_page", 0)
        return {"changed": [record], "usage": None}
    monkeypatch.setattr("connectonion.wiki.investigate.investigate", investigate)
    return resets


def _notebook(tmp_path):
    root = tmp_path / "wiki"
    prepare(root)
    for name in ("ada", "bob", "cy"):
        Notebook(root).stub_person(f"people/{name}.md", name.title(), [f"{name}@example.org"],
                                   email=f"{name}@example.org")
    Notebook(root).write("projects/aurora.md", "# Aurora\n\n## What it is\n- Unknown — not investigated yet\n")
    return root


def test_all_is_one_queue_over_people_projects_and_orgs_by_weight(tmp_path, monkeypatch):
    root = _notebook(tmp_path)
    _queue(monkeypatch, {"people": [("people/ada.md", 1), ("people/bob.md", 9)],
                         "projects": [("projects/aurora.md", 5)]})
    result = invoke(root, "--json", "investigate", "all", "--list")
    assert result.exit_code == 0, result.output
    order = json.loads(result.stdout)["data"]["order"]
    assert [row["path"] for row in order] == ["people/bob.md", "projects/aurora.md", "people/ada.md"]


def test_a_budget_stops_new_pages_once_this_run_has_spent_it(tmp_path, monkeypatch):
    root = _notebook(tmp_path)
    _queue(monkeypatch, {"people": [("people/ada.md", 3), ("people/bob.md", 2), ("people/cy.md", 1)]})
    state = {"used": 5, "per_page": 2, "done": []}
    _meter(monkeypatch, state)
    result = invoke(root, "--json", "investigate", "all", "--budget", "3", "--days", "5")
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    # 0 points spent before ada, 2 before bob (under 3), 4 before cy: stop.
    assert state["done"] == ["people/ada.md", "people/bob.md"]
    assert "3-point" in data["stopped"] and data["left"] == 1


def test_nothing_starts_once_the_week_is_at_the_floor(tmp_path, monkeypatch):
    root = _notebook(tmp_path)
    _queue(monkeypatch, {"people": [("people/ada.md", 3)]})
    state = {"used": 70, "done": []}
    _meter(monkeypatch, state)
    result = invoke(root, "--json", "investigate", "people", "--days", "5")
    assert result.exit_code == 0, result.output
    assert state["done"] == []
    assert "70%" in json.loads(result.stdout)["data"]["stopped"]


def test_the_weekly_budget_already_spent_stops_a_category_run(tmp_path, monkeypatch):
    root = _notebook(tmp_path)
    _queue(monkeypatch, {"people": [("people/ada.md", 3)]})
    state = {"used": 30, "done": []}
    resets = _meter(monkeypatch, state)
    week = {"window_minutes": WEEK, "resets_at": resets}
    write_json(state_path(root, "runs/run_earlier.json"), {
        "id": "run_earlier", "started_at": "2099-01-01T00:00:00+00:00", "phase": "investigate",
        "quota": {"before": {**week, "used_percent": 10}, "after": {**week, "used_percent": 20}}})
    result = invoke(root, "--json", "investigate", "people", "--days", "5")
    assert state["done"] == []
    assert "weekly budget" in json.loads(result.stdout)["data"]["stopped"]


def test_a_manual_page_records_the_week_and_counts_against_the_budget(tmp_path, monkeypatch):
    from connectonion.wiki import quota
    from connectonion.wiki.service import run_logs
    root = _notebook(tmp_path)
    state = {"used": 12, "per_page": 3, "done": []}
    now = _meter(monkeypatch, state)
    result = invoke(root, "--json", "investigate", "people/ada.md", "--days", "5")
    assert result.exit_code == 0, result.output
    run = next(r for r in run_logs(root) if r.get("record") == "people/ada.md")
    assert (run["quota"]["before"]["used_percent"], run["quota"]["after"]["used_percent"]) == (12, 15)
    meter = {"used_percent": 15, "window_minutes": WEEK, "resets_at": now}
    assert quota.points_spent(run_logs(root), meter) == 3


def test_without_a_meter_the_page_limit_is_the_bound(tmp_path, monkeypatch):
    root = _notebook(tmp_path)
    _queue(monkeypatch, {"people": [("people/ada.md", 3), ("people/bob.md", 2), ("people/cy.md", 1)]})
    state = {"used": None, "done": []}
    _meter(monkeypatch, state)
    result = invoke(root, "--json", "investigate", "people", "--limit", "2", "--days", "5")
    assert result.exit_code == 0, result.output
    assert state["done"] == ["people/ada.md", "people/bob.md"]
    assert "stopped" not in json.loads(result.stdout)["data"]
