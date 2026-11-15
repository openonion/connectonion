"""Single-vault configuration and live reads using synthetic local notebooks."""

from concurrent.futures import ThreadPoolExecutor
import sys

import pytest

from connectonion.rem import obsidian
from connectonion.rem.files import RemError, maintenance_lock, read_json, state_path, write_json
from connectonion.useful_tools import obsidian as vault_reader


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "Vault"
    for folder in ("Work", "Work/Meetings", "Study", "Private", ".obsidian", ".trash", ".git"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "Work" / "Plan.md").write_text("# Plan\n[[Diagnosis]] and [[Minutes]]\n", encoding="utf-8")
    (root / "Work" / "Meetings" / "Minutes.md").write_text("# Minutes\nProject plan.\n", encoding="utf-8")
    (root / "Study" / "Lecture.md").write_text("# Lecture\n", encoding="utf-8")
    (root / "Private" / "Diagnosis.md").write_text("Private fixture content.\n", encoding="utf-8")
    for folder in (".obsidian", ".trash", ".git"):
        (root / folder / "Hidden.md").write_text("Excluded fixture.\n", encoding="utf-8")
    return root.resolve()


@pytest.fixture
def notebook(tmp_path):
    return tmp_path / "notebook"


def sources(notebook):
    return read_json(state_path(notebook, "subscriptions.json"), {})


def mark_consented(notebook):
    """Simulate saved approval from a caller, without wiring the shared API."""
    saved = sources(notebook)
    saved["obsidian"]["consented"] = True
    write_json(state_path(notebook, "subscriptions.json"), saved)


def test_unregistered_selection_has_no_filesystem_side_effects(notebook):
    assert obsidian.load_selection(notebook) is None
    assert not notebook.exists()


def test_registration_normalizes_scope_and_preserves_other_sources(notebook, vault):
    other = {"gmail": {"kind": "gmail", "enabled": True, "consented": True}}
    write_json(state_path(notebook, "subscriptions.json"), other)
    selected = obsidian.save_selection(notebook, vault, ["Work/Meetings", "Study", "Work", "./Work"])
    assert selected == obsidian.Selection(vault, ("Study", "Work"))
    assert obsidian.load_selection(notebook) == selected
    saved = sources(notebook)
    assert saved["gmail"] == other["gmail"]
    assert saved["obsidian"] == {
        "id": "obsidian", "kind": "obsidian", "vault": str(vault),
        "folders": ["Study", "Work"], "enabled": True, "consented": False, "unsubscribed": False,
    }


def test_equivalent_selection_preserves_consent_and_subscription_bytes(notebook, vault):
    obsidian.save_selection(notebook, vault, ["Work", "Study"])
    mark_consented(notebook)
    path = state_path(notebook, "subscriptions.json")
    before = path.read_bytes()
    obsidian.save_selection(notebook, vault, ["Study", "Work/Meetings", "Work"])
    assert path.read_bytes() == before


def test_scope_change_and_restore_both_require_new_consent(notebook, vault):
    obsidian.save_selection(notebook, vault, ["Work"])
    mark_consented(notebook)
    obsidian.save_selection(notebook, vault, ["Study"])
    assert sources(notebook)["obsidian"]["consented"] is False
    obsidian.save_selection(notebook, vault, ["Work"])
    assert sources(notebook)["obsidian"]["consented"] is False


def test_reenabling_requires_new_consent(notebook, vault):
    obsidian.save_selection(notebook, vault, ["Work"])
    saved = sources(notebook)
    saved["obsidian"].update(enabled=False, unsubscribed=True, consented=True)
    write_json(state_path(notebook, "subscriptions.json"), saved)
    obsidian.save_selection(notebook, vault, ["Work"])
    assert sources(notebook)["obsidian"]["enabled"] is True
    assert sources(notebook)["obsidian"]["unsubscribed"] is False
    assert sources(notebook)["obsidian"]["consented"] is False


def test_vault_switch_requires_explicit_replacement(notebook, vault, tmp_path):
    obsidian.save_selection(notebook, vault, ["Work"])
    mark_consented(notebook)
    second = tmp_path / "OtherVault"
    (second / "Notes").mkdir(parents=True)
    before = sources(notebook)
    with pytest.raises(RemError, match="replace=True"):
        obsidian.save_selection(notebook, second, ["Notes"])
    assert sources(notebook) == before
    selected = obsidian.save_selection(notebook, second, ["Notes"], replace=True)
    assert selected.vault == second.resolve()
    assert sources(notebook)["obsidian"]["consented"] is False
    assert list(sources(notebook)) == ["obsidian"]


