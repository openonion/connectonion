"""Local provider contract over real synthetic vaults and saved snapshots."""

from copy import deepcopy
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from connectonion.rem import obsidian, obsidian_source as adapter, obsidian_store as store
from connectonion.rem.files import RemError, read_json, state_path, write_json


def saved(root):
    return read_json(state_path(root, "subscriptions.json"), {})["obsidian"]


def approve(root):
    from connectonion.rem.service import approve_sources
    approve_sources(root)
    return saved(root)


@pytest.fixture
def configured(tmp_path):
    vault = tmp_path / "Vault"
    (vault / "Work").mkdir(parents=True)
    (vault / "Private").mkdir()
    (vault / "Work" / "A.md").write_text("Atlas project first note", encoding="utf-8")
    (vault / "Work" / "B.md").write_text("Atlas project second note", encoding="utf-8")
    (vault / "Private" / "Diagnosis.md").write_text("Atlas private sibling", encoding="utf-8")
    root = tmp_path / "notebook"
    obsidian.save_selection(root, vault, ["Work"])
    return root.resolve(), vault.resolve(), approve(root)


def test_metadata_describes_only_the_given_selection_without_storage_access(configured, monkeypatch):
    root, vault, sub = configured
    sub = {**sub, "consented": False}
    def forbidden(*args, **kwargs):
        pytest.fail("Metadata accessed source storage")
    monkeypatch.setattr(obsidian, "_subscriptions", forbidden)
    monkeypatch.setattr(obsidian.vault_reader, "list_notes", forbidden)
    monkeypatch.setattr(store, "_connect", forbidden)
    info = adapter.status(sub)
    assert info["vault"] == str(vault) and info["folders"] == ["Work"]
    assert info["consented"] is False
    assert "Work" in adapter.consent(sub)
    assert not (root / ".state" / store.DATABASE).exists()


@pytest.mark.parametrize("field,value", [("consented", False), ("enabled", False), ("unsubscribed", True)])
def test_content_hooks_refuse_current_revocation_even_with_old_argument(configured, field, value):
    root, _, sub = configured
    adapter.fetch(root, sub)
    version = store.latest_snapshots(root)[0]["source_id"]
    sources = read_json(state_path(root, "subscriptions.json"), {})
    sources["obsidian"][field] = value
    write_json(state_path(root, "subscriptions.json"), sources)
    from connectonion.rem.source_hooks import SourceUnavailable
    with pytest.raises(SourceUnavailable):
        adapter.fetch(root, sub)
    with pytest.raises(store.SnapshotUnavailable):
        adapter.collect(root, sub, {}, 10, 10_000)
    with pytest.raises(store.SnapshotUnavailable):
        adapter.gather(root, sub, ["Atlas"], start=datetime(2000, 1, 1, tzinfo=timezone.utc), record="projects/atlas.md")
    assert adapter.cited(root, sub, version) is None


def test_scope_change_rejects_stale_subscription_after_reapproval(configured):
    root, vault, sub = configured
    adapter.fetch(root, sub)
    version = store.latest_snapshots(root)[0]["source_id"]
    obsidian.save_selection(root, vault, ["Private"])
    approve(root)
    with pytest.raises(store.SnapshotUnavailable):
        adapter.collect(root, sub, {}, 10, 10_000)
    assert adapter.cited(root, sub, version) is None


def test_fetch_only_scans_selected_folders_and_repeat_is_unchanged(configured):
    root, vault, sub = configured
    before = {str(path): path.read_bytes() for path in vault.rglob("*.md")}
    assert adapter.fetch(root, sub)["added"] == 2
    assert adapter.fetch(root, sub)["changes"] == []
    assert {str(path): path.read_bytes() for path in vault.rglob("*.md")} == before
    assert {s["note"]["path"] for s in store.latest_snapshots(root)} == {"Work/A.md", "Work/B.md"}


