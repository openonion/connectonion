"""Atomic single-vault collection using synthetic notes and local notebooks."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
import shutil
import sqlite3
import sys
from threading import Event

import pytest

from connectonion.rem import files, obsidian, obsidian_store as store
from connectonion.rem.files import RemError, read_json, state_path, write_json


@pytest.fixture
def configured(tmp_path):
    vault = tmp_path / "Vault"
    for folder in ("Work", "Private"):
        (vault / folder).mkdir(parents=True)
    (vault / "Work" / "Plan.md").write_text("# Plan\n[[Diagnosis]]\n", encoding="utf-8")
    (vault / "Work" / "Meeting.md").write_text("# Meeting\n", encoding="utf-8")
    (vault / "Private" / "Diagnosis.md").write_text("# Diagnosis\n[[Plan]]\n", encoding="utf-8")
    root = tmp_path / "notebook"
    obsidian.save_selection(root, vault, ["Work"])
    return root, vault.resolve()


def database(root):
    return state_path(root, store.DATABASE)


def snapshots(root):
    return {snapshot["note"]["path"]: snapshot for snapshot in store.latest_snapshots(root)}


def counts(root):
    with closing(sqlite3.connect(database(root))) as connection:
        return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("snapshots", "heads", "changes"))


def test_first_collection_and_repeat_are_idempotent(configured):
    root, _ = configured
    assert store.latest_snapshots(root) == []
    first = store.collect(root)
    assert first["added"] == 2
    assert first["cursor"] == 2
    saved = snapshots(root)
    assert set(saved) == {"Work/Plan.md", "Work/Meeting.md"}
    assert all(item["source_id"].startswith("obsidian:") for item in saved.values())
    repeated = store.collect(root)
    assert repeated["changes"] == []
    assert repeated["unchanged"] == 2
    assert repeated["cursor"] == first["cursor"]
    assert snapshots(root) == saved
    assert counts(root) == (2, 2, 2)


def test_content_change_keeps_exact_old_version_even_with_same_mtime(configured):
    root, vault = configured
    store.collect(root)
    original = snapshots(root)["Work/Plan.md"]
    note = vault / "Work" / "Plan.md"
    stamp = note.stat()
    note.write_text("# New plan\n", encoding="utf-8")
    os.utime(note, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    result = store.collect(root)
    assert result["modified"] == 1
    current = snapshots(root)["Work/Plan.md"]
    assert current["source_id"] != original["source_id"]
    assert current["note"]["content"] == "# New plan\n"
    assert store.read_snapshot(root, original["source_id"]) == original
    assert counts(root) == (3, 2, 3)


def test_touch_without_content_change_does_not_create_version(configured):
    root, vault = configured
    store.collect(root)
    note = vault / "Work" / "Plan.md"
    stamp = note.stat()
    os.utime(note, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000_000))
    assert store.collect(root)["changes"] == []
    assert counts(root) == (2, 2, 2)


def test_delete_and_recreate_retain_history(configured):
    root, vault = configured
    store.collect(root)
    original = snapshots(root)["Work/Plan.md"]
    note = vault / "Work" / "Plan.md"
    note.unlink()
    assert store.collect(root)["deleted"] == 1
    assert "Work/Plan.md" not in snapshots(root)
    assert store.read_snapshot(root, original["source_id"]) == original
    note.write_text(original["note"]["content"], encoding="utf-8")
    assert store.collect(root)["added"] == 1
    assert snapshots(root)["Work/Plan.md"]["source_id"] != original["source_id"]


def test_rename_is_delete_and_add(configured):
    root, vault = configured
    store.collect(root)
    (vault / "Work" / "Plan.md").rename(vault / "Work" / "Renamed.md")
    result = store.collect(root)
    assert result["deleted"] == 1
    assert result["added"] == 1
    assert result["modified"] == 0


def test_scope_narrowing_hides_old_paths_before_next_collection(configured):
    root, vault = configured
    obsidian.save_selection(root, vault, ["Work", "Private"])
    store.collect(root)
    saved = snapshots(root)
    private_id = saved["Private/Diagnosis.md"]["source_id"]
    plan_id = saved["Work/Plan.md"]["source_id"]
    obsidian.save_selection(root, vault, ["Work"])
    assert "Private/Diagnosis.md" not in str(store.latest_snapshots(root))
    plan = store.read_snapshot(root, plan_id)
    assert "Private/Diagnosis.md" not in str(plan)
    assert plan["note"]["backlinks"] == []
    with pytest.raises(RemError, match="unavailable"):
        store.read_snapshot(root, private_id)
    result = store.collect(root)
    assert result["scope_removed"] == 1
    assert result["deleted"] == 0
    assert store.collect(root)["changes"] == []


def test_vault_replacement_revokes_previous_citations(configured, tmp_path):
    root, _ = configured
    store.collect(root)
    old_id = snapshots(root)["Work/Plan.md"]["source_id"]
    other = tmp_path / "OtherVault"
    (other / "Work").mkdir(parents=True)
    (other / "Work" / "Plan.md").write_text("New vault\n", encoding="utf-8")
    obsidian.save_selection(root, other, ["Work"], replace=True)
    assert store.latest_snapshots(root) == []
    with pytest.raises(RemError, match="unavailable"):
        store.read_snapshot(root, old_id)
    result = store.collect(root)
    assert result["vault_replaced"] == 2
    assert result["added"] == 1
    assert result["modified"] == 0
    assert snapshots(root)["Work/Plan.md"]["source_id"] != old_id


def test_incomplete_scan_does_not_advance_progress(configured):
    root, vault = configured
    first = store.collect(root)
    before = snapshots(root)
    (vault / "Work" / "Plan.md").write_bytes(b"\xff\xfe")
    (vault / "Work" / "Meeting.md").unlink()
    with pytest.raises(obsidian.vault_reader.ObsidianError):
        store.collect(root)
    assert snapshots(root) == before
    assert counts(root) == (2, 2, 2)
    (vault / "Work" / "Plan.md").write_text("Recovered\n", encoding="utf-8")
    result = store.collect(root)
    assert result["modified"] == 1 and result["deleted"] == 1
    assert result["cursor"] == first["cursor"] + 2


def test_partial_transaction_rolls_back_and_retry_succeeds(configured, monkeypatch):
    root, vault = configured
    store.collect(root)
    before = snapshots(root)
    (vault / "Work" / "Plan.md").write_text("Changed\n", encoding="utf-8")
    (vault / "Work" / "Added.md").write_text("Added\n", encoding="utf-8")
    original = store._record_change

    def fail_after_write(*args):
        original(*args)
        raise OSError("Synthetic failure after SQL writes")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_record_change", fail_after_write)
        with pytest.raises(OSError, match="Synthetic"):
            store.collect(root)
    assert snapshots(root) == before
    assert counts(root) == (2, 2, 2)
    result = store.collect(root)
    assert result["added"] == 1 and result["modified"] == 1
    assert counts(root) == (4, 3, 4)


def test_failed_first_collection_can_be_retried(configured, monkeypatch):
    root, _ = configured

    def fail(*args):
        raise OSError("Synthetic first collection failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_record_change", fail)
        with pytest.raises(OSError):
            store.collect(root)
    assert store.latest_snapshots(root) == []
    assert store.collect(root)["added"] == 2
    assert counts(root) == (2, 2, 2)


def test_commit_failure_rolls_back_progress_and_versions(configured, monkeypatch):
    root, vault = configured
    first = store.collect(root)
    before = snapshots(root)
    (vault / "Work" / "Plan.md").write_text("Awaiting commit\n", encoding="utf-8")
    original = store._connect

    def deny_commit(action, argument, *unused):
        if action == sqlite3.SQLITE_TRANSACTION and argument == "COMMIT":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def connection_with_failed_commit(root, *, create):
        connection = original(root, create=create)
        if create:
            connection.set_authorizer(deny_commit)
        return connection

    with monkeypatch.context() as patch:
        patch.setattr(store, "_connect", connection_with_failed_commit)
        with pytest.raises(sqlite3.DatabaseError):
            store.collect(root)
    assert snapshots(root) == before
    assert counts(root) == (2, 2, 2)
    result = store.collect(root)
    assert result["modified"] == 1
    assert result["cursor"] == first["cursor"] + 1


def test_snapshot_connection_is_read_only(configured):
    root, _ = configured
    store.collect(root)
    with closing(store._connect(root, create=False)) as connection:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM heads")
    assert counts(root) == (2, 2, 2)


def test_notebook_path_with_uri_characters(configured):
    root, vault = configured
    named = root.with_name("Notebook #1 é")
    obsidian.save_selection(named, vault, ["Work"])
    assert store.collect(named)["added"] == 2
    assert database(named).is_file()
    assert len(store.latest_snapshots(named)) == 2


def test_empty_selected_folder_commits_an_empty_collection(configured):
    root, vault = configured
    (vault / "Empty").mkdir()
    obsidian.save_selection(root, vault, ["Empty"])
    result = store.collect(root)
    assert result["changes"] == []
    assert result["cursor"] == 0
    assert store.latest_snapshots(root) == []
    assert store.collect(root)["changes"] == []


def test_parallel_collections_do_not_duplicate_versions(configured, monkeypatch):
    root, _ = configured
    scanning, release, waiting = Event(), Event(), Event()
    list_notes, try_lock = obsidian.list_notes, files._try_lock
    monkeypatch.setattr(store, "WRITE_WAIT_SECONDS", 5)

    def held_scan(selection):
        scanning.set()
        assert release.wait(10), "The test must release the first scan"
        return list_notes(selection)

    def observe_lock(fd):
        try:
            return try_lock(fd)
        except BlockingIOError:
            waiting.set()
            raise

    monkeypatch.setattr(obsidian, "list_notes", held_scan)
    monkeypatch.setattr(files, "_try_lock", observe_lock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(store.collect, root)]
        try:
            assert scanning.wait(5), "The first collector must reach its scan"
            futures.append(pool.submit(store.collect, root))
            assert waiting.wait(5), "The second collector must contend for the writer lock"
            assert store.latest_snapshots(root) == []
        finally:
            release.set()
        results = [future.result(timeout=10) for future in futures]
    assert sorted(result["added"] for result in results) == [0, 2]
    assert counts(root) == (2, 2, 2)


def test_offline_vault_keeps_saved_versions_available(configured):
    root, vault = configured
    store.collect(root)
    before = snapshots(root)
    vault.rename(vault.with_name("OfflineVault"))
    assert snapshots(root) == before
    with pytest.raises(obsidian.vault_reader.ObsidianError):
        store.collect(root)
    assert snapshots(root) == before


def test_disabled_source_denies_collection_and_snapshots(configured):
    root, _ = configured
    store.collect(root)
    source_id = snapshots(root)["Work/Plan.md"]["source_id"]
    path = state_path(root, "subscriptions.json")
    saved = read_json(path, {})
    saved["obsidian"]["enabled"] = False
    write_json(path, saved)
    for operation in (lambda: store.collect(root), lambda: store.latest_snapshots(root),
                      lambda: store.read_snapshot(root, source_id)):
        with pytest.raises(RemError, match="disabled"):
            operation()


def test_notebook_inside_vault_is_rejected_before_collection(configured):
    _, vault = configured
    root = vault / "Notebook"
    obsidian.save_selection(root, vault, ["Work"])
    before = {path.relative_to(vault): path.read_bytes() for path in vault.rglob("*") if path.is_file()}
    with pytest.raises(RemError, match="outside"):
        store.collect(root)
    assert {path.relative_to(vault): path.read_bytes() for path in vault.rglob("*") if path.is_file()} == before


def test_collection_preserves_vault_and_private_material_is_absent(configured):
    root, vault = configured
    before = {path.relative_to(vault): path.read_bytes() for path in vault.rglob("*") if path.is_file()}
    store.collect(root)
    assert {path.relative_to(vault): path.read_bytes() for path in vault.rglob("*") if path.is_file()} == before
    assert "Private/Diagnosis.md" not in str(store.latest_snapshots(root))
    with closing(sqlite3.connect(database(root))) as connection:
        assert connection.execute("SELECT COUNT(*) FROM snapshots WHERE path LIKE 'Private/%'").fetchone()[0] == 0


def test_copied_store_cannot_be_used_in_another_notebook(configured, tmp_path):
    root, vault = configured
    store.collect(root)
    other = tmp_path / "other-notebook"
    obsidian.save_selection(other, vault, ["Work"])
    shutil.copyfile(database(root), database(other))
    with pytest.raises(RemError, match="another notebook"):
        store.collect(other)
    with pytest.raises(RemError, match="another notebook"):
        store.latest_snapshots(other)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require privileges on Windows")
@pytest.mark.parametrize("suffix", ["", "-journal", "-wal", "-shm"])
def test_linked_store_files_are_refused(configured, tmp_path, suffix):
    root, _ = configured
    target = tmp_path / "unrelated"
    target.write_text("Preserve me", encoding="utf-8")
    (database(root).parent / (store.DATABASE + suffix)).symlink_to(target)
    with pytest.raises(RemError, match="Symlinks"):
        store.collect(root)
    assert target.read_text(encoding="utf-8") == "Preserve me"


def test_unsupported_schema_is_preserved(configured):
    root, _ = configured
    store.collect(root)
    with closing(sqlite3.connect(database(root))) as connection:
        connection.execute("PRAGMA user_version = 999")
    before = database(root).read_bytes()
    with pytest.raises(RemError, match="Unsupported"):
        store.collect(root)
    assert database(root).read_bytes() == before


def test_saved_content_integrity_is_checked(configured):
    root, _ = configured
    store.collect(root)
    with closing(sqlite3.connect(database(root))) as connection, connection:
        connection.execute("UPDATE snapshots SET digest = 'invalid'")
    with pytest.raises(RemError, match="integrity"):
        store.latest_snapshots(root)