@pytest.mark.parametrize("folders", [[], "Work", ["../Private"], [".obsidian"], ["missing"]])
def test_invalid_scope_preserves_saved_configuration(notebook, vault, folders):
    obsidian.save_selection(notebook, vault, ["Work"])
    mark_consented(notebook)
    before = sources(notebook)
    with pytest.raises((ValueError, vault_reader.ObsidianError)):
        obsidian.save_selection(notebook, vault, folders)
    assert sources(notebook) == before


def test_configuration_inspection_works_when_vault_is_offline(notebook, vault):
    selected = obsidian.save_selection(notebook, vault, ["Work"])
    vault.rename(vault.with_name("Offline"))
    assert obsidian.load_selection(notebook) == selected
    with pytest.raises(vault_reader.ObsidianError):
        obsidian.list_notes(selected)


def test_configuring_and_loading_scope_do_not_read_note_contents(notebook, vault, monkeypatch):
    def fail(*args):
        raise AssertionError("Configuration must not read note contents")

    monkeypatch.setattr(vault_reader, "_read_markdown", fail)
    selected = obsidian.save_selection(notebook, vault, ["Work"])
    assert obsidian.load_selection(notebook) == selected


@pytest.mark.parametrize("value", [None, [], {"obsidian": None}, {"obsidian": {"kind": "gmail"}}])
def test_invalid_saved_data_is_reported_without_overwriting(notebook, vault, value):
    path = state_path(notebook, "subscriptions.json")
    write_json(path, value)
    before = path.read_bytes()
    with pytest.raises(RemError):
        obsidian.load_selection(notebook)
    with pytest.raises(RemError):
        obsidian.save_selection(notebook, vault, ["Work"])
    assert path.read_bytes() == before


@pytest.mark.parametrize("update", [
    {"vault": "relative"}, {"folders": []}, {"folders": "Work"},
    {"folders": ["../Private"]}, {"folders": [None]}, {"consented": "true"},
])
def test_invalid_subscription_fields_are_rejected(notebook, vault, update):
    obsidian.save_selection(notebook, vault, ["Work"])
    saved = sources(notebook)
    saved["obsidian"].update(update)
    write_json(state_path(notebook, "subscriptions.json"), saved)
    with pytest.raises(RemError):
        obsidian.load_selection(notebook)


def test_legacy_named_vaults_require_explicit_migration(notebook, vault):
    obsidian.save_selection(notebook, vault, ["Work"])
    saved = sources(notebook)
    saved["obsidian-second"] = dict(saved["obsidian"])
    write_json(state_path(notebook, "subscriptions.json"), saved)
    with pytest.raises(RemError, match="migrate to one vault"):
        obsidian.save_selection(notebook, vault, ["Study"])
    assert sources(notebook) == saved


def test_legacy_exclusions_cannot_be_silently_dropped(notebook, vault):
    obsidian.save_selection(notebook, vault, ["Work"])
    saved = sources(notebook)
    saved["obsidian"]["excluded_paths"] = ["Work/Meetings"]
    write_json(state_path(notebook, "subscriptions.json"), saved)
    with pytest.raises(RemError, match="saved exclusions"):
        obsidian.load_selection(notebook)
    with pytest.raises(RemError, match="saved exclusions"):
        obsidian.save_selection(notebook, vault, ["Study"])
    assert sources(notebook) == saved


def test_failed_save_preserves_previous_selection(notebook, vault, monkeypatch):
    obsidian.save_selection(notebook, vault, ["Work"])
    before = sources(notebook)

    def fail(path, value):
        raise OSError("Synthetic write failure")

    monkeypatch.setattr(obsidian, "write_json", fail)
    with pytest.raises(OSError, match="Synthetic"):
        obsidian.save_selection(notebook, vault, ["Study"])
    assert sources(notebook) == before


