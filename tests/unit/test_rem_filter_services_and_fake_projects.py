"""Institutional mailboxes and dated task folders are not personal projects."""

import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.map import build_map, project_groups, service_page
from connectonion.rem.scan import ONE_OFF_TASK, institutional_name, not_a_project


@pytest.mark.parametrize("term", [
    "Centre", "Center", "Institute", "Foundation", "Hub", "Lab", "Labs",
    "Department", "Society", "Association", "Initiative", "Council",
    "Office", "Team", "Club", "中心", "会议", "学院", "学会", "委员会",
])
def test_institutional_display_names_are_services(term):
    name = f"Innovation {term}"
    assert institutional_name(name)
    assert institutional_name(f"{term} Innovation")
    assert service_page(name, ["cic@example.edu"], None, set())


def test_personal_names_with_similar_letters_stay_people():
    assert not institutional_name("Labhira Stone")
    assert not institutional_name("Alice Councilman")
    assert institutional_name("AcmeLabs")
    assert not service_page("Alice Councilman", ["alice@example.edu"], None, set())


def test_institutional_sender_never_gets_a_people_page(tmp_path, monkeypatch):
    prepare(tmp_path)
    skills = tmp_path / "installed"
    skills.mkdir()
    rows = [
        {"name": "Innovation Centre", "address": "cic@example.edu", "mails": 8,
         "sent": 4, "received": 4, "first": "2026-09-01", "last": "2026-09-20"},
        {"name": "Ada Example", "address": "ada@example.edu", "mails": 8,
         "sent": 4, "received": 4, "first": "2026-09-01", "last": "2026-09-20"},
    ]
    monkeypatch.setattr("connectonion.rem.map._mail_rows", lambda *a, **kw: (rows, set()))
    monkeypatch.setattr("connectonion.rem.map.scan_projects", lambda *a, **kw: [])
    result = build_map(tmp_path, {}, {}, skill_directories=[skills])
    assert [(row["address"], row["classification"]) for row in result["automated_correspondents"]] == [
        ("cic@example.edu", "service desk")]
    assert {row["address"] for row in result["people"]} == {"ada@example.edu"}
    assert len(Notebook(tmp_path).people()) == 1
    assert [row["domain"] for row in result["orgs"]] == ["example.edu"]


def test_dated_scratch_folders_without_manifests_stay_out_across_dates(tmp_path):
    base = tmp_path / "Documents/Codex"
    rows = [{"path": str(base / date / "acme-project"), "repo": "", "origin": "",
             "sessions": 12, "turns": None, "first": date, "last": date}
            for date in ("2026-09-01", "2026-09-02", "2026-09-03")]
    for row in rows:
        assert not_a_project(row) == ONE_OFF_TASK
    dropped = []
    assert project_groups(rows, dropped) == {}
    assert {entry["path"] for entry in dropped} == {row["path"] for row in rows}


def test_prompt_fragment_folder_does_not_become_a_project_from_repetition(tmp_path):
    path = tmp_path / "work/fix-login"
    row = {"path": str(path), "repo": "", "origin": "", "sessions": 9,
           "turns": None, "first": "2026-09-01", "last": "2026-09-20"}
    assert "prompt-fragment" in not_a_project(row)
    assert project_groups([row]) == {}
    path.mkdir(parents=True)
    (path / "Makefile").write_text("all:\n\t@true\n")
    assert not_a_project(row) == ""


def test_dated_scratchpad_without_manifest_stays_out(tmp_path):
    path = tmp_path / "Scratchpad/2026-09-01/acme-project"
    row = {"path": str(path), "repo": "", "origin": "", "sessions": 12,
           "turns": None, "first": "2026-09-01", "last": "2026-09-20"}
    assert not_a_project(row) == ONE_OFF_TASK
    assert project_groups([row]) == {}


@pytest.mark.parametrize("manifest", ["pyproject.toml", "package.json", "Cargo.toml", "go.mod", "Makefile"])
def test_dated_scratch_folder_with_manifest_can_be_a_project(tmp_path, manifest):
    path = tmp_path / "Documents/Codex/2026-09-01/acme-project"
    path.mkdir(parents=True)
    (path / manifest).write_text("# fictional project\n")
    row = {"path": str(path), "repo": "", "origin": "", "sessions": 1,
           "turns": 1, "first": "2026-09-01", "last": "2026-09-01"}
    assert not_a_project(row) == ""
    assert list(project_groups([row])) == ["codex-scratch:acme-project"]


def test_repository_in_dated_scratch_folder_remains_a_project(tmp_path):
    path = tmp_path / "Documents/Codex/2026-09-01/acme-project"
    (path / ".git").mkdir(parents=True)
    row = {"path": str(path), "repo": str(path), "origin": "", "sessions": 1,
           "turns": 1, "first": "2026-09-01", "last": "2026-09-01"}
    assert not_a_project(row) == ""
    assert project_groups([row])
