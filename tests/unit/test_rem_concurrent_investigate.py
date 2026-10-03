"""A category run covers its full queue and reports concurrent completions."""

import json
import threading

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.config import prepare


@pytest.mark.parametrize("category", ["orgs", "all"])
def test_category_runs_every_pending_page_with_ten_workers(tmp_path, monkeypatch, category):
    root = tmp_path / "rem"
    prepare(root)
    rows = [{"path": f"orgs/o{n}.md", "recent": False, "last_investigated": None}
            for n in range(51)]
    monkeypatch.setattr("connectonion.rem.queue.order", lambda root, category: rows)
    monkeypatch.setattr("connectonion.rem.queue.order_all", lambda root: rows)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "no meter"})
    started = threading.Barrier(10, timeout=5)
    seen = []

    def investigate(root, notebook, record, **kwargs):
        seen.append(record)
        if len(seen) <= 10:
            started.wait()
        return {"record": record}

    monkeypatch.setattr("connectonion.cli.commands.rem_commands._investigate_page", investigate)
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "investigate", category])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert len(seen) == len(data["pages"]) == 51
    assert data["left"] == 0
    assert all(row["outcome"] == "accepted" for row in data["pages"])
    assert "[51/51]" in result.output


def test_explicit_limit_and_worker_count_bound_a_trial(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    rows = [{"path": f"orgs/o{n}.md", "recent": False, "last_investigated": None}
            for n in range(5)]
    monkeypatch.setattr("connectonion.rem.queue.order", lambda root, category: rows)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "no meter"})
    together = threading.Barrier(2, timeout=5)
    seen = []

    def investigate(root, notebook, record, **kwargs):
        seen.append(record)
        together.wait()
        return {"record": record}

    monkeypatch.setattr("connectonion.cli.commands.rem_commands._investigate_page", investigate)
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "investigate", "orgs",
                                      "--limit", "2", "--workers", "2"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert len(seen) == len(data["pages"]) == 2
    assert data["left"] == 3


def test_category_reports_refusal_as_it_finishes_and_continues(tmp_path, monkeypatch):
    from connectonion.rem.runner import RunFailed

    root = tmp_path / "rem"
    prepare(root)
    rows = [{"path": f"orgs/o{n}.md", "recent": False, "last_investigated": None}
            for n in range(2)]
    monkeypatch.setattr("connectonion.rem.queue.order", lambda root, category: rows)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "no meter"})

    def investigate(root, notebook, record, **kwargs):
        if record == "orgs/o0.md":
            raise RunFailed("Candidate rejected")
        return {"record": record}

    monkeypatch.setattr("connectonion.cli.commands.rem_commands._investigate_page", investigate)
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "investigate", "orgs"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    data = payload["data"]
    assert sorted(row["outcome"] for row in data["pages"]) == ["accepted", "refused"]
    assert data["left"] == 1 and "skipped_recent" not in data
    assert payload["next"].endswith("logs")
    assert "orgs/o0.md: refused" in result.output
    assert "orgs/o1.md: accepted" in result.output
    from connectonion.cli.commands.rem_output import render
    summary = render(data, "investigate", failed=True)
    assert "Completed: 1 accepted, 1 refused." in summary
    assert "Read accepted: " in summary and "show orgs/o1.md" in summary and "Pages:" not in summary


def test_people_command_runs_the_whole_queue_concurrently(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    rows = [{"record": f"people/p{n}.md", "mode": "full", "days": 30,
             "last_activity": "2026-09-30T00:00:00Z", "mails": 1, "recent": True,
             "sent": 1, "received": 1, "last_investigated": None} for n in range(11)]
    monkeypatch.setattr("connectonion.rem.people_pages.queue", lambda root, **kw: rows)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "no meter"})
    monkeypatch.setattr("connectonion.cli.commands.rem_commands._mail_clients", lambda root: {})
    monkeypatch.setattr("connectonion.rem.service.subscriptions", lambda root: {})
    monkeypatch.setattr("connectonion.cli.commands.rem_commands._logged",
                        lambda root, record, phase, call: call(lambda *args: None))
    together = threading.Barrier(10, timeout=5)
    seen = []

    def investigate(root, row, **kwargs):
        seen.append(row["record"])
        if len(seen) <= 10:
            together.wait()
        return {"record": row["record"]}

    monkeypatch.setattr("connectonion.rem.people_pages.investigate_person", investigate)
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "investigate", "people"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert len(seen) == len(data["pages"]) == 11 and data["left"] == 0
    assert "[11/11]" in result.output


def test_category_does_not_apply_the_scheduled_quota_as_an_implicit_cap(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    rows = [{"path": f"orgs/o{n}.md", "recent": False, "last_investigated": None}
            for n in range(2)]
    monkeypatch.setattr("connectonion.rem.queue.order", lambda root, category: rows)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"used_percent": 50})
    seen = []
    monkeypatch.setattr("connectonion.cli.commands.rem_commands._investigate_page",
                        lambda root, notebook, record, **kwargs: seen.append(record))
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "investigate", "orgs"])
    assert result.exit_code == 0, result.output
    assert len(seen) == 2 and json.loads(result.stdout)["data"]["left"] == 0


def test_terminal_batch_summary_stays_short_and_empty_queue_is_clear(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    rows = [{"path": f"orgs/o{n}.md", "recent": False, "last_investigated": None}
            for n in range(55)]
    monkeypatch.setattr("connectonion.rem.queue.order", lambda root, category: rows)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "no meter"})
    monkeypatch.setattr("connectonion.cli.commands.rem_commands._investigate_page",
                        lambda root, notebook, record, **kwargs: {"record": record})
    runner = CliRunner()
    result = runner.invoke(app, ["rem", "--root", str(root), "investigate", "orgs"])
    assert result.exit_code == 0, result.output
    assert "Investigating 55 of 55 pending orgs pages with up to 10 workers." in result.output
    assert "Completed: 55 accepted." in result.output and "Left: 0" in result.output
    assert "Pages:" not in result.output and "Next: " in result.output
    monkeypatch.setattr("connectonion.rem.queue.order", lambda root, category: [])
    empty = runner.invoke(app, ["rem", "--root", str(root), "investigate", "orgs"])
    assert empty.exit_code == 0, empty.output
    assert "All pending pages in orgs are current." in empty.output
    assert "Pages: None" not in empty.output and empty.output.strip().endswith("list orgs")