def test_parallel_source_changes_preserve_both_updates(notebook, vault):
    def save_mail():
        with maintenance_lock(notebook, wait=5):
            saved = sources(notebook)
            saved["gmail"] = {"kind": "gmail", "enabled": False}
            write_json(state_path(notebook, "subscriptions.json"), saved)

    with ThreadPoolExecutor(max_workers=2) as pool:
        selection = pool.submit(obsidian.save_selection, notebook, vault, ["Work"])
        mail = pool.submit(save_mail)
        selection.result(timeout=10)
        mail.result(timeout=10)
    assert sources(notebook)["gmail"]["enabled"] is False
    assert sources(notebook)["obsidian"]["folders"] == ["Work"]


def test_scoped_reads_keep_private_paths_out_of_links(vault):
    selected = obsidian.validate_selection(vault, ["Work"])
    notes = obsidian.list_notes(selected)
    assert {note["path"] for note in notes} == {"Work/Plan.md", "Work/Meetings/Minutes.md"}
    note = obsidian.read_note(selected, "Plan")
    assert note == obsidian.read_note(selected, "Work/Plan.md")
    private = next(link for link in note["links"] if link["target"] == "Diagnosis")
    assert private.get("resolved_path") is None
    assert private["resolution"] in ("unresolved", "out_of_scope")
    assert "Private/Diagnosis.md" not in str(notes)


def test_unselected_unreadable_folder_is_never_walked(vault, monkeypatch):
    original = vault_reader._walk_files
    visited = []

    def guarded(path, descriptor=None):
        visited.append(path)
        if not path.is_relative_to(vault / "Work"):
            raise PermissionError("Unselected folder is inaccessible")
        yield from original(path, descriptor)

    monkeypatch.setattr(vault_reader, "_walk_files", guarded)
    selected = obsidian.validate_selection(vault, ["Work"])
    assert len(obsidian.list_notes(selected)) == 2
    assert visited
    assert all(path.is_relative_to(vault / "Work") for path in visited)


@pytest.mark.parametrize("reference", ["Private/Diagnosis.md", "../Private/Diagnosis.md", "Diagnosis"])
def test_read_refuses_notes_outside_selection(vault, reference):
    selected = obsidian.validate_selection(vault, ["Work"])
    with pytest.raises((ValueError, vault_reader.ObsidianError)):
        obsidian.read_note(selected, reference)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require privileges on Windows")
