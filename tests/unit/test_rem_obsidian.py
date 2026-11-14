"""Obsidian notes in REM sync and investigations.

A sync with Obsidian selected produces one item per changed note marked added,
modified or deleted; [[links]] and tags stay in the text so existing pages are found;
`co rem sync --dry-run` shows how many notes are pending.

Vault, inbox and notebook live under tmp_path; the model is a recording fake runner;
no network, no real vault, no real notebook.
"""

import json
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.rem import service
from connectonion.rem.config import prepare
from connectonion.rem.files import RemError, read_json, state_path
from connectonion.rem.obsidian import collect_notes, pending_notes
from connectonion.useful_tools import obsidian, obsidian_export as export
from tests.unit.test_obsidian import _notes_vault

pytestmark = pytest.mark.unit

NOTES = {
    "Course/lecture.md": "---\ntags: [exam]\n---\nLogic with [[Alice Smith]] for [[Project Atlas]] #project/atlas\n",
    "Course/Week1/intro.md": "第一周 intro\r\nsee [[Bob]] #week1\r\n",
    "Personal/diary.md": "private diary [[Alice Smith]]\n",
}


@pytest.fixture
def rem(tmp_path, monkeypatch):
    """A notebook initially approved for Course/ only; Personal/ starts outside the scope."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / "config"))
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(service, "codex_sessions_root", lambda: sessions)
    monkeypatch.setattr(service, "claude_projects_root", lambda: tmp_path / "no-claude")

    def refuse_network(*args, **kwargs):
        pytest.fail("Obsidian tests must not connect to a network")
    monkeypatch.setattr(socket.socket, "connect", refuse_network)
    monkeypatch.setattr(socket, "create_connection", refuse_network)

    vault = _notes_vault(tmp_path, NOTES, name="Wiki")
    root = tmp_path / "rem"
    prepare(root)
    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Course"])
    service.approve_sources(root)
    return root, vault


def _runner(calls):
    def runner(notebook, items, config, kind=""):
        calls.append((kind, items))
        return {"usage": {"input_tokens": 1, "output_tokens": 1}, "changed": []}
    return runner


def _items(calls):
    return [item for _, items in calls for item in items if str(item.get("source", "")).startswith("obsidian:")]


def _subscription(root):
    return service.subscriptions(root)["obsidian"]


def _dry(root):
    return service.run_sync(root, dry_run=True)["sources"]["obsidian"]


def _tree(path):
    return {str(p): p.read_bytes() for p in Path(path).rglob("*") if p.is_file()} if Path(path).exists() else {}


# -- one item per changed note, marked added / modified / deleted -------------------------

def test_first_sync_gives_one_added_item_per_selected_note(rem):
    root, vault = rem
    calls = []

    result = service.run_sync(root, runner=_runner(calls))

    assert result["outcome"] == "completed"
    items = _items(calls)
    assert sorted(item["origin"] for item in items) == ["Course/Week1/intro.md", "Course/lecture.md"]
    assert all(item["change_type"] == "added" for item in items)
    assert len({item["source"] for item in items}) == len(items)
    assert result["items_by_source"].get("obsidian") == 2
    assert {kind for kind, _ in calls} == {"obsidian"}


def test_notes_outside_the_folders_never_reach_the_model(rem):
    root, vault = rem
    calls = []

    service.run_sync(root, runner=_runner(calls))

    text = json.dumps(calls, ensure_ascii=False)
    assert "Personal/diary.md" not in text and "private diary" not in text


def test_a_second_sync_without_changes_gives_no_items(rem):
    root, vault = rem
    service.run_sync(root, runner=_runner([]))
    calls = []

    result = service.run_sync(root, runner=_runner(calls))

    assert result["outcome"] == "no_change"
    assert _items(calls) == []


def test_modified_and_deleted_notes_are_marked(rem):
    root, vault = rem
    service.run_sync(root, runner=_runner([]))
    (vault / "Course/lecture.md").write_text("Rewritten with [[Carol]]\n", encoding="utf-8")
    (vault / "Course/Week1/intro.md").unlink()
    calls = []

    service.run_sync(root, runner=_runner(calls))

    items = {item["origin"]: item for item in _items(calls)}
    assert set(items) == {"Course/lecture.md", "Course/Week1/intro.md"}
    modified, deleted = items["Course/lecture.md"], items["Course/Week1/intro.md"]
    assert modified["change_type"] == "modified" and "modified" in modified["text"]
    assert "[[Carol]]" in modified["text"]
    assert modified["previous_source_id"] and modified["previous_source_id"] != modified["source"]
    assert deleted["change_type"] == "deleted" and "deleted" in deleted["text"]
    assert "第一周" not in deleted["text"]                  # a deletion carries no old body
    assert deleted["links"] == [] and deleted["tags"] == []


def test_a_new_note_after_the_first_sync_is_one_added_item(rem):
    root, vault = rem
    service.run_sync(root, runner=_runner([]))
    (vault / "Course/new.md").write_text("fresh [[Dana]]\n", encoding="utf-8")
    calls = []

    service.run_sync(root, runner=_runner(calls))

    [item] = _items(calls)
    assert item["origin"] == "Course/new.md" and item["change_type"] == "added"


def test_an_unchanged_note_is_not_sent_again_when_another_changes(rem):
    root, vault = rem
    service.run_sync(root, runner=_runner([]))
    (vault / "Course/lecture.md").write_text("only this one changed\n", encoding="utf-8")
    calls = []

    service.run_sync(root, runner=_runner(calls))

    assert [item["origin"] for item in _items(calls)] == ["Course/lecture.md"]


# -- [[links]] and tags stay in the text --------------------------------------------

def test_links_and_tags_are_kept_in_the_item_text(rem):
    root, vault = rem
    calls = []

    service.run_sync(root, runner=_runner(calls))

    items = {item["origin"]: item for item in _items(calls)}
    lecture = items["Course/lecture.md"]
    for literal in ("[[Alice Smith]]", "[[Project Atlas]]", "#project/atlas", "tags: [exam]"):
        assert literal in lecture["text"]
    assert {link["target"] for link in lecture["links"]} >= {"Alice Smith", "Project Atlas"}
    assert {"exam", "project/atlas"} <= set(lecture["tags"])
    assert "[[Bob]]" in items["Course/Week1/intro.md"]["text"] and "#week1" in items["Course/Week1/intro.md"]["text"]


def test_note_text_is_passed_whole_and_unchanged(rem):
    root, vault = rem
    calls = []

    service.run_sync(root, runner=_runner(calls))

    items = {item["origin"]: item for item in _items(calls)}
    for path in ("Course/lecture.md", "Course/Week1/intro.md"):
        assert NOTES[path] in items[path]["text"]


def test_each_item_is_traceable_to_its_note_and_collection(rem):
    root, vault = rem
    calls = []

    result = service.run_sync(root, runner=_runner(calls))

    for item in _items(calls):
        assert export.SOURCE_ID.fullmatch(item["source"])
        assert item["note_id"] == item["source"].split(":")[2]
        assert item["source"] in result["collection"]["obsidian"]["source_ids"]


# -- dry run shows how many notes are pending ------------------------------------------

def test_dry_run_before_any_collection_says_the_count_is_unknown(rem, tmp_path):
    root, vault = rem

    pending = _dry(root)

    assert pending["body_reads"] is False and pending["initialized"] is False
    assert pending["pending_notes"] is None
    assert not (tmp_path / "inbox").exists()


def test_dry_run_counts_collected_notes_waiting_for_sync(rem):
    root, vault = rem
    source = _subscription(root)
    export.sync_notes(vault, Path(source["root"]), folders=["Course"], notebook_root=root)

    pending = _dry(root)

    assert pending["initialized"] is True
    assert pending["pending_notes"] == 2 and pending["pending_events"] == 2
    service.run_sync(root, runner=_runner([]))
    assert _dry(root)["pending_notes"] == 0


def test_dry_run_counts_a_modified_and_a_deleted_note(rem):
    root, vault = rem
    service.run_sync(root, runner=_runner([]))
    (vault / "Course/lecture.md").write_text("changed\n", encoding="utf-8")
    (vault / "Course/Week1/intro.md").unlink()
    source = _subscription(root)
    export.sync_notes(vault, Path(source["root"]), folders=["Course"], notebook_root=root)

    assert _dry(root)["pending_notes"] == 2


def test_dry_run_reads_no_body_and_writes_nothing(rem, monkeypatch, tmp_path):
    root, vault = rem
    source = _subscription(root)
    export.sync_notes(vault, Path(source["root"]), folders=["Course"], notebook_root=root)
    before = (_tree(tmp_path / "inbox"), _tree(root), _tree(vault))
    monkeypatch.setattr(obsidian, "_read_markdown", lambda *a, **k: pytest.fail("dry run read a note"))
    monkeypatch.setattr(export, "load_snapshots", lambda *a, **k: pytest.fail("dry run read a saved body"))
    monkeypatch.setattr(export, "sync_notes", lambda *a, **k: pytest.fail("dry run collected"))

    assert _dry(root)["pending_notes"] == 2
    assert (_tree(tmp_path / "inbox"), _tree(root), _tree(vault)) == before


def test_dry_run_json_from_the_cli(rem):
    root, vault = rem
    source = _subscription(root)
    export.sync_notes(vault, Path(source["root"]), folders=["Course"], notebook_root=root)
    from connectonion.cli.main import app

    result = CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "sync", "--dry-run"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["sources"]["obsidian"]["pending_notes"] == 2


# -- batching, approval and failures ---------------------------------------------------

def test_a_batch_limit_leaves_the_rest_pending(rem):
    root, vault = rem
    source = _subscription(root)
    export.sync_notes(vault, Path(source["root"]), folders=["Course"], notebook_root=root)

    batch = collect_notes(source, {}, 1, 1_000_000, notebook_root=root)

    assert len(batch.items) == 1
    assert pending_notes(source, batch.progress, notebook_root=root)["pending_notes"] == 1
    assert pending_notes(source, {}, notebook_root=root)["pending_notes"] == 2     # not accepted yet


def test_an_unapproved_source_is_neither_collected_nor_read(rem, tmp_path):
    root, vault = rem
    from connectonion.rem.files import write_json
    saved = read_json(state_path(root, "subscriptions.json"), {})
    saved["obsidian"]["consented"] = False                 # chosen, but not yet approved by start
    write_json(state_path(root, "subscriptions.json"), saved)
    calls = []

    with pytest.raises(RemError) as caught:
        service.run_sync(root, runner=_runner(calls))

    assert "start" in str(caught.value)
    assert _items(calls) == []
    assert not any((tmp_path / "inbox").rglob("*.jsonl")) if (tmp_path / "inbox").exists() else True


def test_an_unreadable_note_stops_obsidian_without_moving_progress(rem):
    root, vault = rem
    service.run_sync(root, runner=_runner([]))
    progress = read_json(state_path(root, "progress.json"), {})
    (vault / "Course/lecture.md").write_text("changed\n", encoding="utf-8")
    (vault / "Course/bad.md").write_bytes(b"\xff\xfe not utf-8")
    calls = []

    with pytest.raises(RemError):
        service.run_sync(root, runner=_runner(calls))

    assert _items(calls) == []
    assert read_json(state_path(root, "progress.json"), {}).get("obsidian") == progress.get("obsidian")


def test_consumed_changes_are_recorded_for_source_logs(rem):
    root, vault = rem
    calls = []
    service.run_sync(root, runner=_runner(calls))
    source_id = _items(calls)[0]["source"]

    log = service.source_logs(root, source_id)

    assert log["path"] == _items(calls)[0]["origin"]
    assert log["ingestion_status"] == "ingested" and log["ingested_at"]


# -- adding folders keeps existing selections and consumption progress ------------------

@pytest.mark.parametrize("changed_existing", [False, True], ids=["unchanged", "modified"])
def test_new_folders_wait_for_approval_and_join_incremental_sync(changed_existing, rem):
    root, vault = rem
    calls = []
    service.run_sync(root, runner=_runner(calls))
    old_id = _items(calls)[0]["source"]
    before = _subscription(root)
    progress = read_json(state_path(root, "progress.json"), {})
    inbox = _tree(before["root"])
    original = _tree(vault)

    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Personal"])

    source = _subscription(root)
    assert source["folders"] == ["Course", "Personal"] and source["consented"] is False
    assert source["source_instance_id"] == before["source_instance_id"]
    assert read_json(state_path(root, "progress.json"), {}) == progress
    assert _tree(before["root"]) == inbox and _tree(vault) == original
    assert service.source_logs(root, old_id)["ingestion_status"] == "ingested"
    calls = []
    with pytest.raises(RemError, match="start"):
        service.run_sync(root, source="obsidian", runner=_runner(calls))
    assert not calls and _tree(before["root"]) == inbox
    if changed_existing:
        (vault / "Course/lecture.md").write_text("Changed in the old folder\n", encoding="utf-8")
    service.approve_sources(root)
    result = service.run_sync(root, source="obsidian", runner=_runner(calls))
    assert result["outcome"] == "completed"
    expected = {"Personal/diary.md": "added"}
    if changed_existing:
        expected["Course/lecture.md"] = "modified"
    assert {item["origin"]: item["change_type"] for item in _items(calls)} == expected
    assert len(_items(calls)) == len(expected)
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "no_change"


@pytest.mark.parametrize("folders", [["Course"], ["Course/Week1"], ["Course", "Course/Week1", "Course"]])
def test_an_already_covered_folder_keeps_approval_and_progress(folders, rem):
    root, vault = rem
    service.run_sync(root, runner=_runner([]))
    before = _subscription(root)
    progress = read_json(state_path(root, "progress.json"), {})
    consent = state_path(root, "consent.json").read_bytes()

    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=folders)

    assert _subscription(root) == before
    assert state_path(root, "consent.json").read_bytes() == consent
    assert read_json(state_path(root, "progress.json"), {}) == progress
    calls = []
    assert service.run_sync(root, source="obsidian", runner=_runner(calls))["outcome"] == "no_change"
    assert not calls


def test_extending_a_child_folder_to_its_parent_does_not_replay_notes(rem):
    root, vault = rem
    service.toggle_source(root, "obsidian", False)
    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Course/Week1"])
    service.approve_sources(root)
    service.run_sync(root, source="obsidian", runner=_runner([]))

    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Course"])

    assert _subscription(root)["folders"] == ["Course"]
    assert _subscription(root)["consented"] is False
    service.approve_sources(root)
    calls = []
    service.run_sync(root, source="obsidian", runner=_runner(calls))
    [item] = _items(calls)
    assert item["origin"] == "Course/lecture.md" and item["change_type"] == "added"
    assert "Personal/diary.md" not in json.dumps(calls)


def test_a_failed_folder_add_preserves_approval_history_and_progress(rem, monkeypatch):
    root, vault = rem
    service.run_sync(root, runner=_runner([]))
    before = _tree(root), _tree(_subscription(root)["root"]), _tree(vault)

    def fail_settings(path, value):
        raise RemError("Storage temporarily unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(service, "write_json", fail_settings)
        with pytest.raises(RemError, match="Storage temporarily unavailable"):
            service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Personal"])

    assert (_tree(root), _tree(_subscription(root)["root"]), _tree(vault)) == before
    assert _subscription(root)["consented"] is True


# -- removing explicitly selected folders ----------------------------------------------

def test_removing_a_folder_preserves_history_and_waits_for_scope_approval(rem):
    root, vault = rem
    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Personal"])
    service.approve_sources(root)
    calls = []
    service.run_sync(root, source="obsidian", runner=_runner(calls))
    source = _subscription(root)
    removed_id = next(item["source"] for item in _items(calls) if item["origin"] == "Personal/diary.md")
    page = root / "knowledge" / "retained.md"
    page.parent.mkdir(exist_ok=True)
    page.write_text("Existing knowledge stays until reviewed\n", encoding="utf-8")
    before = _tree(vault), _tree(source["root"]), state_path(root, "progress.json").read_bytes()
    consent = state_path(root, "consent.json").read_bytes()

    service.toggle_source(root, "obsidian", False, folders=["Personal"])

    selected = _subscription(root)
    assert selected["folders"] == ["Course"] and selected["enabled"] is True
    assert selected["consented"] is False and selected["source_instance_id"] == source["source_instance_id"]
    assert (_tree(vault), _tree(source["root"]), state_path(root, "progress.json").read_bytes()) == before
    assert state_path(root, "consent.json").read_bytes() == consent
    assert page.read_text(encoding="utf-8") == "Existing knowledge stays until reviewed\n"
    assert service.source_logs(root, removed_id)["ingestion_status"] == "ingested"
    calls = []
    with pytest.raises(RemError, match="start"):
        service.run_sync(root, source="obsidian", runner=_runner(calls))
    assert not calls and _tree(source["root"]) == before[1]


@pytest.mark.parametrize("consumed", [False, True], ids=["pending", "processed"])
def test_sync_after_folder_removal_withdraws_support_without_reading_removed_bodies(consumed, rem, monkeypatch):
    root, vault = rem
    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Personal"])
    service.approve_sources(root)
    source = _subscription(root)
    export.sync_notes(vault, Path(source["root"]), folders=source["folders"], notebook_root=root)
    if consumed:
        service.run_sync(root, source="obsidian", runner=_runner([]))
    service.toggle_source(root, "obsidian", False, folders=["Personal"])
    (vault / "Personal/diary.md").write_text("REMOVED-FOLDER-BODY-MUST-STAY-PRIVATE\n", encoding="utf-8")
    if consumed:
        (vault / "Course/lecture.md").write_text("Updated retained note for [[Alice Smith]]\n", encoding="utf-8")
    read_markdown = obsidian._read_markdown

    def read_selected(scope, path):
        assert not path.is_relative_to(vault / "Personal"), "removed folder body was read"
        return read_markdown(scope, path)

    monkeypatch.setattr(obsidian, "_read_markdown", read_selected)
    service.approve_sources(root)
    calls = []

    result = service.run_sync(root, source="obsidian", runner=_runner(calls))

    assert result["outcome"] == "completed"
    items = _items(calls)
    [withdrawal] = [item for item in items if item["origin"] == "Personal/diary.md"]
    assert withdrawal["change_type"] == "deleted"
    assert "scope_removed" in withdrawal["text"]
    assert "private diary" not in json.dumps(calls) and "REMOVED-FOLDER-BODY" not in json.dumps(calls)
    assert sum(item["origin"] == "Course/lecture.md" for item in items) == 1
    assert ("Updated retained note" if consumed else "Logic with") in json.dumps(calls)
    assert sum(item["origin"] == "Course/Week1/intro.md" for item in items) == (0 if consumed else 1)
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "no_change"


def test_investigation_respects_removed_folder_before_another_collection(rem):
    root, vault = rem
    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Personal"])
    service.approve_sources(root)
    service.run_sync(root, source="obsidian", runner=_runner([]))

    service.toggle_source(root, "obsidian", False, folders=["Personal"])
    service.approve_sources(root)
    notes, coverage = _gather(root, "Alice Smith")

    assert _origins(notes) == ["Course/lecture.md"]
    assert "private diary" not in json.dumps(notes)
    assert len(coverage) == 1 and "not searched" not in coverage[0]


def test_last_folder_removal_and_readdition_resume_saved_progress(rem):
    root, vault = rem
    calls = []
    service.run_sync(root, source="obsidian", runner=_runner(calls))
    original = _items(calls)[0]["source"]
    progress = state_path(root, "progress.json").read_bytes()

    service.toggle_source(root, "obsidian", False, folders=["Course"])

    assert "obsidian" not in service.subscriptions(root)
    assert state_path(root, "progress.json").read_bytes() == progress
    assert service.source_logs(root, original)["ingestion_status"] == "ingested"
    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Course"])
    service.approve_sources(root)
    calls = []
    assert service.run_sync(root, source="obsidian", runner=_runner(calls))["outcome"] == "no_change"
    assert not calls


def test_a_failed_folder_removal_preserves_approval_history_and_progress(rem, monkeypatch):
    root, vault = rem
    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Personal"])
    service.approve_sources(root)
    service.run_sync(root, source="obsidian", runner=_runner([]))
    source = _subscription(root)
    before = _tree(root), _tree(source["root"]), _tree(vault)

    def fail_settings(path, value):
        raise RemError("Storage temporarily unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(service, "write_json", fail_settings)
        with pytest.raises(RemError, match="Storage temporarily unavailable"):
            service.toggle_source(root, "obsidian", False, folders=["Personal"])

    assert (_tree(root), _tree(source["root"]), _tree(vault)) == before
    assert _subscription(root)["consented"] is True


@pytest.mark.parametrize("enabled", [False, True], ids=["remove", "add"])
def test_folder_changes_cannot_write_a_notebook_inside_the_saved_vault(enabled, rem):
    root, vault = rem
    inside = vault / "REM"
    state_path(inside, "subscriptions.json").parent.mkdir(parents=True)
    state_path(inside, "subscriptions.json").write_bytes(state_path(root, "subscriptions.json").read_bytes())
    before = _tree(vault)

    with pytest.raises(RemError, match="outside the original Obsidian vault"):
        service.toggle_source(inside, "obsidian", enabled, folders=["Course"])

    assert _tree(vault) == before


# -- unregistering and selecting another scope -----------------------------------------

def test_unregister_preserves_notes_history_pages_and_progress(rem):
    root, vault = rem
    calls = []
    service.run_sync(root, runner=_runner(calls))
    source_id = _items(calls)[0]["source"]
    inbox = Path(_subscription(root)["root"])
    page = root / "knowledge" / "retained.md"
    page.parent.mkdir(exist_ok=True)
    page.write_text("Existing independently supported knowledge\n", encoding="utf-8")
    before_vault, before_inbox = _tree(vault), _tree(inbox)
    before_progress = read_json(state_path(root, "progress.json"), {})

    service.toggle_source(root, "obsidian", False)

    assert "obsidian" not in service.subscriptions(root)
    assert _tree(vault) == before_vault and _tree(inbox) == before_inbox
    assert page.read_text(encoding="utf-8") == "Existing independently supported knowledge\n"
    assert read_json(state_path(root, "progress.json"), {}) == before_progress
    assert service.source_logs(root, source_id)["ingestion_status"] == "ingested"
    with pytest.raises(RemError):
        service.run_sync(root, source="obsidian", runner=_runner([]))


def test_replacing_a_vault_requires_new_consent_and_keeps_old_receipts(rem, tmp_path):
    root, vault = rem
    calls = []
    service.run_sync(root, runner=_runner(calls))
    old_id = _items(calls)[0]["source"]
    original_log = service.source_logs(root, old_id)
    replacement = _notes_vault(tmp_path, {"Other/new.md": "Replacement [[Dana]]\n"}, name="OtherWiki")
    before = _tree(vault), _tree(replacement)
    service.toggle_source(root, "obsidian", False)

    service.toggle_source(root, "obsidian", True, vault=str(replacement), folders=["Other"])

    assert _subscription(root)["consented"] is False
    assert service.source_logs(root, old_id) == original_log
    calls = []
    with pytest.raises(RemError, match="start"):
        service.run_sync(root, source="obsidian", runner=_runner(calls))
    assert not calls
    service.approve_sources(root)
    result = service.run_sync(root, source="obsidian", runner=_runner(calls))
    assert result["outcome"] == "completed"
    assert [item["origin"] for item in _items(calls)] == ["Other/new.md"]
    assert old_id not in {item["source"] for item in _items(calls)}
    assert service.source_logs(root, old_id) == original_log
    assert (_tree(vault), _tree(replacement)) == before


def test_returning_to_a_vault_resumes_without_replaying_old_notes(rem, tmp_path):
    root, vault = rem
    calls = []
    service.run_sync(root, runner=_runner(calls))
    first_id = _items(calls)[0]["source"]
    other = _notes_vault(tmp_path, {"Other/new.md": "Other\n"}, name="OtherWiki")
    service.toggle_source(root, "obsidian", False)
    service.toggle_source(root, "obsidian", True, vault=str(other), folders=["Other"])
    service.approve_sources(root)
    calls = []
    service.run_sync(root, source="obsidian", runner=_runner(calls))
    other_id = _items(calls)[0]["source"]
    service.toggle_source(root, "obsidian", False)

    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Course"])
    service.approve_sources(root)
    calls = []
    result = service.run_sync(root, source="obsidian", runner=_runner(calls))

    assert result["outcome"] == "no_change" and not _items(calls)
    assert service.source_logs(root, first_id)["ingestion_status"] == "ingested"
    assert service.source_logs(root, other_id)["ingestion_status"] == "ingested"
    (vault / "Course/lecture.md").write_text("Changed while registered again\n", encoding="utf-8")
    service.run_sync(root, source="obsidian", runner=_runner(calls))
    [item] = _items(calls)
    assert item["origin"] == "Course/lecture.md" and item["change_type"] == "modified"


def test_reselecting_folders_keeps_scope_withdrawals_and_new_material(rem):
    root, vault = rem
    service.run_sync(root, runner=_runner([]))
    before = _tree(vault)
    service.toggle_source(root, "obsidian", False)

    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Course/Week1", "Personal"])
    service.approve_sources(root)
    calls = []
    result = service.run_sync(root, source="obsidian", runner=_runner(calls))

    assert result["outcome"] == "completed"
    items = {item["origin"]: item for item in _items(calls)}
    assert set(items) == {"Course/lecture.md", "Personal/diary.md"}
    assert items["Course/lecture.md"]["change_type"] == "deleted"
    assert "Logic with" not in items["Course/lecture.md"]["text"]
    assert items["Personal/diary.md"]["change_type"] == "added"
    assert _tree(vault) == before


def test_reregistering_detects_changes_made_while_removed(rem):
    root, vault = rem
    service.run_sync(root, runner=_runner([]))
    service.toggle_source(root, "obsidian", False)
    (vault / "Course/lecture.md").write_text("Changed while removed\n", encoding="utf-8")

    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Course"])
    assert _subscription(root)["consented"] is False
    service.approve_sources(root)
    calls = []
    service.run_sync(root, source="obsidian", runner=_runner(calls))

    [item] = _items(calls)
    assert item["origin"] == "Course/lecture.md" and item["change_type"] == "modified"
    assert "Changed while removed" in item["text"]


@pytest.mark.parametrize("failed_file", ["progress.json", "subscriptions.json"])
def test_a_failed_vault_switch_keeps_history_and_can_be_retried(failed_file, rem, tmp_path, monkeypatch):
    root, vault = rem
    calls = []
    service.run_sync(root, runner=_runner(calls))
    old_id = _items(calls)[0]["source"]
    old_log = service.source_logs(root, old_id)
    other = _notes_vault(tmp_path, {"Notes/new.md": "New vault\n"}, name="OtherWiki")
    service.toggle_source(root, "obsidian", False)
    write = service.write_json

    def fail_save(path, value):
        if path == state_path(root, failed_file):
            raise RemError("Storage temporarily unavailable")
        write(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(service, "write_json", fail_save)
        with pytest.raises(RemError, match="Storage temporarily unavailable"):
            service.toggle_source(root, "obsidian", True, vault=str(other), folders=["Notes"])
    assert "obsidian" not in service.subscriptions(root)
    assert service.source_logs(root, old_id) == old_log
    service.toggle_source(root, "obsidian", True, vault=str(other), folders=["Notes"])
    service.approve_sources(root)
    calls = []
    assert service.run_sync(root, source="obsidian", runner=_runner(calls))["outcome"] == "completed"
    assert [item["origin"] for item in _items(calls)] == ["Notes/new.md"]
    service.toggle_source(root, "obsidian", False)
    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Course"])
    service.approve_sources(root)
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "no_change"


# -- Story 29: investigating a person or project includes the notes about them ------------
#
# AC: investigating a subject gathers notes in the chosen folders that link to or name it,
# and the coverage line says why Obsidian was not searched when the vault is unavailable
# or no folder is chosen. Investigation reads saved snapshots only (co rem sync collects).

from connectonion.rem import investigate as inv

PERSON, PROJECT_PAGE = "people/alice-smith.md", "projects/project-atlas.md"


def _gather(root, subject, record=PERSON, *, handles=(), days=3650, subscriptions=None):
    subs = service.subscriptions(root) if subscriptions is None else subscriptions
    items, coverage = inv.gather(subject, [subject, *handles], days=days, clients={}, subscriptions=subs,
                                 record=record, archive_root=root)
    notes = [item for item in items if str(item.get("source", "")).startswith("obsidian:")]
    return notes, [line for line in coverage if line.startswith("obsidian:")]


def _origins(notes):
    return sorted(note["origin"] for note in notes)


@pytest.fixture
def synced(rem):
    """rem plus a note that names Alice in plain text, collected by one sync."""
    root, vault = rem
    (vault / "Course/meeting.md").write_text(
        "Met Alice Smith about the budget. Alice Smithson was not there.\n", encoding="utf-8")
    service.run_sync(root, runner=_runner([]))
    return root, vault


def test_investigating_a_person_gathers_notes_that_link_to_or_name_them(synced):
    root, vault = synced
    notes, coverage = _gather(root, "Alice Smith")
    assert _origins(notes) == ["Course/lecture.md", "Course/meeting.md"]
    by_origin = {note["origin"]: note for note in notes}
    assert "[[Alice Smith]]" in by_origin["Course/lecture.md"]["text"]       # the link stays in the text
    assert "link target/alias" in by_origin["Course/lecture.md"]["matched_by"]
    assert "body mention" in by_origin["Course/meeting.md"]["matched_by"]
    assert len(coverage) == 1 and "not searched" not in coverage[0]


def test_investigating_a_project_gathers_notes_that_link_to_it(synced):
    root, vault = synced
    notes, _ = _gather(root, "Project Atlas", PROJECT_PAGE)
    assert _origins(notes) == ["Course/lecture.md"]


def test_notes_outside_the_chosen_folders_are_never_gathered(synced):
    root, vault = synced
    notes, _ = _gather(root, "Alice Smith")
    assert "Personal/diary.md" not in _origins(notes)
    assert all("private diary" not in note["text"] for note in notes)


def test_a_longer_name_or_another_subject_is_not_a_match(synced):
    root, vault = synced
    # meeting.md names "Alice Smithson" itself; lecture.md only links [[Alice Smith]].
    assert _origins(_gather(root, "Alice Smithson")[0]) == ["Course/meeting.md"]
    notes, coverage = _gather(root, "Carol Jones")
    assert notes == [] and "0 subject candidate" in coverage[0]


def test_a_name_inside_a_longer_word_does_not_match(rem):
    root, vault = rem
    (vault / "Course/notes.md").write_text("Bobby and Bobcat came; [[Bob]] did not.\n", encoding="utf-8")
    service.run_sync(root, runner=_runner([]))
    notes, _ = _gather(root, "Bobb")
    assert notes == []


def test_a_cjk_name_is_found_without_spaces_around_it(rem):
    root, vault = rem
    (vault / "Course/组会.md").write_text("今天张伟讲了实验结果。\n", encoding="utf-8")
    service.run_sync(root, runner=_runner([]))
    notes, _ = _gather(root, "张伟", "people/zhang-wei.md")
    assert _origins(notes) == ["Course/组会.md"]


def test_the_window_uses_the_notes_modification_time(rem):
    root, vault = rem
    recent = vault / "Course/recent.md"
    recent.write_text("Call with [[Alice Smith]] today.\n", encoding="utf-8")
    service.run_sync(root, runner=_runner([]))
    notes, _ = _gather(root, "Alice Smith", days=1)                # lecture.md is from 2026-09-21
    assert _origins(notes) == ["Course/recent.md"]


def test_same_named_notes_are_not_merged_and_a_note_path_chooses_one(rem):
    root, vault = rem
    for folder in ("Course/Team A", "Course/Team B"):
        (vault / folder).mkdir(parents=True)
        (vault / folder / "Alice Smith.md").write_text(f"Alice in {folder}\n", encoding="utf-8")
    service.run_sync(root, runner=_runner([]))
    notes, coverage = _gather(root, "Alice Smith")
    assert notes == []
    assert "ambiguous" in coverage[0] and "not searched" in coverage[0] and "--handle" in coverage[0]
    notes, coverage = _gather(root, "Alice Smith", handles=["Course/Team A/Alice Smith.md"])
    assert "Course/Team A/Alice Smith.md" in _origins(notes)
    assert "Course/Team B/Alice Smith.md" not in _origins(notes)


def test_a_deleted_note_is_not_gathered(synced):
    root, vault = synced
    (vault / "Course/meeting.md").unlink()
    service.run_sync(root, runner=_runner([]))
    assert _origins(_gather(root, "Alice Smith")[0]) == ["Course/lecture.md"]


def test_investigation_reads_saved_notes_without_changing_the_vault_or_sync_progress(synced):
    root, vault = synced
    (vault / "Course/unsynced.md").write_text("Lunch with Alice Smith.\n", encoding="utf-8")
    vault_before, inbox_before = _tree(vault), _tree(_subscription(root)["root"])
    progress_before = read_json(state_path(root, "progress.json"), {}).get("obsidian")

    notes, _ = _gather(root, "Alice Smith")

    assert "Course/unsynced.md" not in _origins(notes)               # not collected yet: not read
    assert _tree(vault) == vault_before and _tree(_subscription(root)["root"]) == inbox_before
    assert read_json(state_path(root, "progress.json"), {}).get("obsidian") == progress_before


# -- why Obsidian was not searched --------------------------------------------------------

def test_no_folder_chosen_says_so(synced):
    root, vault = synced
    subscription = {**_subscription(root), "folders": []}
    notes, coverage = _gather(root, "Alice Smith", subscriptions={"obsidian": subscription})
    assert notes == [] and coverage and "no folder chosen" in coverage[0] and "not searched" in coverage[0]


def test_an_unavailable_vault_says_so(synced, tmp_path):
    root, vault = synced
    vault.rename(tmp_path / "vault-moved-away")
    notes, coverage = _gather(root, "Alice Smith")
    assert notes == [] and coverage and "unavailable" in coverage[0] and "not searched" in coverage[0]


@pytest.mark.parametrize("change, words", [
    ({"consented": False}, "not approved"),
    ({"enabled": False}, "disabled"),
])
def test_a_source_that_may_not_be_read_says_why(synced, change, words):
    root, vault = synced
    subscription = {**_subscription(root), **change}
    notes, coverage = _gather(root, "Alice Smith", subscriptions={"obsidian": subscription})
    assert notes == [] and words in coverage[0] and "not searched" in coverage[0]


def test_registered_but_never_collected_says_so(rem):
    root, vault = rem
    notes, coverage = _gather(root, "Alice Smith")
    assert notes == [] and "nothing collected yet" in coverage[0] and "not searched" in coverage[0]


def test_unregistered_obsidian_says_so(synced):
    root, vault = synced
    notes, coverage = _gather(root, "Alice Smith", subscriptions={})
    assert notes == [] and coverage == [
        "obsidian: not registered; not searched (co rem sources add obsidian --help)"]


def test_organisation_pages_do_not_search_notes(synced):
    root, vault = synced
    notes, coverage = _gather(root, "Atlas Pty", "orgs/atlas.md")
    assert notes == [] and "not searched" in coverage[0]


def test_investigate_hands_the_notes_and_their_reading_rules_to_the_writer(synced):
    root, vault = synced
    inv.Notebook(root).stub_person(PERSON, "Alice Smith", [])
    received = []

    def runner(notebook, items, config, stage):
        received.extend(items)
        return {"changed": []}

    result = inv.investigate(root, PERSON, "Alice Smith", ["Alice Smith"], days=3650, clients={},
                             subscriptions=service.subscriptions(root), runner=runner)

    origins = sorted(item.get("origin") for item in received if str(item.get("source", "")).startswith("obsidian:"))
    assert origins == ["Course/lecture.md", "Course/meeting.md"]
    assert any(item.get("role") == "obsidian-scope" for item in received)
    assert any(line.startswith("obsidian:") for line in result["coverage"])


# -- multiple vaults: each explicit folder selection keeps its own history ---------------

@pytest.fixture
def two_vaults(rem, tmp_path):
    root, vault = rem
    other = _notes_vault(tmp_path, {
        "Course/lecture.md": "Other vault evidence for [[Alice Smith]] #other\n",
        "Course/notes.md": "Other work on [[Project Atlas]]\n",
        "Personal/diary.md": "OTHER-PRIVATE-NOTE\n",
    }, name="OtherWiki")
    service.toggle_source(root, "obsidian", True, vault=str(other), folders=["Course"])
    return root, vault, other


def _vault_sources(root):
    return {Path(sub["vault"]): sub for sub in service.subscriptions(root).values()
            if sub.get("kind") == "obsidian"}


def test_multiple_vault_registration_is_metadata_only_and_requires_new_approval(rem, tmp_path):
    root, vault = rem
    calls = []
    service.run_sync(root, source="obsidian", runner=_runner(calls))
    source_id = _items(calls)[0]["source"]
    receipt = service.source_logs(root, source_id)
    before = _tree(_subscription(root)["root"]), state_path(root, "progress.json").read_bytes()
    consent = state_path(root, "consent.json").read_bytes()
    other = _notes_vault(tmp_path, {"Course/new.md": "Other vault\n"}, name="OtherWiki")
    original = _tree(vault), _tree(other)

    service.toggle_source(root, "obsidian", True, vault=str(other), folders=["Course"])

    sources = _vault_sources(root)
    assert set(sources) == {vault, other}
    assert len({s["source_instance_id"] for s in sources.values()}) == 2
    assert not any(s["consented"] for s in sources.values())
    assert not Path(sources[other]["root"]).exists()
    assert (_tree(sources[vault]["root"]), state_path(root, "progress.json").read_bytes()) == before
    assert state_path(root, "consent.json").read_bytes() == consent
    assert service.source_logs(root, source_id) == receipt
    assert (_tree(vault), _tree(other)) == original
    with pytest.raises(RemError, match="start"):
        service.run_sync(root, source="obsidian", runner=_runner([]))
    assert not Path(sources[other]["root"]).exists()


def test_multi_vault_dry_run_counts_saved_backlogs_without_scanning_or_writing(two_vaults, monkeypatch):
    root, vault, other = two_vaults
    pending = _dry(root)
    assert pending["pending_notes"] is None and not pending["initialized"]
    source = _vault_sources(root)[vault]
    export.sync_notes(vault, Path(source["root"]), folders=["Course"], notebook_root=root)
    assert _dry(root)["pending_notes"] is None          # the other vault is still unknown
    source = _vault_sources(root)[other]
    export.sync_notes(other, Path(source["root"]), folders=["Course"], notebook_root=root)
    before = _tree(root), _tree(vault), _tree(other), _tree(Path(source["root"]).parent)

    def no_bodies(*args, **kwargs):
        pytest.fail("dry-run must not read a note body or collect a vault")
    monkeypatch.setattr(obsidian, "_read_markdown", no_bodies)
    monkeypatch.setattr(export, "load_snapshots", no_bodies)
    monkeypatch.setattr(export, "sync_notes", no_bodies)

    pending = service.run_sync(root, source="obsidian", dry_run=True)["sources"]["obsidian"]

    assert pending["pending_notes"] == pending["pending_events"] == 4
    assert pending["body_reads"] is False and pending["initialized"]
    assert {row["vault"]: row["pending_notes"] for row in pending["vaults"]} == {str(vault): 2, str(other): 2}
    assert (_tree(root), _tree(vault), _tree(other), _tree(Path(source["root"]).parent)) == before


def test_multi_vault_sync_uses_distinct_ids_receipts_and_collection_reports(two_vaults):
    root, vault, other = two_vaults
    original = _tree(vault), _tree(other)
    service.approve_sources(root)
    calls = []

    result = service.run_sync(root, source="obsidian", runner=_runner(calls))

    items = _items(calls)
    assert result["outcome"] == "completed" and result["items_by_source"] == {"obsidian": 4}
    assert {kind for kind, _ in calls} == {"obsidian"}
    assert len(items) == len({item["source"] for item in items}) == 4
    same_path = [item for item in items if item["origin"] == "Course/lecture.md"]
    assert len(same_path) == 2 and same_path[0]["text"] != same_path[1]["text"]
    collection = result["collection"]["obsidian"]
    assert collection["appended_records"] == collection["scanned_notes"] == 4
    assert {v["vault"] for v in collection["vaults"]} == {str(vault), str(other)}
    for item in items:
        receipt = service.source_logs(root, item["source"])
        assert receipt["ingestion_status"] == "ingested" and receipt["run_id"] == result["id"]
        assert receipt["path"] == item["origin"]
    assert "OTHER-PRIVATE-NOTE" not in json.dumps(calls)
    assert (_tree(vault), _tree(other)) == original
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "no_change"
    assert _dry(root)["pending_notes"] == 0


def test_only_changed_vault_is_sent_again(two_vaults):
    root, vault, other = two_vaults
    service.approve_sources(root)
    service.run_sync(root, source="obsidian", runner=_runner([]))
    (other / "Course/lecture.md").write_text("Changed second vault [[Alice Smith]]\n", encoding="utf-8")
    calls = []

    result = service.run_sync(root, source="obsidian", runner=_runner(calls))

    [item] = _items(calls)
    assert result["items"] == 1 and item["change_type"] == "modified"
    assert item["source"].split(":")[1] == _vault_sources(root)[other]["source_instance_id"]
    assert "Changed second vault" in item["text"]


def test_multi_vault_batches_keep_limits_and_drain_without_replaying(two_vaults):
    from connectonion.rem.config import set_config
    root, vault, other = two_vaults
    set_config(root, ["limits.items_per_batch", "1", "limits.extract_items_per_batch", "1"])
    service.approve_sources(root)
    calls = []

    result = service.run_sync(root, source="obsidian", all_pending=True, runner=_runner(calls))

    assert all(len(items) == 1 for kind, items in calls)
    assert len(_items(calls)) == len({item["source"] for item in _items(calls)}) == 4
    assert _dry(root)["pending_notes"] == 0
    assert result["collection"]["obsidian"]["appended_records"] == 4


def test_next_vault_note_that_will_not_fit_waits_for_a_fresh_batch(two_vaults):
    root, vault, other = two_vaults
    first_body, second_body = "First detail.\n" * 5000, "Other detail.\n" * 5000
    (vault / "Course/lecture.md").write_text(first_body, encoding="utf-8")
    (other / "Course/lecture.md").write_text(second_body, encoding="utf-8")
    service.approve_sources(root)
    calls = []

    first = service.run_sync(root, source="obsidian", runner=_runner(calls))
    second = service.run_sync(root, source="obsidian", runner=_runner(calls))

    assert first["outcome"] == second["outcome"] == "completed"
    assert first["items"] + second["items"] == 4
    assert len(_items(calls)) == len({item["source"] for item in _items(calls)}) == 4
    assert any(first_body in item["text"] for item in _items(calls))
    assert any(second_body in item["text"] for item in _items(calls))
    assert _dry(root)["pending_notes"] == 0


def test_failed_multi_vault_runner_keeps_both_progresses_for_retry(two_vaults):
    root, vault, other = two_vaults
    service.approve_sources(root)
    before = read_json(state_path(root, "progress.json"), {})
    attempts = []

    def fail(notebook, items, config, kind=""):
        attempts.extend(item["source"] for item in items)
        raise RuntimeError("model temporarily unavailable")
    failed = service.run_sync(root, source="obsidian", runner=fail)

    assert failed["outcome"] == "failed" and len(attempts) == 4
    assert read_json(state_path(root, "progress.json"), {}) == before
    calls = []
    result = service.run_sync(root, source="obsidian", runner=_runner(calls))
    assert result["outcome"] == "completed"
    assert sorted(item["source"] for item in _items(calls)) == sorted(attempts)
    assert result["collection"]["obsidian"]["appended_records"] == 0


def test_unavailable_second_vault_is_checked_before_any_collection(two_vaults, tmp_path, monkeypatch):
    root, vault, other = two_vaults
    service.approve_sources(root)
    moved = tmp_path / "moved"
    other.rename(moved)
    collect = export.sync_notes

    def no_collection(*args, **kwargs):
        pytest.fail("all selected vaults must be available before collection starts")
    with monkeypatch.context() as patch:
        patch.setattr(export, "sync_notes", no_collection)
        with pytest.raises(RemError, match="unavailable"):
            service.run_sync(root, source="obsidian", runner=_runner([]))
    assert not any(Path(s["root"]).exists() for s in _vault_sources(root).values())
    moved.rename(other)
    assert export.sync_notes is collect
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "completed"


@pytest.mark.parametrize("as_json", [False, True], ids=["human", "json"])
def test_unavailable_multi_vault_sync_points_back_to_scoped_sources(as_json, two_vaults, tmp_path):
    import shlex
    from connectonion.cli.main import app
    root, vault, other = two_vaults
    service.approve_sources(root)
    other.rename(tmp_path / "missing-vault")

    result = CliRunner().invoke(app, ["rem", "--root", str(root), *(["--json"] if as_json else []),
                                     "sync", "--source", "obsidian"])

    assert result.exit_code != 0 and "unavailable" in result.output
    if as_json:
        assert shlex.split(json.loads(result.stdout)["next"]) == ["co", "rem", "--root", str(root), "sources"]
    else:
        assert f"co rem --root {root} sources" in result.output


@pytest.mark.parametrize("remove_first", [False, True])
def test_removing_one_vault_keeps_other_history_and_readding_does_not_replay(remove_first, two_vaults):
    root, vault, other = two_vaults
    service.approve_sources(root)
    calls = []
    service.run_sync(root, source="obsidian", runner=_runner(calls))
    receipts = {item["source"]: service.source_logs(root, item["source"]) for item in _items(calls)}
    original = _tree(vault), _tree(other)
    selected, retained = (vault, other) if remove_first else (other, vault)
    before = _vault_sources(root)

    service.toggle_source(root, "obsidian", False, vault=str(selected))

    assert set(_vault_sources(root)) == {retained}
    assert _vault_sources(root)[retained]["source_instance_id"] == before[retained]["source_instance_id"]
    assert not _vault_sources(root)[retained]["consented"]
    service.approve_sources(root)
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "no_change"
    service.toggle_source(root, "obsidian", True, vault=str(selected), folders=["Course"])
    service.approve_sources(root)
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "no_change"
    assert all(service.source_logs(root, source) == receipt for source, receipt in receipts.items())
    assert (_tree(vault), _tree(other)) == original
    (selected / "Course/lecture.md").write_text("Updated after reregistering\n", encoding="utf-8")
    calls = []
    service.run_sync(root, source="obsidian", runner=_runner(calls))
    assert len(_items(calls)) == 1 and _items(calls)[0]["change_type"] == "modified"
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "no_change"


def test_remove_all_and_readd_in_reverse_order_preserves_both_receipts(two_vaults):
    root, vault, other = two_vaults
    service.approve_sources(root)
    calls = []
    service.run_sync(root, source="obsidian", runner=_runner(calls))
    receipts = {item["source"]: service.source_logs(root, item["source"]) for item in _items(calls)}
    service.toggle_source(root, "obsidian", False)

    for chosen in (other, vault):
        service.toggle_source(root, "obsidian", True, vault=str(chosen), folders=["Course"])
        service.approve_sources(root)
        assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "no_change"

    assert set(_vault_sources(root)) == {vault, other}
    assert all(service.source_logs(root, source) == receipt for source, receipt in receipts.items())


@pytest.mark.parametrize("remove_first", [False, True])
def test_last_folder_removal_unregisters_only_its_vault(remove_first, two_vaults):
    root, vault, other = two_vaults
    service.approve_sources(root)
    service.run_sync(root, source="obsidian", runner=_runner([]))
    selected, retained = (vault, other) if remove_first else (other, vault)

    service.toggle_source(root, "obsidian", False, vault=str(selected), folders=["Course"])

    assert set(_vault_sources(root)) == {retained}
    service.approve_sources(root)
    (retained / "Course/lecture.md").write_text("Only retained vault changes\n", encoding="utf-8")
    calls = []
    result = service.run_sync(root, source="obsidian", runner=_runner(calls))
    [item] = _items(calls)
    assert result["outcome"] == "completed"
    assert item["source"].split(":")[1] == _vault_sources(root)[retained]["source_instance_id"]


def test_removing_a_folder_from_one_vault_withdraws_only_its_support(two_vaults, monkeypatch):
    root, vault, other = two_vaults
    service.toggle_source(root, "obsidian", True, vault=str(other), folders=["Personal"])
    service.approve_sources(root)
    service.run_sync(root, source="obsidian", runner=_runner([]))
    service.toggle_source(root, "obsidian", False, vault=str(other), folders=["Personal"])
    service.approve_sources(root)
    read_markdown = obsidian._read_markdown

    def only_retained(scope, path):
        assert not path.is_relative_to(other / "Personal")
        return read_markdown(scope, path)
    monkeypatch.setattr(obsidian, "_read_markdown", only_retained)
    calls = []

    service.run_sync(root, source="obsidian", runner=_runner(calls))

    [item] = _items(calls)
    assert item["change_type"] == "deleted" and item["origin"] == "Personal/diary.md"
    assert "scope_removed" in item["text"] and "OTHER-PRIVATE-NOTE" not in item["text"]
    assert _vault_sources(root)[vault]["folders"] == ["Course"]
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "no_change"


def test_citations_resolve_the_correct_vault_and_obey_its_current_scope(two_vaults):
    from connectonion.rem.obsidian import cited_snapshot
    root, vault, other = two_vaults
    service.approve_sources(root)
    calls = []
    service.run_sync(root, source="obsidian", runner=_runner(calls))
    matching = [item for item in _items(calls) if item["origin"] == "Course/lecture.md"]
    assert len(matching) == 2
    for item in matching:
        assert item["text"] == cited_snapshot(root, item["source"])["excerpt"]
    removed = _vault_sources(root)[other]["source_instance_id"]
    service.toggle_source(root, "obsidian", False, vault=str(other))
    service.approve_sources(root)
    for item in matching:
        snapshot = cited_snapshot(root, item["source"])
        assert (snapshot is None) == (item["source"].split(":")[1] == removed)


def test_investigation_searches_each_vault_and_reports_coverage_separately(two_vaults):
    root, vault, other = two_vaults
    service.approve_sources(root)
    service.run_sync(root, source="obsidian", runner=_runner([]))
    before = _tree(vault), _tree(other), state_path(root, "progress.json").read_bytes()

    notes, coverage = _gather(root, "Alice Smith")

    assert len(notes) == 2 and {item["origin"] for item in notes} == {"Course/lecture.md"}
    assert len({item["source"].split(":")[1] for item in notes}) == 2
    assert len(coverage) == 2 and all("saved snapshots" in line for line in coverage)
    assert all(any(str(chosen) in line for line in coverage) for chosen in (vault, other))
    assert (_tree(vault), _tree(other), state_path(root, "progress.json").read_bytes()) == before


def test_multi_vault_sync_summary_reports_collected_notes(two_vaults):
    from connectonion.cli.commands.rem_output import sync_summary
    from rich.text import Text
    root, vault, other = two_vaults
    service.approve_sources(root)
    result = service.run_sync(root, source="obsidian", runner=_runner([]))

    shown = Text.from_markup(sync_summary(result)).plain

    assert "Not collected" not in shown and "4 changes" in shown and "2 vaults" in shown


def test_obsidian_only_sync_does_not_import_sessions_or_resume_mail(rem, monkeypatch):
    from connectonion.rem import sessions

    root, _ = rem

    def unrelated(*args, **kwargs):
        pytest.fail("An Obsidian-only sync must not read other sources")

    monkeypatch.setattr(sessions, "import_sessions", unrelated)
    monkeypatch.setattr(service, "refresh_init_mailboxes", unrelated)
    monkeypatch.setattr(service, "_resume_archive", unrelated)
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["items"] == 2


def test_obsidian_stage_route_change_waits_for_approval(rem):
    from connectonion.rem.inquiry import set_route

    root, _ = rem
    set_route(root, "maintain", "coai", "default")
    with pytest.raises(RemError, match="runner or model changed"):
        service.run_sync(root, source="obsidian", runner=_runner([]))
    assert _dry(root)["initialized"] is False

    service.grant_init_sources(root)
    with pytest.raises(RemError, match="runner or model changed"):
        service.run_sync(root, source="obsidian", runner=_runner([]))
    assert service.ensure_consent(root, confirm=lambda summary: summary["obsidian_model_scope"]["routes"]
                                  == {"maintain": {"runner": "coai", "model": "default"}})
    assert service.run_sync(root, source="obsidian", runner=_runner([]))["items"] == 2


def test_scope_changed_while_start_confirmation_is_open_waits_for_a_new_approval(rem):
    root, vault = rem
    service.toggle_source(root, "obsidian", True, vault=str(vault), folders=["Personal"])

    def confirm(summary):
        service.toggle_source(root, "obsidian", False, vault=str(vault), folders=["Course"])
        return True

    with pytest.raises(RemError, match="changed during approval"):
        service.ensure_consent(root, confirm=confirm)
    assert not _subscription(root)["consented"]
    assert _dry(root)["initialized"] is False


@pytest.mark.parametrize("remove_before_receipt", [False, True])
def test_native_batch_resumes_and_commits_only_approved_coverage(rem, tmp_path, remove_before_receipt):
    from connectonion.rem import native_round
    from connectonion.rem.config import read_config

    root, _ = rem
    config = read_config(root)
    progress = read_json(state_path(root, "progress.json"), {})
    batch = native_round._read_sources(root, {"obsidian": _subscription(root)}, progress, config, [])
    batch["progress_before"] = read_json(state_path(root, "progress.json"), {})
    cursor = {"phase": "daily-update", "batch": batch, "batch_index": 0}
    directory = tmp_path / "native-task"
    directory.mkdir()
    task = native_round.prepare_batch(root, cursor, config, directory)
    assert task["stage"] == "maintain"
    sources = task["task"]["obsidian_sources"]
    assert len(sources) == 2
    assert service.source_logs(root, sources[0])["ingestion_status"] == "not consumed yet"

    if remove_before_receipt:
        service.toggle_source(root, "obsidian", False)
    native_round._advance_batch(root, cursor, task, {"changed": []})
    assert native_round.prepare_batch(root, cursor, config, directory) is None
    record = batch["record"]
    assert record["outcome"] == ("discarded" if remove_before_receipt else "completed")
    for source_id in sources:
        trace = service.source_logs(root, source_id)
        if remove_before_receipt:
            assert trace["ingestion_status"] == "not consumed yet"
        else:
            assert trace["ingestion_status"] == "ingested"
            assert trace["run_id"] == record["id"]
    if not remove_before_receipt:
        assert service.run_sync(root, source="obsidian", runner=_runner([]))["outcome"] == "no_change"


def test_sync_one_vault_by_instance_also_works_for_the_first_registration(two_vaults):
    root, vault, _ = two_vaults
    service.approve_sources(root)
    instance = _subscription(root)["source_instance_id"]
    calls = []

    result = service.run_sync(root, source=f"obsidian-{instance}", runner=_runner(calls))

    assert result["collection"]["obsidian"]["vault"] == str(vault)
    assert len(_items(calls)) == 2
    assert all(item["source"].split(":")[1] == instance for item in _items(calls))
