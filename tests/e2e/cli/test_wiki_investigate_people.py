"""`co wiki investigate people`: the order and the cost first, then one call per person (#1943 stage 3)."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook, state_path, write_json


def invoke(root, *args):
    return CliRunner().invoke(app, ["wiki", "--root", str(root), *args])


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "wiki"
    prepare(root)
    now = datetime.now(timezone.utc)
    rows = []
    for slug, days in (("old", 40), ("new", 1)):
        Notebook(root).stub_person(f"people/{slug}.md", slug.title(), [f"{slug}@example.org"],
                                   email=f"{slug}@example.org")
        rows.append({"record": f"people/{slug}.md", "addresses": [f"{slug}@example.org"], "mails": 4,
                     "last": (now - timedelta(days=days)).date().isoformat(), "classification": "unassessed"})
    write_json(state_path(root, "map.json"), {"people": rows, "projects": [], "orgs": []})
    monkeypatch.setattr("connectonion.wiki.service.mail_available", lambda kind: False)
    return root


def test_list_shows_recent_first_and_the_cost_and_reads_nothing(root, monkeypatch):
    monkeypatch.setattr("connectonion.wiki.investigate.investigate",
                        lambda *a, **k: pytest.fail("--list investigated"))
    result = invoke(root, "investigate", "people", "--list")
    assert result.exit_code == 0, result.output
    assert result.output.index("people/new.md") < result.output.index("people/old.md")
    assert "Cost: 2 model call(s), one per person; 8 mails mapped" in result.output
    assert "Nothing was read or spent." in result.output


def test_a_run_states_the_cost_before_the_first_call_and_says_what_is_left(root, monkeypatch):
    order = []

    def investigate(root, record, subject, handles, *, days, **kw):
        order.append((record, days))
        return {"changed": [record], "usage": None}
    monkeypatch.setattr("connectonion.wiki.investigate.investigate", investigate)
    result = invoke(root, "--json", "investigate", "people", "--limit", "1", "--recent-days", "7")
    assert result.exit_code == 0, result.output
    assert order == [("people/new.md", 150)]
    assert result.stderr.index("Cost:") < result.stderr.index("\n[1/1] people/new.md")
    assert "1 people left to investigate." in result.stderr
    assert json.loads(result.stdout)["data"]["left"] == 1


def test_recent_days_belongs_to_people(root):
    result = invoke(root, "investigate", "projects", "--recent-days", "7")
    assert result.exit_code == 1 and "--recent-days goes with people" in result.output