def test_selection_is_revalidated_after_folder_becomes_a_symlink(vault):
    selected = obsidian.validate_selection(vault, ["Work"])
    (vault / "Work").rename(vault / "OriginalWork")
    (vault / "Work").symlink_to(vault / "Private", target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        obsidian.list_notes(selected)
    with pytest.raises(ValueError, match="symlinks"):
        obsidian.read_note(selected, "Diagnosis")


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require privileges on Windows")
def test_symlinked_notes_are_skipped_and_explicit_reads_rejected(vault):
    (vault / "Work" / "Linked.md").symlink_to(vault / "Private" / "Diagnosis.md")
    selected = obsidian.validate_selection(vault, ["Work"])
    assert "Work/Linked.md" not in {note["path"] for note in obsidian.list_notes(selected)}
    with pytest.raises(ValueError, match="symlinks"):
        obsidian.read_note(selected, "Work/Linked.md")


def test_whole_vault_is_explicit_and_system_folders_stay_excluded(vault):
    selected = obsidian.validate_selection(vault, ["."])
    assert selected.folders == (".",)
    assert {note["path"] for note in obsidian.list_notes(selected)} == {
        "Work/Plan.md", "Work/Meetings/Minutes.md", "Study/Lecture.md", "Private/Diagnosis.md",
    }


def test_live_reads_preserve_all_vault_files(vault):
    before = {path.relative_to(vault): path.read_bytes() for path in vault.rglob("*") if path.is_file()}
    selected = obsidian.validate_selection(vault, ["Work"])
    obsidian.list_notes(selected)
    obsidian.read_note(selected, "Plan")
    after = {path.relative_to(vault): path.read_bytes() for path in vault.rglob("*") if path.is_file()}
    assert after == before


@pytest.mark.parametrize("error", [KeyError("schema"), TypeError("schema")])
def test_programming_errors_propagate(vault, monkeypatch, error):
    def fail(*args):
        raise error

    monkeypatch.setattr(vault_reader, "_parse_markdown", fail)
    selected = obsidian.validate_selection(vault, ["Work"])
    with pytest.raises(type(error), match="schema"):
        obsidian.list_notes(selected)


# -- future source-version hook adapters ---------------------------------

VALID_SOURCE = f"obsidian:{'a' * 32}:{'b' * 32}:{'c' * 32}"


@pytest.mark.parametrize("source_id", [
    "", None, 42, "gmail:abc", VALID_SOURCE + "\n", VALID_SOURCE + ":extra",
    VALID_SOURCE[:-1], VALID_SOURCE.replace("c" * 32, "z" * 32),
    VALID_SOURCE.replace("obsidian:", "asana:"),
])
def test_invalid_version_ids_do_not_access_snapshots(notebook, monkeypatch, source_id):
    from connectonion.rem import obsidian_store

    def fail(*args):
        raise AssertionError("Invalid IDs must not access saved material")

    monkeypatch.setattr(obsidian_store, "read_snapshot", fail)
    assert obsidian.record_of(source_id) is None
    assert obsidian.cited(notebook, source_id) is None
    assert not notebook.exists()


def test_record_identity_is_pure_and_does_not_imply_version_order():
    other_version = VALID_SOURCE.rsplit(":", 1)[0] + ":" + "d" * 32
    assert obsidian.record_of(VALID_SOURCE) == "obsidian:" + "a" * 32 + ":" + "b" * 32
    assert obsidian.record_of(VALID_SOURCE) == obsidian.record_of(other_version)
    assert obsidian.record_of(VALID_SOURCE) != obsidian.record_of(VALID_SOURCE.replace("a" * 32, "e" * 32))
    assert obsidian.record_of(VALID_SOURCE) != obsidian.record_of(VALID_SOURCE.replace("b" * 32, "e" * 32))


def test_cited_resolves_the_exact_version_in_reader_format(notebook, vault):
    from connectonion.rem import obsidian_store

    obsidian.save_selection(notebook, vault, ["Work"])
    obsidian_store.collect(notebook)
    first = next(item for item in obsidian_store.latest_snapshots(notebook)
                 if item["note"]["path"] == "Work/Plan.md")
    (vault / "Work" / "Plan.md").write_text("Changed plan\n", encoding="utf-8")
    obsidian_store.collect(notebook)
    second = next(item for item in obsidian_store.latest_snapshots(notebook)
                  if item["note"]["path"] == "Work/Plan.md")
    assert first["source_id"] != second["source_id"]
    assert obsidian.record_of(first["source_id"]) == obsidian.record_of(second["source_id"])
    assert obsidian.cited(notebook, first["source_id"]) == {
        "excerpt": first["note"]["content"], "truncated": False, "time": first["note"]["modified_at"],
        "sender": "", "thread": "", "source": "obsidian", "subject": "Work/Plan.md",
        "captured_at": first["collected_at"],
        "input_scope": "One saved Obsidian note version within the currently selected folders. "
                       "Collection time is not the date of its claims.",
    }
    assert obsidian.cited(notebook, second["source_id"])["excerpt"] == "Changed plan\n"


def test_record_identity_separates_notebooks_for_the_same_note(notebook, vault, tmp_path):
    from connectonion.rem import obsidian_store

    other = tmp_path / "another-notebook"
    identities = []
    for root in (notebook, other):
        obsidian.save_selection(root, vault, ["Work"])
        obsidian_store.collect(root)
        snapshot = next(item for item in obsidian_store.latest_snapshots(root)
                        if item["note"]["path"] == "Work/Plan.md")
        identities.append(obsidian.record_of(snapshot["source_id"]))
    assert identities[0] != identities[1]


def test_cited_works_offline_and_never_reads_live_notes(notebook, vault, monkeypatch):
    from connectonion.rem import obsidian_store

    obsidian.save_selection(notebook, vault, ["Work"])
    obsidian_store.collect(notebook)
    saved = obsidian_store.latest_snapshots(notebook)[0]
    vault.rename(vault.with_name("Offline"))

    def fail(*args, **kwargs):
        raise AssertionError("Citation lookup must use the snapshot")

    monkeypatch.setattr(vault_reader, "list_notes", fail)
    monkeypatch.setattr(vault_reader, "read_note", fail)
    assert obsidian.cited(notebook, saved["source_id"])["excerpt"] == saved["note"]["content"]


def test_missing_subscription_store_and_version_return_none(notebook, vault):
    from connectonion.rem import obsidian_store

    assert obsidian.cited(notebook, VALID_SOURCE) is None
    assert not notebook.exists()
    obsidian.save_selection(notebook, vault, ["Work"])
    assert obsidian.cited(notebook, VALID_SOURCE) is None
    obsidian_store.collect(notebook)
    assert obsidian.cited(notebook, VALID_SOURCE) is None


@pytest.mark.parametrize("change", ["disable", "unsubscribe", "narrow", "replace"])
def test_cited_returns_none_when_current_selection_revokes_access(notebook, vault, tmp_path, change):
    from connectonion.rem import obsidian_store

    obsidian.save_selection(notebook, vault, ["Work"])
    obsidian_store.collect(notebook)
    saved = next(item for item in obsidian_store.latest_snapshots(notebook)
                 if item["note"]["path"] == "Work/Plan.md")
    if change == "narrow":
        obsidian.save_selection(notebook, vault, ["Work/Meetings"])
    elif change == "replace":
        other = tmp_path / "other-vault"
        other.mkdir()
        obsidian.save_selection(notebook, other, ["."], replace=True)
    else:
        subscriptions = sources(notebook)
        subscriptions["obsidian"]["enabled" if change == "disable" else "unsubscribed"] = change != "disable"
        write_json(state_path(notebook, "subscriptions.json"), subscriptions)
    assert obsidian.cited(notebook, saved["source_id"]) is None


@pytest.mark.parametrize("label", ["[personal]", "[SENSITIVE]", "［personal］"])
def test_private_labelled_notes_are_omitted_from_citation_context(notebook, vault, label):
    from connectonion.rem import obsidian_store

    (vault / "Work" / "Plan.md").write_text(f"# Plan\n{label} Private fixture\n", encoding="utf-8")
    obsidian.save_selection(notebook, vault, ["Work"])
    obsidian_store.collect(notebook)
    saved = next(item for item in obsidian_store.latest_snapshots(notebook)
                 if item["note"]["path"] == "Work/Plan.md")
    assert obsidian.cited(notebook, saved["source_id"]) is None


def test_private_label_in_filename_is_omitted(notebook, vault):
    from connectonion.rem import obsidian_store

    (vault / "Work" / "Plan.md").rename(vault / "Work" / "[personal] Plan.md")
    obsidian.save_selection(notebook, vault, ["Work"])
    obsidian_store.collect(notebook)
    saved = next(item for item in obsidian_store.latest_snapshots(notebook)
                 if "[personal]" in item["note"]["path"])
    assert obsidian.cited(notebook, saved["source_id"]) is None


@pytest.mark.parametrize("content", ["", " \n你好\n\n", "Long note\n" * 2000])
def test_cited_preserves_saved_content_for_the_callers_budget(notebook, vault, content):
    from connectonion.rem import obsidian_store

    (vault / "Work" / "Plan.md").write_text(content, encoding="utf-8")
    obsidian.save_selection(notebook, vault, ["Work"])
    obsidian_store.collect(notebook)
    saved = next(item for item in obsidian_store.latest_snapshots(notebook)
                 if item["note"]["path"] == "Work/Plan.md")
    context = obsidian.cited(notebook, saved["source_id"])
    assert context["excerpt"] == content
    assert context["truncated"] is False


@pytest.mark.parametrize("error", [RemError("Corrupt store"), OSError("Disk error"),
                                 KeyError("schema"), TypeError("schema")])
def test_cited_does_not_hide_storage_or_programming_errors(notebook, monkeypatch, error):
    from connectonion.rem import obsidian_store

    def fail(*args):
        raise error

    monkeypatch.setattr(obsidian_store, "read_snapshot", fail)
    with pytest.raises(type(error)):
        obsidian.cited(notebook, VALID_SOURCE)


def test_cited_reports_actual_snapshot_corruption(notebook, vault):
    from contextlib import closing
    import sqlite3
    from connectonion.rem import obsidian_store

    obsidian.save_selection(notebook, vault, ["Work"])
    obsidian_store.collect(notebook)
    source_id = obsidian_store.latest_snapshots(notebook)[0]["source_id"]
    with closing(sqlite3.connect(state_path(notebook, obsidian_store.DATABASE))) as connection, connection:
        connection.execute("UPDATE snapshots SET digest = 'invalid' WHERE source_id = ?", (source_id,))
    with pytest.raises(RemError, match="integrity"):
        obsidian.cited(notebook, source_id)
