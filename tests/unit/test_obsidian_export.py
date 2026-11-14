"""Obsidian incremental collection: sync_notes(), export_status(), latest_snapshots(),
load_snapshots() and source_log() in useful_tools/obsidian_export.py.

Acceptance criteria covered:
  * each sync appends one Note record per changed note (stable ID, path, change type, time,
    metadata, body) to the agreed location; a second sync with no changes appends nothing;
    an unreadable vault reports an error without advancing the cursor;
  * a source ID such as obsidian:<...> traces back to the note's path and collection time
    (the CLI side, `co rem logs --source`, is in test_obsidian_commands.py).

Vaults, the inbox root and the notebook root all live under tmp_path; time is fixed through
obsidian_export._now; nothing reads a real vault, runs REM or calls a model.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from connectonion.useful_tools import obsidian
from connectonion.useful_tools import obsidian_export as export
from tests.unit.test_obsidian import _disk, _notes_vault, isolated_home  # noqa: F401

pytestmark = pytest.mark.unit

T1 = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
T3 = datetime(2026, 11, 3, 9, 0, tzinfo=timezone.utc)
SOURCE_ID = re.compile(r"obsidian:[0-9a-f]{32}:[0-9a-f]{32}:[0-9a-f]{32}")
RECORD_FIELDS = {"schema", "source_instance_id", "note_id", "event_id", "source_id", "path", "change_type",
                 "reason", "observed_at", "source_modified_at", "scope_revision", "previous_source_id",
                 "content_hash", "note", "ingested_at"}


# -- fixtures ----------------------------------------------------------------

@pytest.fixture(autouse=True)
def inbox(monkeypatch, tmp_path):
    """The agreed source root (inbox/obsidian) points into tmp_path."""
    root = tmp_path / "inbox"
    monkeypatch.setenv("CO_INBOX_HOME", str(root))
    return root


@pytest.fixture
def clock(monkeypatch):
    """Fixed collection time; set clock.now to move it."""
    class Clock:
        now = T1
    monkeypatch.setattr(export, "_now", lambda: Clock.now)
    return Clock


@pytest.fixture
def notebook(tmp_path):
    return tmp_path / "rem"


@pytest.fixture
def vault(tmp_path):
    return _notes_vault(tmp_path, {
        "Course/lecture.md": "---\ntags: [exam]\nweek: 3\n---\nLogic notes, see [[Reading]] #study\n",
        "Course/Reading.md": "Reading list\r\nwith CRLF\r\n",
        "Course/Week1/intro.md": "第一周 🌿\n",
        "Other/outside.md": "never collected\n",
    }, name="Vault")


def _sync(vault, notebook, folders=("Course",), **kwargs):
    return export.sync_notes(vault, folders=list(folders), notebook_root=notebook, **kwargs)


def _records(source_dir):
    """Every committed line, read the way a reader may: up to the committed boundary."""
    state = json.loads((Path(source_dir) / ".state/manifest.json").read_text(encoding="utf-8"))
    rows = []
    for relative, size in sorted(state["committed_bytes"].items()):
        data = (Path(source_dir) / relative).read_bytes()[:size]
        rows += [json.loads(line) for line in data.decode("utf-8").splitlines() if line]
    return rows


def _manifest(source_dir):
    return json.loads((Path(source_dir) / ".state/manifest.json").read_text(encoding="utf-8"))


def _daily_bytes(source_dir):
    daily = Path(source_dir) / "daily"
    return {p.relative_to(daily).as_posix(): p.read_bytes() for p in sorted(daily.rglob("*.jsonl"))}


def _by_path(rows):
    return {row["path"]: row for row in rows}


# -- first sync: one record per note, at the agreed location ---------------------

def test_first_sync_records_every_selected_note_as_added(vault, notebook, clock):
    result = _sync(vault, notebook)

    assert result["scanned_notes"] == 3 and result["appended_records"] == 3
    assert (result["added"], result["modified"], result["deleted"]) == (3, 0, 0)
    rows = _records(result["source_dir"])
    assert sorted(row["path"] for row in rows) == ["Course/Reading.md", "Course/Week1/intro.md", "Course/lecture.md"]
    assert all(row["change_type"] == "added" for row in rows)
    assert [row["source_id"] for row in rows] == result["source_ids"]


def test_a_note_record_has_stable_id_path_type_time_metadata_and_body(vault, notebook, clock):
    result = _sync(vault, notebook)

    row = _by_path(_records(result["source_dir"]))["Course/lecture.md"]
    assert set(row) == RECORD_FIELDS
    assert row["schema"] == "obsidian-note-change/1"
    assert re.fullmatch(r"[0-9a-f]{32}", row["note_id"])
    assert SOURCE_ID.fullmatch(row["source_id"])
    assert row["source_id"] == f"obsidian:{result['source_instance_id']}:{row['note_id']}:{row['event_id']}"
    assert row["path"] == "Course/lecture.md" and row["change_type"] == "added" and row["reason"] is None
    assert row["observed_at"] == T1.isoformat()
    assert datetime.fromisoformat(row["source_modified_at"]).tzinfo is not None
    note = row["note"]
    assert note["content"] == (vault / "Course/lecture.md").read_text(encoding="utf-8")
    assert note["frontmatter"] == {"tags": ["exam"], "week": 3}
    assert set(note["tags"]) >= {"exam", "study"}
    assert [link["target"] for link in note["links"]] == ["Reading"]
    assert row["content_hash"].startswith("sha256:") and row["ingested_at"] is None


def test_body_bytes_are_kept_exactly(vault, notebook, clock):
    rows = _by_path(_records(_sync(vault, notebook)["source_dir"]))

    assert rows["Course/Reading.md"]["note"]["content"] == "Reading list\r\nwith CRLF\r\n"
    assert rows["Course/Week1/intro.md"]["note"]["content"] == "第一周 🌿\n"


def test_records_go_to_the_inbox_daily_file_of_the_collection_day(vault, notebook, clock, inbox):
    result = _sync(vault, notebook)

    source = Path(result["source_dir"])
    assert source == export.source_directory(vault, notebook_root=notebook)
    assert source.parent == inbox / "obsidian" and re.fullmatch(r"[0-9a-f]{32}", source.name)
    assert list(_daily_bytes(source)) == ["2026/11/01.jsonl"]
    assert (source / ".state/manifest.json").is_file()


def test_notes_outside_the_folders_and_system_folders_are_not_recorded(vault, notebook, clock):
    (vault / ".obsidian/workspace.md").write_text("system\n", encoding="utf-8")

    rows = _records(_sync(vault, notebook)["source_dir"])

    paths = {row["path"] for row in rows}
    assert "Other/outside.md" not in paths and ".obsidian/workspace.md" not in paths


def test_collection_never_changes_the_vault(vault, notebook, clock):
    before = _disk(vault)

    _sync(vault, notebook)
    (vault / "Course/lecture.md").write_text("changed\n", encoding="utf-8")
    after_edit = _disk(vault)
    _sync(vault, notebook)

    assert _disk(vault) == after_edit and len(before) == len(after_edit)


# -- second sync without changes appends nothing ----------------------------------

def test_a_second_sync_without_changes_appends_nothing(vault, notebook, clock):
    first = _sync(vault, notebook)
    files = _daily_bytes(first["source_dir"])
    count = _manifest(first["source_dir"])["record_count"]

    clock.now = T2
    second = _sync(vault, notebook)

    assert second["appended_records"] == 0 and second["source_ids"] == []
    assert (second["added"], second["modified"], second["deleted"]) == (0, 0, 0)
    assert _daily_bytes(first["source_dir"]) == files
    assert _manifest(first["source_dir"])["record_count"] == count
    assert second["cursor"] == T2.isoformat()


def test_a_new_mtime_with_the_same_content_is_not_a_change(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    os.utime(vault / "Course/lecture.md", ns=(2_000_000_000_000_000_000,) * 2)

    assert _sync(vault, notebook)["appended_records"] == 0
    assert len(_records(source)) == 3


# -- modified / deleted / re-added / renamed ----------------------------------------

def test_a_modified_note_keeps_its_id_and_links_to_the_previous_record(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    first = _by_path(_records(source))["Course/lecture.md"]

    clock.now = T2
    (vault / "Course/lecture.md").write_text("rewritten body\n", encoding="utf-8")
    result = _sync(vault, notebook)

    assert (result["added"], result["modified"], result["deleted"]) == (0, 1, 0)
    row = _records(source)[-1]
    assert row["change_type"] == "modified" and row["path"] == "Course/lecture.md"
    assert row["note_id"] == first["note_id"] and row["source_id"] != first["source_id"]
    assert row["previous_source_id"] == first["source_id"]
    assert row["note"]["content"] == "rewritten body\n" and row["observed_at"] == T2.isoformat()
    assert list(_daily_bytes(source)) == ["2026/11/01.jsonl", "2026/11/02.jsonl"]


def test_a_deleted_note_is_a_tombstone_without_content(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    first = _by_path(_records(source))["Course/Reading.md"]

    (vault / "Course/Reading.md").unlink()
    result = _sync(vault, notebook)

    assert (result["added"], result["modified"], result["deleted"]) == (0, 0, 1)
    row = _records(source)[-1]
    assert row["change_type"] == "deleted" and row["reason"] == "source_deleted"
    assert row["note"] is None and row["content_hash"] is None
    assert row["note_id"] == first["note_id"] and row["previous_source_id"] == first["source_id"]
    assert _sync(vault, notebook)["appended_records"] == 0          # a tombstone is written once


def test_a_note_created_again_at_the_same_path_is_added_with_its_old_id(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    note_id = _by_path(_records(source))["Course/Reading.md"]["note_id"]
    (vault / "Course/Reading.md").unlink()
    _sync(vault, notebook)

    (vault / "Course/Reading.md").write_text("back again\n", encoding="utf-8")
    result = _sync(vault, notebook)

    row = _records(source)[-1]
    assert result["added"] == 1 and row["change_type"] == "added" and row["note_id"] == note_id


def test_a_rename_is_a_deletion_plus_an_addition(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    old = _by_path(_records(source))["Course/Reading.md"]

    (vault / "Course/Reading.md").rename(vault / "Course/Books.md")
    result = _sync(vault, notebook)

    assert (result["added"], result["deleted"]) == (1, 1)
    new_rows = _by_path(_records(source)[-2:])
    assert new_rows["Course/Reading.md"]["change_type"] == "deleted"
    assert new_rows["Course/Books.md"]["change_type"] == "added"
    assert new_rows["Course/Books.md"]["note_id"] != old["note_id"]


def test_each_record_has_its_own_source_id_and_the_note_id_is_stable(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    for body in ("v2\n", "v3\n"):
        (vault / "Course/lecture.md").write_text(body, encoding="utf-8")
        _sync(vault, notebook)

    rows = [row for row in _records(source) if row["path"] == "Course/lecture.md"]
    assert len(rows) == 3 and len({row["note_id"] for row in rows}) == 1
    assert len({row["source_id"] for row in rows}) == 3


def test_excluding_a_collected_note_records_its_removal(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]

    result = _sync(vault, notebook, excluded_paths=["Course/lecture.md"])

    row = _records(source)[-1]
    assert result["deleted"] == 1 and row["path"] == "Course/lecture.md"
    assert row["change_type"] == "deleted" and row["reason"] == "excluded"
    assert (vault / "Course/lecture.md").exists()


def test_narrowing_the_folders_records_scope_removal_not_source_deletion(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]

    _sync(vault, notebook, folders=("Course/Week1",))

    removed = {row["path"]: row for row in _records(source)[-2:]}
    assert set(removed) == {"Course/lecture.md", "Course/Reading.md"}
    assert all(row["change_type"] == "deleted" and row["reason"] == "scope_removed" for row in removed.values())


# -- unreadable vault: error, cursor not advanced ------------------------------------

def test_a_missing_vault_is_an_error_and_nothing_is_written(tmp_path, notebook, clock):
    with pytest.raises((obsidian.ObsidianError, ValueError)):
        export.sync_notes(tmp_path / "vaults" / "Gone", folders=["."], notebook_root=notebook)

    assert not (tmp_path / "inbox" / "obsidian").exists() or not any((tmp_path / "inbox" / "obsidian").rglob("*.jsonl"))


def test_an_unreadable_note_fails_the_pass_without_advancing_the_cursor(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    before = _manifest(source)
    files = _daily_bytes(source)

    clock.now = T2
    (vault / "Course/lecture.md").write_text("changed\n", encoding="utf-8")
    (vault / "Course/bad.md").write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(obsidian.ObsidianError) as caught:
        _sync(vault, notebook)

    assert "Course/bad.md" in caught.value.failed_paths
    after = _manifest(source)
    assert after["cursor"] == before["cursor"] == T1.isoformat()
    assert after["record_count"] == before["record_count"] and after["notes"] == before["notes"]
    assert after["last_success_at"] == before["last_success_at"]
    assert after["last_failure"]["at"] == T2.isoformat()
    assert _daily_bytes(source) == files


def test_after_the_bad_note_is_fixed_the_change_is_collected_once(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    (vault / "Course/lecture.md").write_text("changed\n", encoding="utf-8")
    (vault / "Course/bad.md").write_bytes(b"\xff")
    with pytest.raises(obsidian.ObsidianError):
        _sync(vault, notebook)

    (vault / "Course/bad.md").write_text("fixed\n", encoding="utf-8")
    result = _sync(vault, notebook)

    assert (result["added"], result["modified"]) == (1, 1)
    assert _manifest(source)["last_failure"] is None
    assert sum(row["path"] == "Course/lecture.md" for row in _records(source)) == 2


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs POSIX permissions and a non-root user")
def test_a_note_without_read_permission_fails_without_advancing(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    cursor = _manifest(source)["cursor"]
    note = vault / "Course/Reading.md"
    note.chmod(0)
    try:
        clock.now = T2
        with pytest.raises(obsidian.ObsidianError):
            _sync(vault, notebook)
        assert _manifest(source)["cursor"] == cursor
    finally:
        note.chmod(0o644)


# -- store safety -----------------------------------------------------------------------

def test_the_source_directory_cannot_be_inside_the_vault(vault, notebook, clock):
    with pytest.raises(ValueError):
        _sync(vault, notebook, source_dir=vault / "export")

    assert not (vault / "export").exists()


def test_a_source_directory_is_bound_to_one_vault(vault, notebook, clock, tmp_path):
    source = _sync(vault, notebook)["source_dir"]
    other = _notes_vault(tmp_path, {"Course/x.md": "x\n"}, name="Other")

    with pytest.raises(export.ObsidianStoreError) as caught:
        export.sync_notes(other, source, folders=["Course"], notebook_root=notebook)

    assert caught.value.stage == "binding"


def test_daily_material_without_a_manifest_is_never_reset(vault, notebook, clock):
    source = Path(_sync(vault, notebook)["source_dir"])
    files = _daily_bytes(source)
    (source / ".state/manifest.json").unlink()

    with pytest.raises(export.ObsidianStoreError) as caught:
        _sync(vault, notebook)

    assert caught.value.stage == "state"
    assert _daily_bytes(source) == files


def test_an_uncommitted_tail_is_invisible_and_cut_before_the_next_append(vault, notebook, clock):
    source = Path(_sync(vault, notebook)["source_dir"])
    daily = source / "daily/2026/11/01.jsonl"
    committed = daily.read_bytes()
    with open(daily, "ab") as handle:
        handle.write(b'{"half a record')

    assert len(export.load_snapshots(source, export.latest_snapshots(source))) == 3
    _sync(vault, notebook)

    assert daily.read_bytes() == committed


def test_a_symlink_in_daily_is_refused_and_its_target_left_alone(vault, notebook, clock, tmp_path):
    source = Path(_sync(vault, notebook)["source_dir"])
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"x" * 34)
    (source / "daily/2026/11/02.jsonl").symlink_to(outside)

    with pytest.raises(export.ObsidianStoreError):
        _sync(vault, notebook)

    assert outside.read_bytes() == b"x" * 34


def test_a_failed_manifest_replacement_keeps_the_previous_pass(vault, notebook, clock, monkeypatch):
    source = Path(_sync(vault, notebook)["source_dir"])
    before = _manifest(source)
    (vault / "Course/lecture.md").write_text("changed\n", encoding="utf-8")
    real = os.replace
    calls = []

    def fail_first(src, dst, *args, **kwargs):
        calls.append(dst)
        if len(calls) == 1:
            raise OSError(28, "No space left on device")
        return real(src, dst, *args, **kwargs)
    monkeypatch.setattr(os, "replace", fail_first)

    with pytest.raises(export.ObsidianStoreError) as caught:
        _sync(vault, notebook)

    assert caught.value.stage == "write" and caught.value.committed is False
    after = _manifest(source)
    assert after["cursor"] == before["cursor"] and after["record_count"] == before["record_count"]
    assert len(export.latest_snapshots(source)) == 3
    monkeypatch.setattr(os, "replace", real)
    assert _sync(vault, notebook)["modified"] == 1
    assert sum(row["path"] == "Course/lecture.md" for row in _records(source)) == 2


def test_a_durability_error_after_replacement_says_the_pass_is_committed(vault, notebook, clock, monkeypatch):
    source = Path(_sync(vault, notebook)["source_dir"])
    (vault / "Course/lecture.md").write_text("changed\n", encoding="utf-8")
    real = export._sync_directory

    def fail_state_dir(path):
        if Path(path).name == ".state":
            raise OSError(5, "I/O error")
        return real(path)
    monkeypatch.setattr(export, "_sync_directory", fail_state_dir)

    with pytest.raises(export.ObsidianStoreError) as caught:
        _sync(vault, notebook)

    assert caught.value.stage == "durability" and caught.value.committed is True
    monkeypatch.setattr(export, "_sync_directory", real)
    assert _manifest(source)["record_count"] == 4


def test_a_second_collection_while_one_runs_is_refused(vault, notebook, clock):
    source = Path(_sync(vault, notebook)["source_dir"])

    with export._source_lock(source):
        with pytest.raises(export.ObsidianStoreError) as caught:
            _sync(vault, notebook)

    assert caught.value.stage == "lock"


@pytest.mark.parametrize("folders", [[".obsidian"], ["../outside"], ["/abs"]])
def test_unsafe_selections_are_refused_before_writing(folders, vault, notebook, clock, inbox):
    with pytest.raises((ValueError, obsidian.ObsidianError)):
        _sync(vault, notebook, folders=folders)

    assert not any(inbox.rglob("*.jsonl")) if inbox.exists() else True


# -- readers ---------------------------------------------------------------------------

def test_status_before_any_collection_is_not_initialized_and_creates_nothing(tmp_path):
    source = tmp_path / "inbox" / "obsidian" / ("0" * 32)

    status = export.export_status(source)

    assert status["initialized"] is False and status["record_count"] == 0 and status["cursor"] is None
    assert not source.exists()


def test_status_after_collection(vault, notebook, clock):
    result = _sync(vault, notebook)

    status = export.export_status(result["source_dir"])

    assert status["initialized"] is True and status["record_count"] == 3
    assert status["cursor"] == status["last_success_at"] == T1.isoformat()
    assert status["folders"] == ["Course"] and status["last_failure"] is None
    assert status["vault"] == str(vault.resolve()) and status["notebook_root"] == str(notebook.resolve())


def test_latest_snapshots_hide_tombstones_unless_asked(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    (vault / "Course/Reading.md").unlink()
    _sync(vault, notebook)

    live = {entry["path"] for entry in export.latest_snapshots(source)}
    every = {entry["path"]: entry["change_type"] for entry in export.latest_snapshots(source, include_deleted=True)}

    assert live == {"Course/lecture.md", "Course/Week1/intro.md"}
    assert every["Course/Reading.md"] == "deleted"


def test_load_snapshots_returns_the_committed_records(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]

    loaded = export.load_snapshots(source, export.latest_snapshots(source))

    assert {row["path"] for row in loaded} == {"Course/lecture.md", "Course/Reading.md", "Course/Week1/intro.md"}
    assert all(row["note"]["content"] == (Path(vault) / row["path"]).read_text(encoding="utf-8")
               for row in loaded if row["path"] != "Course/Reading.md")


def test_load_snapshots_refuses_a_changed_or_unknown_locator(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    entry = export.latest_snapshots(source)[0]

    for bad in ({**entry, "locator": {**entry["locator"], "offset": entry["locator"]["offset"] + 1}},
                {**entry, "source_id": "obsidian:" + ":".join(["0" * 32] * 3)}, "not a dict"):
        with pytest.raises(export.ObsidianStoreError) as caught:
            export.load_snapshots(source, [bad])
        assert caught.value.stage == "read"


def test_tampered_record_content_is_detected(vault, notebook, clock):
    source = Path(_sync(vault, notebook)["source_dir"])
    daily = source / "daily/2026/11/01.jsonl"
    data = daily.read_bytes()
    daily.write_bytes(data.replace("第一周".encode("utf-8"), "第二周".encode("utf-8")))

    with pytest.raises(export.ObsidianStoreError) as caught:
        export.load_snapshots(source, export.latest_snapshots(source))

    assert caught.value.stage == "read"


# -- source ID tracing ---------------------------------------------------------------------

def test_source_log_traces_an_id_to_the_path_and_collection_time(vault, notebook, clock):
    result = _sync(vault, notebook)
    rows = _by_path(_records(result["source_dir"]))
    source_id = rows["Course/lecture.md"]["source_id"]

    log = export.source_log(result["source_dir"], source_id, notebook_root=notebook)

    assert log["source_id"] == source_id and log["path"] == "Course/lecture.md"
    assert log["change_type"] == "added" and log["collected_at"] == T1.isoformat()
    assert "note" not in log and "locator" not in log
    assert "Logic notes" not in json.dumps(log, ensure_ascii=False)


def test_source_log_keeps_every_version_traceable(vault, notebook, clock):
    source = _sync(vault, notebook)["source_dir"]
    first = _by_path(_records(source))["Course/lecture.md"]["source_id"]
    clock.now = T2
    (vault / "Course/lecture.md").write_text("changed\n", encoding="utf-8")
    second = _sync(vault, notebook)["source_ids"][0]

    old = export.source_log(source, first, notebook_root=notebook)
    new = export.source_log(source, second, notebook_root=notebook)

    assert old["collected_at"] == T1.isoformat() and old["change_type"] == "added"
    assert new["collected_at"] == T2.isoformat() and new["previous_source_id"] == first


def test_source_log_refuses_an_unknown_id_or_another_notebook(vault, notebook, clock, tmp_path):
    result = _sync(vault, notebook)
    known = result["source_ids"][0]
    unknown = f"obsidian:{result['source_instance_id']}:{'0' * 32}:{'1' * 32}"

    with pytest.raises(export.ObsidianStoreError) as caught:
        export.source_log(result["source_dir"], unknown, notebook_root=notebook)
    assert caught.value.stage == "read"
    with pytest.raises(export.ObsidianStoreError) as caught:
        export.source_log(result["source_dir"], known, notebook_root=tmp_path / "other")
    assert caught.value.stage == "binding"


def test_source_log_does_not_read_the_vault(vault, notebook, clock, monkeypatch):
    result = _sync(vault, notebook)
    monkeypatch.setattr(obsidian, "_read_markdown", lambda *a, **k: pytest.fail("tracing must not read notes"))

    log = export.source_log(result["source_dir"], result["source_ids"][0], notebook_root=notebook)

    assert log["path"]
