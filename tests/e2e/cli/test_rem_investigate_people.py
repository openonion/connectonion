"""`co rem investigate people`: the order and the cost first, then one call per person (#1943 stage 3)."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json


def invoke(root, *args):
    return CliRunner().invoke(app, ["rem", "--root", str(root), *args])


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    now = datetime.now(timezone.utc)
    rows = []
    for slug, days in (("old", 40), ("new", 1)):
        Notebook(root).stub_person(f"people/{slug}.md", slug.title(), [f"{slug}@example.org"],
                                   email=f"{slug}@example.org")
        rows.append({"record": f"people/{slug}.md", "addresses": [f"{slug}@example.org"], "mails": 4,
                     "last": (now - timedelta(days=days)).date().isoformat(), "classification": "unassessed"})
    write_json(state_path(root, "map.json"), {"people": rows, "projects": [], "orgs": []})
    monkeypatch.setattr("connectonion.rem.service.mail_available", lambda kind: False)
    return root


def test_list_shows_recent_first_and_the_cost_and_reads_nothing(root, monkeypatch):
    monkeypatch.setattr("connectonion.rem.investigate.investigate",
                        lambda *a, **k: pytest.fail("--list investigated"))
    result = invoke(root, "investigate", "people", "--list")
    assert result.exit_code == 0, result.output
    assert result.output.index("people/new.md") < result.output.index("people/old.md")
    assert "Cost: 2 model calls, one per person" in result.output and "at least 8 mails" in result.output
    assert "Nothing was read or spent." in result.output


def test_a_run_states_the_cost_before_the_first_call_and_says_what_is_left(root, monkeypatch):
    order = []

    def investigate(root, record, subject, handles, *, days, **kw):
        order.append((record, days))
        return {"changed": [record], "usage": None}
    monkeypatch.setattr("connectonion.rem.investigate.investigate", investigate)
    result = invoke(root, "--json", "investigate", "people", "--limit", "1", "--recent-days", "7")
    assert result.exit_code == 0, result.output
    assert order == [("people/new.md", 730)]  # two years on a first investigation
    assert result.stderr.index("Cost:") < result.stderr.index("\n[1/1] people/new.md")
    assert "1 person left to investigate." in result.stderr
    assert json.loads(result.stdout)["data"]["left"] == 1


def test_recent_days_belongs_to_people(root):
    result = invoke(root, "investigate", "projects", "--recent-days", "7")
    assert result.exit_code == 1 and "--recent-days goes with people" in result.output


# ------------------------------------------------ #1974: one queue, the owner first


def _with_owner(root, *, investigated=False, own=()):
    Notebook(root).stub_person("people/me.md", "Me", ["me@example.org"], email="me@example.org")
    if investigated:
        page = Notebook(root).read("people/me.md").replace("· not investigated yet", "· investigated 2026-09-20 (gmail)")
        Notebook(root).write("people/me.md", page)
    state = json.loads(state_path(root, "map.json").read_text())
    state["owner"] = {"record": "people/me.md", "addresses": ["me@example.org"]}
    state["possible_own_addresses"] = [{"address": a, "sent": 40 - i, "record": f"people/own{i}.md",
                                        "confirm": f"co wiki init --mine {a}"} for i, a in enumerate(own)]
    write_json(state_path(root, "map.json"), state)


def test_the_overview_and_the_people_list_are_one_queue(root):
    overview = invoke(root, "--json", "investigate")
    listing = invoke(root, "--json", "investigate", "people", "--list")
    assert overview.exit_code == listing.exit_code == 0, overview.output + listing.output
    people = json.loads(overview.stdout)["data"]["people"]
    order = json.loads(listing.stdout)["data"]["order"]
    assert people["unfinished"] == len(order)
    assert people["next"] == [row["record"] for row in order][:3]


def test_the_owner_s_page_comes_first_until_it_is_investigated(root):
    _with_owner(root, own=["me.personal@example.net", "me.backup@example.com"])
    result = invoke(root, "investigate")
    assert result.exit_code == 0, result.output
    assert result.output.index("people/me.md") < result.output.index("people/new.md")
    assert "Next: co rem --root" in result.output and "investigate me" in result.output and "--quick" not in result.output
    assert "init --mine me.personal@example.net,me.backup@example.com" in result.output
    assert "co wiki" not in result.output
    listing = invoke(root, "investigate", "people", "--list")
    assert listing.output.index("investigate me") < listing.output.index("people/new.md")


def test_an_investigated_owner_page_does_not_hold_the_next_line(root):
    _with_owner(root, investigated=True)
    result = invoke(root, "investigate")
    assert "investigate me" not in result.output.split("Next:")[-1]


def test_one_person_left_is_one_person(root, monkeypatch):
    monkeypatch.setattr("connectonion.rem.investigate.investigate",
                        lambda root, record, *a, **k: {"changed": [record], "usage": None})
    result = invoke(root, "--json", "investigate", "people", "--limit", "1")
    assert "1 person left to investigate." in result.stderr