def test_offline_batches_are_bounded_repeatable_and_do_not_save_progress(configured, monkeypatch):
    root, vault, sub = configured
    adapter.fetch(root, sub)
    vault.rename(vault.with_name("Offline"))
    def forbidden(*args, **kwargs):
        pytest.fail("Offline consumption rescanned a vault")
    monkeypatch.setattr(obsidian, "list_notes", forbidden)
    original_resolve = Path.resolve
    def resolve(path, *args, **kwargs):
        if path == vault or path.is_relative_to(vault):
            pytest.fail("Offline consumption resolved a live vault path")
        return original_resolve(path, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", resolve)
    checkpoint = {}
    first = adapter.collect(root, sub, checkpoint, 1, 10_000)
    assert len(first.items) == 1 and checkpoint == {}
    assert first == adapter.collect(root, sub, checkpoint, 1, 10_000)
    second = adapter.collect(root, sub, first.progress, 1, 10_000)
    assert len(second.items) == 1
    assert first.items[0]["source"] != second.items[0]["source"]
    assert adapter.collect(root, sub, second.progress, 1, 10_000).items == []
    assert not (root / ".state" / "obsidian-progress.json").exists()


def test_skipped_history_does_not_report_empty_before_a_current_version(configured):
    root, vault, sub = configured
    adapter.fetch(root, sub)
    old = store.latest_snapshots(root)[0]["source_id"]
    (vault / "Work" / "A.md").write_text("Atlas latest version", encoding="utf-8")
    adapter.fetch(root, sub)
    current = {s["note"]["path"]: s["source_id"] for s in store.latest_snapshots(root)}
    # More history than the former 1000-event cap, without 1001 filesystem scans.
    with closing(sqlite3.connect(state_path(root, store.DATABASE))) as db, db:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("DELETE FROM changes")
        for index in range(1001):
            source_id = old.rsplit(":", 1)[0] + f":{index:032x}"
            db.execute("INSERT INTO snapshots SELECT ?, vault, path, digest, note, collected_at "
                       "FROM snapshots WHERE source_id = ?", (source_id, old))
            db.execute("INSERT INTO changes(kind, source_id, observed_at) VALUES ('modified', ?, ?)",
                       (source_id, "2026-11-01T00:00:00Z"))
        for path in ("Work/B.md", "Work/A.md"):
            db.execute("INSERT INTO changes(kind, source_id, observed_at) VALUES ('modified', ?, ?)",
                       (current[path], "2026-11-02T00:00:00Z"))
    first = adapter.collect(root, sub, {}, 1, 10_000)
    second = adapter.collect(root, sub, first.progress, 1, 10_000)
    assert [item["subject"] for item in first.items + second.items] == ["Work/B.md", "Work/A.md"]
    assert adapter.collect(root, sub, second.progress, 1, 10_000).items == []


def test_scope_is_rechecked_after_waiting_for_storage_lock(configured, monkeypatch):
    from contextlib import contextmanager
    from connectonion.rem.source_hooks import SourceUnavailable

    root, _, sub = configured
    real_lock = store._file_lock
    @contextmanager
    def revoke_then_lock(path, wait, **kwargs):
        sources = read_json(state_path(root, "subscriptions.json"), {})
        sources["obsidian"]["consented"] = False
        write_json(state_path(root, "subscriptions.json"), sources)
        with real_lock(path, wait, **kwargs):
            yield
    monkeypatch.setattr(store, "_file_lock", revoke_then_lock)
    with pytest.raises(SourceUnavailable):
        adapter.fetch(root, sub)
    assert not state_path(root, store.DATABASE).exists()


def test_small_character_budget_never_loses_the_next_note(configured):
    root, _, sub = configured
    adapter.fetch(root, sub)
    full = adapter.collect(root, sub, {}, 10, 100_000)
    limit = max(len(json.dumps(item, ensure_ascii=False)) for item in full.items)
    first = adapter.collect(root, sub, {}, 10, limit)
    second = adapter.collect(root, sub, first.progress, 10, limit)
    assert len(first.items) == len(second.items) == 1
    assert sum(len(json.dumps(item, ensure_ascii=False)) for item in first.items) <= limit
    assert {item["source"] for item in first.items + second.items} == {item["source"] for item in full.items}


def test_large_note_is_explicitly_truncated_and_tiny_budget_does_not_advance(configured):
    root, vault, sub = configured
    (vault / "Work" / "A.md").write_text("Atlas " * 10_000, encoding="utf-8")
    adapter.fetch(root, sub)
    batch = adapter.collect(root, sub, {}, 1, 2000)
    assert len(json.dumps(batch.items[0], ensure_ascii=False)) <= 2000
    assert "truncated by co rem" in batch.items[0]["text"]
    progress = deepcopy(batch.progress)
    with pytest.raises(RemError, match="limit"):
        adapter.collect(root, sub, progress, 1, 1)
    assert progress == batch.progress


def test_updates_and_deletions_before_consumption_do_not_replay_stale_bodies(configured):
    root, vault, sub = configured
    adapter.fetch(root, sub)
    old = store.latest_snapshots(root)[0]["source_id"]
    (vault / "Work" / "A.md").write_text("Atlas updated words", encoding="utf-8")
    (vault / "Work" / "B.md").unlink()
    result = adapter.fetch(root, sub)
    batch = adapter.collect(root, sub, {}, 10, 10_000)
    assert len(batch.items) == 1
    assert batch.items[0]["text"] == "Atlas updated words"
    assert batch.progress["sequence"] == result["cursor"]
    assert adapter.cited(root, sub, old)["excerpt"] == "Atlas project first note"


def test_incremental_batch_and_gather_do_not_imply_capture_time_is_claim_time(configured):
    root, vault, sub = configured
    adapter.fetch(root, sub)
    initial = adapter.collect(root, sub, {}, 10, 10_000)
    (vault / "Work" / "A.md").write_text("Atlas changed", encoding="utf-8")
    adapter.fetch(root, sub)
    batch = adapter.collect(root, sub, initial.progress, 10, 10_000)
    assert len(batch.items) == 1
    snapshot = store.read_snapshot(root, batch.items[0]["source"])
    assert batch.items[0]["timestamp"] == snapshot["note"]["modified_at"]
    assert batch.items[0]["captured_at"] == snapshot["collected_at"]
    assert "not the date" in batch.items[0]["input_scope"]


@pytest.mark.parametrize("label", ["[personal]", "[SENSITIVE]", "［personal］"])
def test_private_notes_do_not_reach_batches_or_investigation(configured, label):
    root, vault, sub = configured
    (vault / "Work" / "A.md").write_text("Atlas " + "x" * 4000 + label, encoding="utf-8")
    adapter.fetch(root, sub)
    batch = adapter.collect(root, sub, {}, 10, 2000)
    assert [item["subject"] for item in batch.items] == ["Work/B.md"]
    items, _ = adapter.gather(root, sub, ["Atlas"], start=datetime(2000, 1, 1, tzinfo=timezone.utc), record="projects/atlas.md")
    assert [item["subject"] for item in items] == ["Work/B.md"]


def test_investigation_reads_saved_matches_only_and_has_explicit_limits(configured, monkeypatch):
    root, vault, sub = configured
    adapter.fetch(root, sub)
    (vault / "Work" / "A.md").write_text("Uncollected live change", encoding="utf-8")
    vault.rename(vault.with_name("Offline"))
    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(adapter, "GATHER_MAX_ITEMS", 1)
    items, coverage = adapter.gather(root, sub, ["ATLAS"], start=start, record="projects/atlas.md")
    assert len(items) == 1 and "Atlas project" in items[0]["text"]
    assert "limited" in " ".join(coverage)
    assert "Private" not in str((items, coverage))
    assert adapter.gather(root, sub, ["Uncollected"], start=start, record="projects/atlas.md")[0] == []
    assert adapter.gather(root, sub, ["Atlas"], start=datetime(2100, 1, 1, tzinfo=timezone.utc), record="projects/atlas.md")[0] == []


def test_expanded_scope_resets_consumption_without_exposing_revoked_scope(configured):
    root, vault, sub = configured
    adapter.fetch(root, sub)
    progress = adapter.collect(root, sub, {}, 10, 10_000).progress
    obsidian.save_selection(root, vault, ["Work", "Private"])
    sub = approve(root)
    adapter.fetch(root, sub)
    expanded = adapter.collect(root, sub, progress, 10, 10_000)
    assert len(expanded.items) == 3
    assert expanded.progress["scope"] != progress["scope"]
    obsidian.save_selection(root, vault, ["Work"])
    sub = approve(root)
    narrowed = adapter.collect(root, sub, expanded.progress, 10, 10_000)
    assert "Private" not in str(narrowed.items)


def test_absent_store_is_not_reported_as_successful_empty_collection(configured):
    root, _, sub = configured
    with pytest.raises(store.SnapshotUnavailable, match="snapshot"):
        adapter.collect(root, sub, {}, 10, 10_000)


def test_corrupt_or_future_checkpoint_is_not_silently_reset(configured):
    root, _, sub = configured
    adapter.fetch(root, sub)
    batch = adapter.collect(root, sub, {}, 10, 10_000)
    for sequence in (-1, True, "1", 10000):
        with pytest.raises(RemError, match="progress|checkpoint"):
            adapter.collect(root, sub, {**batch.progress, "sequence": sequence}, 10, 10_000)


@pytest.mark.parametrize("error", [KeyError("schema"), TypeError("schema"), RemError("corrupt store")])
def test_programming_and_corruption_errors_propagate(configured, monkeypatch, error):
    root, _, sub = configured
    adapter.fetch(root, sub)
    def broken(*args, **kwargs):
        raise error
    monkeypatch.setattr(store, "_decode", broken)
    with pytest.raises(type(error)):
        adapter.collect(root, sub, {}, 10, 10_000)


def test_stream_closes_its_lock_when_batch_stops_early(configured):
    root, _, sub = configured
    adapter.fetch(root, sub)
    adapter.collect(root, sub, {}, 1, 10_000)
    # A leaked generator/lock would prevent another acquisition.
    assert adapter.fetch(root, sub)["unchanged"] == 2


@pytest.mark.parametrize("option,value", [("max_items", 0), ("max_items", -1),
                                        ("max_items", True), ("max_chars", 0),
                                        ("max_chars", -1), ("max_chars", True)])
def test_gather_rejects_invalid_budgets_before_reading(configured, monkeypatch, option, value):
    root, _, sub = configured
    monkeypatch.setattr(store, "iter_latest", lambda *a, **kw: pytest.fail("invalid budget read storage"))
    with pytest.raises(ValueError, match="limits"):
        adapter.gather(root, sub, ["Atlas"], start=datetime(2000, 1, 1, tzinfo=timezone.utc),
                       record="projects/atlas.md", **{option: value})


def test_gather_owner_only_does_not_read_unattributed_notes(configured, monkeypatch):
    root, _, sub = configured
    monkeypatch.setattr(store, "iter_latest", lambda *a, **kw: pytest.fail("owner gather read storage"))
    items, coverage = adapter.gather(root, sub, ["Atlas"], start=datetime(2000, 1, 1, tzinfo=timezone.utc),
                                     record="people/owner.md", owner=True)
    assert items == [] and "owner authorship" in " ".join(coverage)


@pytest.mark.parametrize("end", [datetime(2025, 1, 1), datetime(1999, 1, 1, tzinfo=timezone.utc),
                                 datetime(2000, 1, 1, tzinfo=timezone.utc)])
def test_gather_rejects_invalid_end_before_reading(configured, monkeypatch, end):
    root, _, sub = configured
    monkeypatch.setattr(store, "iter_latest", lambda *a, **kw: pytest.fail("invalid window read storage"))
    with pytest.raises(ValueError, match="end"):
        adapter.gather(root, sub, ["Atlas"], start=datetime(2000, 1, 1, tzinfo=timezone.utc),
                       end=end, record="projects/atlas.md")


@pytest.mark.parametrize("error", [ValueError("parser bug"), TypeError("reader bug")])
def test_unexpected_reader_errors_are_not_translated_to_availability(configured, monkeypatch, error):
    root, _, sub = configured
    def broken(scope):
        raise error
    monkeypatch.setattr(obsidian.vault_reader, "_load_scope_notes", broken)
    with pytest.raises(type(error), match=str(error)):
        adapter.fetch(root, sub)


@pytest.mark.parametrize("sql,parameters,error_type", [
    ("SELECT ?", (), sqlite3.ProgrammingError),
    ("SELEC 1", (), sqlite3.OperationalError),
    ("SELECT * FROM table_that_does_not_exist", (), sqlite3.OperationalError),
])
def test_sql_programming_failures_propagate_through_shared_fetch(configured, monkeypatch, sql, parameters, error_type):
    from connectonion.rem import source_hooks
    root, _, _ = configured
    before = read_json(state_path(root, "source-acquisition.json"), {})

    def broken_query(connection, *args):
        connection.execute(sql, parameters)

    monkeypatch.setattr(store, "_collect", broken_query)
    with pytest.raises(error_type):
        source_hooks.fetch(root)
    assert read_json(state_path(root, "source-acquisition.json"), {}) == before


def test_actual_sqlite_corruption_blocks_saved_material(configured):
    from connectonion.rem import source_hooks
    root, _, _ = configured
    state_path(root, store.DATABASE).write_bytes(b"not a SQLite database")

    result = source_hooks.fetch(root)["obsidian"]

    assert result["ok"] is False and result["allow_saved"] is False
    assert state_path(root, store.DATABASE).read_bytes() == b"not a SQLite database"
