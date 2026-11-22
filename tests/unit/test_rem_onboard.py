"""Adding a source onboards it: the source says which kinds of page it yields, the map reads each row's kind (#3331).

Owner, 2026-11-22: "新加一个 source 的话，要在新加的 source 上去跑建页面和 investigate". Invented people only.
"""

import json

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import onboard
from connectonion.rem.files import Notebook, RemError

MAIL_PERSON = "people/mara-ostrowski-0000000001.md"
CONTACTS = [
    {"address": "wxid_mara", "name": "Mara Ostrowski", "mails": 5, "sent": 2, "received": 3},
    {"address": "wxid_quinn", "name": "Quinn Harbour", "mails": 4, "sent": 2, "received": 2},
    {"address": "wxid_ines", "name": "Ines Vale", "mails": 3, "sent": 1, "received": 2},
]
SUBS = {"wechat": {"id": "wechat", "kind": "wechat", "enabled": True, "consented": True}}


def _notebook(root):
    """A notebook that already knows one person from mail, investigated."""
    book = Notebook(root)
    book.stub_person(MAIL_PERSON, "Mara Ostrowski", ["mara@fernhill.example"], email="mara@fernhill.example")
    page = book.read(MAIL_PERSON)
    book.write(MAIL_PERSON, "\n".join("Investigation: investigated 2026-11-01" if line.startswith("Investigation:")
                                      else line for line in page.split("\n")))
    return book


def _rows():
    return [{"kind": "person", **row} for row in CONTACTS]


def _tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_a_new_source_creates_its_new_people_and_adds_its_handle_to_a_known_one(tmp_path):
    book = _notebook(tmp_path)
    result = onboard.plan(tmp_path, _rows(), ("people",), write=True)["people"]
    assert sorted(row["name"] for row in result["create"]) == ["Ines Vale", "Quinn Harbour"]
    assert [row["record"] for row in result["merge"]] == [MAIL_PERSON]
    assert "wxid_mara" in book.read(MAIL_PERSON)          # the mail page is now reachable on the new source
    assert "mara@fernhill.example" in book.read(MAIL_PERSON)  # and kept what it had
    for row in result["create"]:
        assert book.exists(row["record"])


def test_the_new_pages_are_investigated_first_and_the_known_one_is_appended_to(tmp_path):
    _notebook(tmp_path)
    onboard.plan(tmp_path, _rows(), ("people",), write=True)
    pages = onboard.touched(tmp_path, _rows())
    assert len(pages["new"]) == 2 and pages["existing"] == [MAIL_PERSON]


def test_a_second_round_is_a_no_op(tmp_path):
    _notebook(tmp_path)
    onboard.plan(tmp_path, _rows(), ("people",), write=True)
    before = _tree(tmp_path)
    again = onboard.plan(tmp_path, _rows(), ("people",), write=True)["people"]
    assert (again["create"], again["merge"], again["known"]) == ([], [], 3)
    assert _tree(tmp_path) == before


def test_a_dry_run_counts_the_same_and_writes_nothing(tmp_path):
    _notebook(tmp_path)
    before = _tree(tmp_path)
    counted = onboard.plan(tmp_path, _rows(), ("people",), write=False)["people"]
    assert (len(counted["create"]), len(counted["merge"])) == (2, 1)
    assert _tree(tmp_path) == before


def test_a_one_way_contact_is_not_worth_a_page(tmp_path):
    _notebook(tmp_path)
    rows = _rows() + [{"kind": "person", "address": "wxid_shop", "name": "Corner Shop", "mails": 1,
                       "sent": 1, "received": 0}]
    assert onboard.plan(tmp_path, rows, ("people",), write=False)["people"]["skip"] == 1


def test_a_kind_the_source_does_not_yield_is_refused():
    with pytest.raises(RemError, match="wechat yields: people"):
        onboard.check_kinds("wechat", SUBS["wechat"], ("orgs",))
    assert onboard.check_kinds("wechat", SUBS["wechat"], ()) == ("people",)
    assert onboard.check_kinds("gmail", {"kind": "gmail"}, ()) == ("people", "orgs")


def test_a_source_with_nothing_to_map_says_so():
    with pytest.raises(RemError, match="can't be mapped yet"):
        onboard.check_kinds("notes", {"kind": "notes"}, ())


def test_the_map_reads_the_row_kind_so_a_knowledge_source_needs_no_map_change(tmp_path):
    rows = [{"kind": "knowledge", "name": "Heat storage"}]
    made = onboard.plan(tmp_path, rows, ("knowledge",), write=True)["knowledge"]["create"]
    assert len(made) == 1 and Notebook(tmp_path).exists(made[0])


def _cli(tmp_path, monkeypatch, *args):
    monkeypatch.setattr("connectonion.rem.service.subscriptions", lambda root: SUBS)
    # A producer's rows carry the source's own "kind" (as WeChat's do); the page kind must still win.
    monkeypatch.setattr("connectonion.rem.chat.wechat_people",
                        lambda *a, **k: [{**r, "kind": "wechat"} for r in CONTACTS])
    return CliRunner().invoke(app, ["rem", "--root", str(tmp_path), *args])


def test_co_rem_map_dry_run_prints_what_it_would_make_and_writes_nothing(tmp_path, monkeypatch):
    _notebook(tmp_path)
    before = _tree(tmp_path)
    result = _cli(tmp_path, monkeypatch, "map", "people", "--source", "wechat", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would create 2 people, merge 1" in result.output
    assert "investigate people --source wechat --new" in result.output
    assert _tree(tmp_path) == before


def test_co_rem_map_refuses_a_kind_the_source_does_not_yield(tmp_path, monkeypatch):
    _notebook(tmp_path)
    before = _tree(tmp_path)
    result = _cli(tmp_path, monkeypatch, "map", "orgs", "--source", "wechat")
    assert result.exit_code == 2 and "wechat yields: people" in result.output
    assert _tree(tmp_path) == before


def test_co_rem_investigate_lists_a_sources_pages_new_first(tmp_path, monkeypatch):
    _notebook(tmp_path)
    assert _cli(tmp_path, monkeypatch, "map", "--source", "wechat").exit_code == 0
    result = _cli(tmp_path, monkeypatch, "--json", "investigate", "people", "--source", "wechat", "--list")
    assert result.exit_code == 0, result.output
    value = json.loads(result.output)
    value = value["data"]
    assert len(value["new"]) == 2 and value["existing"] == [MAIL_PERSON]
