"""Unit tests for connectonion/cli/commands/granola_commands.py.

All tests use synthetic fixtures and mocked GranolaClient.
No real API keys or network calls required.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from tests.unit.granola_fixtures import (
    FOLDER_ID,
    FOLDER_IN_SPACE,
    FOLDERS_PAGE,
    NOTE_DELETED_FULL,
    NOTE_FULL,
    NOTE_IN_SPACE,
    NOTE_MINIMAL,
    NOTE_STUB_1,
    NOTE_STUB_2,
    NOTE_STUB_DELETED,
    NOTES_SINGLE_PAGE,
    NOTES_EMPTY,
    PROFILE,
    _API_KEY,
)
from connectonion.useful_tools.granola import (
    GranolaAuthError,
    GranolaConfigError,
    GranolaIncompleteRead,
    GranolaPermissionError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_client(
    *,
    verify_return=None,
    folders_return=None,
    notes_return=None,
    notes_raise=None,
):
    """Return a MagicMock that mimics GranolaClient's public API surface."""
    client = MagicMock()
    client.verify.return_value = verify_return or {"verified_read": True, "note": "Weekly Sync"}
    client.list_folders.return_value = folders_return if folders_return is not None else FOLDERS_PAGE["folders"]
    if notes_raise is not None:
        client.list_notes.side_effect = notes_raise
    else:
        client.list_notes.return_value = notes_return if notes_return is not None else [NOTE_FULL, NOTE_MINIMAL]
    client.hydrate_notes.side_effect = lambda notes: notes
    client.write_source_yaml = MagicMock()
    return client


def _patch_granola(monkeypatch, client):
    monkeypatch.setattr(
        "connectonion.cli.commands.granola_commands._granola",
        lambda: client,
    )


# ---------------------------------------------------------------------------
# Tests: handle_granola_verify
# ---------------------------------------------------------------------------


class TestHandleGranolaVerify:
    def test_verify_success_prints_note_and_next(self, monkeypatch, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_verify
        client = _mock_client(verify_return={"verified_read": True, "note": "Team Standup"})
        _patch_granola(monkeypatch, client)

        handle_granola_verify()

        out = capsys.readouterr().out
        assert "Team Standup" in out
        assert "Next:" in out
        # Canvas spec: terminal output must include the scope caveat.
        assert "does not confirm" in out.lower() or "minimal" in out.lower()

    def test_verify_success_json(self, monkeypatch, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_verify
        client = _mock_client(verify_return={"verified_read": True, "note": "Weekly Sync"})
        _patch_granola(monkeypatch, client)

        handle_granola_verify(as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert payload["verified_read"] is True
        assert payload["note"] == "Weekly Sync"
        # Canvas spec: JSON must include verify_scope caveat.
        assert "verify_scope" in payload
        assert "minimal" in payload["verify_scope"].lower()

    def test_verify_config_error_exits_1(self, monkeypatch):
        from connectonion.cli.commands.granola_commands import handle_granola_verify
        client = _mock_client()
        client.verify.side_effect = GranolaConfigError("GRANOLA_API_KEY missing")
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_verify()
        assert exc_info.value.code == 1

    def test_verify_auth_error_exits_1(self, monkeypatch):
        from connectonion.cli.commands.granola_commands import handle_granola_verify
        client = _mock_client()
        client.verify.side_effect = GranolaAuthError("401")
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_verify()
        assert exc_info.value.code == 1

    def test_verify_auth_error_json_includes_recovery(self, monkeypatch, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_verify
        client = _mock_client()
        client.verify.side_effect = GranolaAuthError("401 Unauthorized")
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit):
            handle_granola_verify(as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert payload["exit_code"] == 1
        assert payload["source"] == "granola"
        assert "recovery_action" in payload

    def test_verify_permission_error_exits_1(self, monkeypatch):
        from connectonion.cli.commands.granola_commands import handle_granola_verify
        client = _mock_client()
        client.verify.side_effect = GranolaPermissionError("403")
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_verify()
        assert exc_info.value.code == 1

    def test_verify_incomplete_read_exits_1_with_transient_error_code(self, monkeypatch, capsys):
        """GranolaIncompleteRead on verify() (429/5xx retries exhausted) → exit 1, error_code transient_error."""
        from connectonion.cli.commands.granola_commands import handle_granola_verify
        client = _mock_client()
        client.verify.side_effect = GranolaIncompleteRead(
            reason="500 after 3 retries", partial_pages=[]
        )
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_verify(as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["exit_code"] == 1
        assert payload["source"] == "granola"
        assert payload["error_code"] == "transient_error"
        assert "recovery_action" in payload


# ---------------------------------------------------------------------------
# Tests: handle_granola_folders
# ---------------------------------------------------------------------------


class TestHandleGranolaFolders:
    def test_folders_success_prints_ids_and_next(self, monkeypatch, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_folders
        folders = FOLDERS_PAGE["folders"]
        client = _mock_client(folders_return=folders)
        _patch_granola(monkeypatch, client)

        handle_granola_folders()

        out = capsys.readouterr().out
        assert "fld-fixture" in out
        assert "Team Meetings" in out
        assert "Next:" in out

    def test_folders_empty_prints_message(self, monkeypatch, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_folders
        client = _mock_client(folders_return=[])
        _patch_granola(monkeypatch, client)

        handle_granola_folders()

        out = capsys.readouterr().out
        assert "No personal folders" in out

    def test_folders_json_output(self, monkeypatch, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_folders
        folders = FOLDERS_PAGE["folders"]
        client = _mock_client(folders_return=folders)
        _patch_granola(monkeypatch, client)

        handle_granola_folders(as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert "folders" in payload
        assert len(payload["folders"]) == 2
        ids = [f["id"] for f in payload["folders"]]
        assert "fld-fixture" in ids

    def test_folders_auth_error_exits_1(self, monkeypatch):
        from connectonion.cli.commands.granola_commands import handle_granola_folders
        client = _mock_client()
        client.list_folders.side_effect = GranolaAuthError("401")
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_folders()
        assert exc_info.value.code == 1

    def test_folders_config_error_json_output(self, monkeypatch, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_folders
        client = _mock_client()
        client.list_folders.side_effect = GranolaConfigError("missing key")
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit):
            handle_granola_folders(as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert payload["exit_code"] == 1
        assert payload["source"] == "granola"

    def test_folders_incomplete_read_exits_1_with_transient_error_code(self, monkeypatch, capsys):
        """GranolaIncompleteRead on list_folders() (429/5xx retries exhausted) → exit 1, error_code transient_error."""
        from connectonion.cli.commands.granola_commands import handle_granola_folders
        client = _mock_client()
        client.list_folders.side_effect = GranolaIncompleteRead(
            reason="429 rate limit on 3 retries", partial_pages=[]
        )
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_folders(as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["exit_code"] == 1
        assert payload["source"] == "granola"
        assert payload["error_code"] == "transient_error"
        assert "recovery_action" in payload

    def test_folders_filters_space_folders(self, monkeypatch, capsys):
        """Folders with space_id != None are filtered out; only personal (space_id=None) folders shown."""
        from connectonion.cli.commands.granola_commands import handle_granola_folders
        # Mix 2 personal folders + 1 space folder
        mixed = FOLDERS_PAGE["folders"] + [FOLDER_IN_SPACE]
        client = _mock_client(folders_return=mixed)
        _patch_granola(monkeypatch, client)

        handle_granola_folders(as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert len(payload["folders"]) == 2  # space folder excluded
        ids = [f["id"] for f in payload["folders"]]
        assert "fld-in-space" not in ids     # FOLDER_IN_SPACE is excluded
        assert "fld-fixture" in ids          # personal folders retained


# ---------------------------------------------------------------------------
# Tests: handle_granola_import
# ---------------------------------------------------------------------------


class TestHandleGranolaImport:
    def test_import_rejects_existing_different_source_before_network(
        self, monkeypatch, tmp_path, capsys,
    ):
        from connectonion.cli.commands import granola_commands

        existing = {
            "driver": "granola", "account": PROFILE,
            "scope": {"folder_id": "another-personal-folder"},
        }
        source = tmp_path / "source.yaml"
        source.write_text(yaml.safe_dump(existing), encoding="utf-8")
        original = source.read_bytes()

        def unexpected_client():
            pytest.fail("Granola client must not be created for a mismatched source")

        monkeypatch.setattr(granola_commands, "_granola", unexpected_client)
        with pytest.raises(SystemExit) as exc_info:
            granola_commands.handle_granola_import(
                FOLDER_ID, profile=PROFILE, output_dir=tmp_path, as_json=True,
            )
        assert exc_info.value.code == 1
        assert json.loads(capsys.readouterr().out)["error_code"] == "invalid_configuration"
        assert source.read_bytes() == original

    def test_import_success_writes_source_yaml(self, monkeypatch, tmp_path, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[NOTE_FULL, NOTE_MINIMAL])
        _patch_granola(monkeypatch, client)

        handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path)

        # write_source_yaml was called with complete=True (full read).
        # limit=1000 (MAX_SELECTED) because no --limit flag was supplied; the P1 fix
        # computes effective_limit before calling write_source_yaml so manifest and
        # source.yaml record the same value.
        from connectonion.useful_tools.granola import MAX_SELECTED
        client.write_source_yaml.assert_called_once_with(tmp_path, FOLDER_ID, PROFILE, limit=MAX_SELECTED, complete=True, note_id=None)
        out = capsys.readouterr().out
        assert "Next:" in out

    def test_import_success_json_fields(self, monkeypatch, tmp_path, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[NOTE_FULL, NOTE_MINIMAL])
        _patch_granola(monkeypatch, client)

        handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path, as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert payload["folder_id"] == FOLDER_ID
        assert payload["profile"] == PROFILE
        assert payload["notes"] == 2
        assert payload["mapped"] == 2
        assert payload["complete"] is True
        assert payload["rejected"] == {}
        assert Path(payload["jsonl"]).exists()

    def test_import_empty_folder_exits_0(self, monkeypatch, tmp_path, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[])
        _patch_granola(monkeypatch, client)

        # Should not raise
        handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path, as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert payload["notes"] == 0
        assert payload["mapped"] == 0
        assert payload["complete"] is True

    def test_import_auth_error_exits_1_no_files(self, monkeypatch, tmp_path):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_raise=GranolaAuthError("401"))
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path)
        assert exc_info.value.code == 1
        # No source.yaml written
        assert not (tmp_path / "source.yaml").exists()

    def test_import_config_error_exits_1(self, monkeypatch, tmp_path):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_raise=GranolaConfigError("no key"))
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path)
        assert exc_info.value.code == 1

    def test_import_incomplete_read_retains_partial_records_exits_1(
        self, monkeypatch, tmp_path, capsys
    ):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        exc = GranolaIncompleteRead(
            reason="transient 500 on 4 attempts",
            partial_pages=[[NOTE_FULL], [NOTE_MINIMAL]],
        )
        client = _mock_client(notes_raise=exc)
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path, as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["complete"] is False
        assert payload["notes"] == 2          # NOTE_FULL + NOTE_MINIMAL from 2 partial pages
        assert payload["mapped"] == 2         # both map successfully
        assert payload["appended"] == 2
        # source.yaml IS written even on partial read (complete=False in YAML) so
        # source metadata (scope, profile, limit) is always present alongside records.
        assert payload["written"] is not None
        assert "source.yaml" in payload["written"]
        # write_source_yaml was called with complete=False.
        # limit=1000 (MAX_SELECTED) because no --limit flag was supplied.
        from connectonion.useful_tools.granola import MAX_SELECTED
        client.write_source_yaml.assert_called_once_with(tmp_path, FOLDER_ID, PROFILE, limit=MAX_SELECTED, complete=False, note_id=None)
        # Daily JSONL is still written with the partial records
        assert payload["jsonl"] is not None
        assert Path(payload["jsonl"]).exists()

    def test_import_incomplete_read_no_partial_pages(
        self, monkeypatch, tmp_path, capsys
    ):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        exc = GranolaIncompleteRead(
            reason="immediate 500",
            partial_pages=[],
        )
        client = _mock_client(notes_raise=exc)
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path, as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["complete"] is False
        assert payload["notes"] == 0
        assert payload["mapped"] == 0

    def test_import_space_only_note_rejected_valid_notes_retained(
        self, monkeypatch, tmp_path, capsys
    ):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        # NOTE_IN_SPACE has folder_id=None — rejected by adapter
        client = _mock_client(notes_return=[NOTE_FULL, NOTE_IN_SPACE])
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path, as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["notes"] == 2        # 2 collected
        assert payload["mapped"] == 1       # only NOTE_FULL mapped
        assert len(payload["rejected"]) == 1
        assert payload["complete"] is True  # read was complete, just a mapping error

    def test_import_profile_used_in_record_id(self, monkeypatch, tmp_path, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        profile = "myoffice"
        client = _mock_client(notes_return=[NOTE_FULL])
        _patch_granola(monkeypatch, client)

        handle_granola_import(FOLDER_ID, profile=profile, output_dir=tmp_path, as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert payload["profile"] == profile
        # Verify JSONL contains a record with the correct account
        jsonl_path = Path(payload["jsonl"])
        records = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]
        assert records[0]["account"] == profile
        assert records[0]["source"] == "granola"

    def test_import_with_limit_forwarded_to_list_notes(self, monkeypatch, tmp_path):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[NOTE_FULL])
        _patch_granola(monkeypatch, client)

        handle_granola_import(FOLDER_ID, profile=PROFILE, limit=10, output_dir=tmp_path)

        client.list_notes.assert_called_once_with(folder_id=FOLDER_ID, limit=10)
        client.write_source_yaml.assert_called_once_with(tmp_path, FOLDER_ID, PROFILE, limit=10, complete=True, note_id=None)

    def test_import_with_export_id_writes_export(self, monkeypatch, tmp_path, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[NOTE_FULL])
        _patch_granola(monkeypatch, client)

        handle_granola_import(
            FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
            export_id="test-export-2026-10-24", as_json=True,
        )

        payload = json.loads(capsys.readouterr().out)
        assert payload["placement"] == "export"
        export_dir = tmp_path / "exports" / "test-export-2026-10-24"
        assert export_dir.is_dir()
        assert (export_dir / "records.jsonl").exists()
        assert (export_dir / "manifest.json").exists()

    def test_import_incomplete_read_export_manifest_records_complete_false(
        self, monkeypatch, tmp_path, capsys
    ):
        """A partial read with --export writes the manifest with scope.complete=false so the export is identifiable."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        exc = GranolaIncompleteRead(
            reason="transient 500 on 3 retries",
            partial_pages=[[NOTE_FULL]],
        )
        client = _mock_client(notes_raise=exc)
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(
                FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                export_id="partial-export-test", as_json=True,
            )
        assert exc_info.value.code == 1

        export_dir = tmp_path / "exports" / "partial-export-test"
        assert export_dir.is_dir()
        manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["scope"]["complete"] is False
        assert "failure_reason" in manifest["scope"]

    def test_import_bulk_export_manifest_scope_limit_is_max_selected_when_no_limit_given(
        self, monkeypatch, tmp_path, capsys
    ):
        """P1 fix: bulk export without --limit must record MAX_SELECTED in manifest scope, not null.

        Previously scope["limit"] was set to the raw CLI ``limit`` parameter (None when the flag
        is omitted), so the manifest carried null while source.yaml correctly recorded 1000.
        After the fix, effective_limit is computed first and applied to scope unconditionally.
        """
        from connectonion.cli.commands.granola_commands import handle_granola_import
        from connectonion.useful_tools.granola import MAX_SELECTED

        client = _mock_client(notes_return=[NOTE_FULL])
        _patch_granola(monkeypatch, client)

        handle_granola_import(
            FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
            export_id="bulk-limit-check", as_json=True,
            # no limit= kwarg → limit=None → effective_limit should be MAX_SELECTED
        )

        export_dir = tmp_path / "exports" / "bulk-limit-check"
        manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["scope"]["limit"] == MAX_SELECTED   # must NOT be null
        assert manifest["scope"]["limit"] is not None

    def test_import_duplicate_export_id_exits_1(self, monkeypatch, tmp_path, capsys):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        # Create the export directory to simulate an existing export
        existing = tmp_path / "exports" / "dup-export"
        existing.mkdir(parents=True)
        client = _mock_client(notes_return=[NOTE_FULL])
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(
                FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                export_id="dup-export",
            )
        assert exc_info.value.code == 1
        # list_notes should never be called if export_target raises
        client.list_notes.assert_not_called()

    def test_import_os_error_exits_1(self, monkeypatch, tmp_path):
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[NOTE_FULL])
        # Patch write_source_yaml to raise OSError
        client.write_source_yaml.side_effect = OSError("disk full")
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path)
        assert exc_info.value.code == 1

    def test_import_default_output_dir_used_when_not_specified(self, monkeypatch, tmp_path, capsys):
        """When output_dir=None, defaults to ~/.co/rem/docs/granola."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[NOTE_FULL])
        _patch_granola(monkeypatch, client)

        # Override Path.home() to use tmp_path
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

        handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=None, as_json=True)

        expected_dir = tmp_path / ".co" / "rem" / "docs" / "granola"
        # limit=1000 (MAX_SELECTED) because no --limit flag was supplied.
        from connectonion.useful_tools.granola import MAX_SELECTED
        client.write_source_yaml.assert_called_once_with(expected_dir, FOLDER_ID, PROFILE, limit=MAX_SELECTED, complete=True, note_id=None)

    def test_import_shared_space_folder_rejected(self, monkeypatch, tmp_path, capsys):
        """A folder with space_id != None is rejected before list_notes() or any file writes."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        # Only expose the shared-space folder so the target ID is accessible but not personal.
        client = _mock_client(folders_return=[FOLDER_IN_SPACE])
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_IN_SPACE["id"], profile=PROFILE, output_dir=tmp_path, as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_code"] == "personal_folder_required"
        assert "recovery_action" in payload
        client.list_notes.assert_not_called()
        client.write_source_yaml.assert_not_called()
        assert not (tmp_path / "source.yaml").exists()

    def test_import_unknown_folder_rejected(self, monkeypatch, tmp_path, capsys):
        """A folder ID absent from list_folders() is rejected before list_notes() or any file writes."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(folders_return=FOLDERS_PAGE["folders"])  # fld-fixture, fld-other only
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import("fld-does-not-exist", profile=PROFILE, output_dir=tmp_path, as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_code"] == "folder_not_found"
        assert "recovery_action" in payload
        client.list_notes.assert_not_called()
        client.write_source_yaml.assert_not_called()
        # No output directory contents created
        assert list(tmp_path.iterdir()) == []

    def test_import_list_folders_incomplete_read_exits_1_no_files(self, monkeypatch, tmp_path, capsys):
        """GranolaIncompleteRead from list_folders() during validation → transient_error, no side effects."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client()
        client.list_folders.side_effect = GranolaIncompleteRead(
            reason="429 rate limit on folder list", partial_pages=[]
        )
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path, as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_code"] == "transient_error"
        client.list_notes.assert_not_called()
        client.write_source_yaml.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: GranolaClient.write_source_yaml
# ---------------------------------------------------------------------------


class TestWriteSourceYaml:
    @pytest.mark.parametrize("changed_folder,changed_profile", [
        ("another-personal-folder", PROFILE),
        (FOLDER_ID, "another-profile"),
    ])
    def test_rejects_reusing_output_for_different_source(
        self, tmp_path, monkeypatch, changed_folder, changed_profile,
    ):
        from connectonion.useful_tools.granola import GranolaClient

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        client.write_source_yaml(tmp_path, FOLDER_ID, PROFILE)
        source = tmp_path / "source.yaml"
        original = source.read_bytes()

        with pytest.raises(GranolaConfigError, match="separate --output"):
            client.write_source_yaml(tmp_path, changed_folder, changed_profile)
        assert source.read_bytes() == original

    def test_allows_rerun_for_same_source(self, tmp_path, monkeypatch):
        from connectonion.useful_tools.granola import GranolaClient

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        client.write_source_yaml(tmp_path, FOLDER_ID, PROFILE)
        client.write_source_yaml(tmp_path, FOLDER_ID, PROFILE, limit=1, note_id="note-1")
        doc = yaml.safe_load((tmp_path / "source.yaml").read_text(encoding="utf-8"))
        assert doc["scope"]["folder_id"] == FOLDER_ID
        assert doc["scope"]["note_id"] == "note-1"

    def test_write_source_yaml_creates_file(self, tmp_path, monkeypatch):
        from connectonion.useful_tools.granola import GranolaClient

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        client.write_source_yaml(tmp_path, FOLDER_ID, PROFILE)

        assert (tmp_path / "source.yaml").exists()

    def test_write_source_yaml_fields(self, tmp_path, monkeypatch):
        from connectonion.useful_tools.granola import GranolaClient

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        client.write_source_yaml(tmp_path, FOLDER_ID, PROFILE, limit=50)

        doc = yaml.safe_load((tmp_path / "source.yaml").read_text(encoding="utf-8"))
        assert doc["driver"] == "granola"
        assert doc["account"] == PROFILE
        assert doc["scope"]["folder_id"] == FOLDER_ID
        assert doc["scope"]["limit"] == 50
        assert doc["retention"] == "90d"
        assert doc["media_policy"] == "metadata_only"
        assert "validated_with" in doc
        assert "connectonion_version" in doc["validated_with"]

    def test_write_source_yaml_limit_none_uses_max_selected(self, tmp_path, monkeypatch):
        from connectonion.useful_tools.granola import GranolaClient, MAX_SELECTED

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        client.write_source_yaml(tmp_path, FOLDER_ID, PROFILE, limit=None)

        doc = yaml.safe_load((tmp_path / "source.yaml").read_text(encoding="utf-8"))
        assert doc["scope"]["limit"] == MAX_SELECTED

    def test_write_source_yaml_invalid_profile_raises(self, tmp_path, monkeypatch):
        from connectonion.useful_tools.granola import GranolaClient

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        with pytest.raises(GranolaConfigError):
            client.write_source_yaml(tmp_path, FOLDER_ID, "invalid:profile")

    def test_write_source_yaml_creates_directory(self, tmp_path, monkeypatch):
        from connectonion.useful_tools.granola import GranolaClient

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        nested = tmp_path / "new_dir" / "granola"
        client.write_source_yaml(nested, FOLDER_ID, PROFILE)

        assert (nested / "source.yaml").exists()

    def test_write_source_yaml_complete_false_recorded(self, tmp_path, monkeypatch):
        """complete=False is written to source.yaml so partial reads are identifiable."""
        from connectonion.useful_tools.granola import GranolaClient

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        client.write_source_yaml(tmp_path, FOLDER_ID, PROFILE, complete=False)

        doc = yaml.safe_load((tmp_path / "source.yaml").read_text(encoding="utf-8"))
        assert doc["complete"] is False

    def test_write_source_yaml_excludes_api_key(self, tmp_path, monkeypatch):
        from connectonion.useful_tools.granola import GranolaClient

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        client.write_source_yaml(tmp_path, FOLDER_ID, PROFILE)

        content = (tmp_path / "source.yaml").read_text(encoding="utf-8")
        assert _API_KEY not in content


# ---------------------------------------------------------------------------
# Integration: CLI runner test (co granola import through the full CLI stack)
# ---------------------------------------------------------------------------


class TestGranolaImportCliRunner:
    def test_cli_import_exits_0_and_writes_jsonl(self, monkeypatch, tmp_path):
        """Smoke test the full CLI path through typer → handler → tool."""
        from typer.testing import CliRunner
        from connectonion.cli.main import app
        from connectonion.useful_tools import granola as granola_mod

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)

        # Patch httpx.Client so GranolaClient's _request_once uses mock data.
        import httpx
        original_init = httpx.Client.__init__

        class _MockTransport(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                assert request.method == "GET"
                path = request.url.path
                if path == "/v1/folders":
                    return httpx.Response(200, json=FOLDERS_PAGE, request=request)
                if path == "/v1/notes":
                    return httpx.Response(200, json=NOTES_SINGLE_PAGE, request=request)
                if path == f"/v1/notes/{NOTE_FULL['id']}":
                    return httpx.Response(200, json=NOTE_FULL, request=request)
                if path == f"/v1/notes/{NOTE_MINIMAL['id']}":
                    return httpx.Response(200, json=NOTE_MINIMAL, request=request)
                return httpx.Response(404, json={}, request=request)

        def patched_init(self_client, **kwargs):
            kwargs["transport"] = _MockTransport()
            original_init(self_client, **kwargs)

        monkeypatch.setattr(httpx.Client, "__init__", patched_init)

        result = CliRunner().invoke(
            app,
            ["granola", "import", FOLDER_ID,
             "--profile", PROFILE,
             "--output", str(tmp_path),
             "--json"],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["folder_id"] == FOLDER_ID
        assert payload["profile"] == PROFILE
        assert payload["notes"] == 2
        assert payload["mapped"] == 2
        assert payload["complete"] is True
        assert Path(payload["jsonl"]).exists()


# ---------------------------------------------------------------------------
# Tests: handle_granola_notes  (Phase 5)
# ---------------------------------------------------------------------------


class TestHandleGranolaNotes:
    def test_notes_table_output_contains_id_and_title(self, monkeypatch, capsys):
        """Human table shows full note ID and (possibly truncated) title; Next: tip included."""
        from connectonion.cli.commands.granola_commands import handle_granola_notes
        client = _mock_client(notes_return=[NOTE_STUB_1, NOTE_STUB_2])
        _patch_granola(monkeypatch, client)

        handle_granola_notes(FOLDER_ID)

        out = capsys.readouterr().out
        assert "not_note1" in out
        assert "Weekly Sync" in out
        assert "not_note2" in out
        assert "Next:" in out

    def test_notes_json_complete_true(self, monkeypatch, capsys):
        """JSON success output has notes array and complete: true."""
        from connectonion.cli.commands.granola_commands import handle_granola_notes
        client = _mock_client(notes_return=[NOTE_STUB_1, NOTE_STUB_2])
        _patch_granola(monkeypatch, client)

        handle_granola_notes(FOLDER_ID, as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert payload["complete"] is True
        assert len(payload["notes"]) == 2
        ids = [n["id"] for n in payload["notes"]]
        assert "not_note1" in ids
        assert "not_note2" in ids

    def test_notes_filters_deleted_stubs(self, monkeypatch, capsys):
        """Stubs with deleted_at set are excluded from both table and JSON output."""
        from connectonion.cli.commands.granola_commands import handle_granola_notes
        client = _mock_client(notes_return=[NOTE_STUB_1, NOTE_STUB_DELETED, NOTE_STUB_2])
        _patch_granola(monkeypatch, client)

        handle_granola_notes(FOLDER_ID, as_json=True)

        payload = json.loads(capsys.readouterr().out)
        ids = [n["id"] for n in payload["notes"]]
        assert "not_deleted" not in ids
        assert "not_note1" in ids
        assert "not_note2" in ids
        assert len(payload["notes"]) == 2

    def test_notes_empty_folder_prints_message(self, monkeypatch, capsys):
        """No active notes → prints 'No notes found' message, exits 0."""
        from connectonion.cli.commands.granola_commands import handle_granola_notes
        client = _mock_client(notes_return=[])
        _patch_granola(monkeypatch, client)

        handle_granola_notes(FOLDER_ID)  # should not raise

        out = capsys.readouterr().out
        assert "No notes found" in out

    def test_notes_json_safe_fields_only(self, monkeypatch, capsys):
        """JSON notes contain only id, title, created_at, updated_at — no private fields."""
        from connectonion.cli.commands.granola_commands import handle_granola_notes
        client = _mock_client(notes_return=[NOTE_STUB_1])
        _patch_granola(monkeypatch, client)

        handle_granola_notes(FOLDER_ID, as_json=True)

        payload = json.loads(capsys.readouterr().out)
        note = payload["notes"][0]
        assert set(note.keys()) == {"id", "title", "created_at", "updated_at"}

    def test_notes_folder_not_found_exits_1(self, monkeypatch, capsys):
        """Unknown folder ID → folder_not_found error code, exit 1."""
        from connectonion.cli.commands.granola_commands import handle_granola_notes
        client = _mock_client(folders_return=FOLDERS_PAGE["folders"])
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_notes("fld-does-not-exist", as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_code"] == "folder_not_found"
        assert "recovery_action" in payload

    def test_notes_shared_folder_exits_1(self, monkeypatch, capsys):
        """Folder with space_id != None → personal_folder_required error code, exit 1."""
        from connectonion.cli.commands.granola_commands import handle_granola_notes
        client = _mock_client(folders_return=[FOLDER_IN_SPACE])
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_notes(FOLDER_IN_SPACE["id"], as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_code"] == "personal_folder_required"
        client.list_notes.assert_not_called()

    def test_notes_list_folders_incomplete_read_exits_1_no_notes_key(self, monkeypatch, capsys):
        """GranolaIncompleteRead from list_folders() → standard error JSON (no 'notes' key), exit 1."""
        from connectonion.cli.commands.granola_commands import handle_granola_notes
        client = _mock_client()
        client.list_folders.side_effect = GranolaIncompleteRead(
            reason="429 rate limit on folder list", partial_pages=[]
        )
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_notes(FOLDER_ID, as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_code"] == "transient_error"
        assert "notes" not in payload  # standard error format, not partial-notes format
        client.list_notes.assert_not_called()

    def test_notes_list_notes_incomplete_read_partial_json_exits_1(self, monkeypatch, capsys):
        """GranolaIncompleteRead from list_notes() → partial notes JSON with complete:false, exit 1."""
        from connectonion.cli.commands.granola_commands import handle_granola_notes
        client = _mock_client()
        client.list_notes.side_effect = GranolaIncompleteRead(
            reason="500 after 3 retries",
            partial_pages=[[NOTE_STUB_1]],
        )
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_notes(FOLDER_ID, as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["complete"] is False
        assert payload["error_code"] == "transient_error"
        assert "recovery_action" in payload
        assert len(payload["notes"]) == 1
        assert payload["notes"][0]["id"] == "not_note1"

    def test_notes_list_notes_incomplete_deleted_filtered(self, monkeypatch, capsys):
        """Deleted stubs in a partial list_notes result are also filtered out."""
        from connectonion.cli.commands.granola_commands import handle_granola_notes
        client = _mock_client()
        client.list_notes.side_effect = GranolaIncompleteRead(
            reason="transient 500",
            partial_pages=[[NOTE_STUB_1, NOTE_STUB_DELETED]],
        )
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit):
            handle_granola_notes(FOLDER_ID, as_json=True)

        payload = json.loads(capsys.readouterr().out)
        ids = [n["id"] for n in payload["notes"]]
        assert "not_deleted" not in ids
        assert "not_note1" in ids


# ---------------------------------------------------------------------------
# Tests: handle_granola_import with --note-id  (Phase 5)
# ---------------------------------------------------------------------------


class TestHandleGranolaImportNoteId:
    def test_import_note_id_success_json(self, monkeypatch, tmp_path, capsys):
        """--note-id imports exactly one note; JSON output has notes=1, mapped=1, complete=true."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[NOTE_STUB_1, NOTE_STUB_2])
        # hydrate_notes must return the full note for the requested ID
        client.hydrate_notes.side_effect = lambda stubs: [NOTE_FULL]
        _patch_granola(monkeypatch, client)

        handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                              note_id="not_note1", as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert payload["notes"] == 1
        assert payload["mapped"] == 1
        assert payload["complete"] is True

    def test_import_note_id_source_yaml_records_note_id_and_limit_1(self, monkeypatch, tmp_path, capsys):
        """When --note-id is given, write_source_yaml is called with note_id and limit=1."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[NOTE_STUB_1, NOTE_STUB_2])
        client.hydrate_notes.side_effect = lambda stubs: [NOTE_FULL]
        _patch_granola(monkeypatch, client)

        handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                              note_id="not_note1")

        client.write_source_yaml.assert_called_once_with(
            tmp_path, FOLDER_ID, PROFILE, limit=1, complete=True, note_id="not_note1"
        )

    def test_import_note_id_and_limit_mutually_exclusive_exits_1(self, monkeypatch, tmp_path, capsys):
        """--note-id and --limit together → invalid_configuration, exit 1, no network calls."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client()
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                                  note_id="not_note1", limit=10, as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_code"] == "invalid_configuration"
        client.list_folders.assert_not_called()
        client.list_notes.assert_not_called()
        client.write_source_yaml.assert_not_called()

    def test_import_note_id_not_in_scoped_list_exits_1(self, monkeypatch, tmp_path, capsys):
        """note_id absent from active list → note_not_in_selected_folder, exit 1, no files."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        # Scoped list only contains not_note2; requesting not_note1 → not found
        client = _mock_client(notes_return=[NOTE_STUB_2])
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                                  note_id="not_note1", as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_code"] == "note_not_in_selected_folder"
        assert "recovery_action" in payload
        client.write_source_yaml.assert_not_called()
        assert not (tmp_path / "source.yaml").exists()

    def test_import_note_id_deleted_stub_excluded_exits_1(self, monkeypatch, tmp_path, capsys):
        """note_id present in list but deleted_at is set → treated as not found, exit 1."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        # Scoped list returns the deleted stub; requesting its ID → not found
        client = _mock_client(notes_return=[NOTE_STUB_DELETED])
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                                  note_id="not_deleted", as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_code"] == "note_not_in_selected_folder"
        client.write_source_yaml.assert_not_called()

    def test_import_note_id_with_export_allowed(self, monkeypatch, tmp_path, capsys):
        """--note-id and --export together is a valid combination; export dir is written."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[NOTE_STUB_1, NOTE_STUB_2])
        client.hydrate_notes.side_effect = lambda stubs: [NOTE_FULL]
        _patch_granola(monkeypatch, client)

        handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                              note_id="not_note1", export_id="note-export-test", as_json=True)

        payload = json.loads(capsys.readouterr().out)
        assert payload["placement"] == "export"
        assert payload["mapped"] == 1
        export_dir = tmp_path / "exports" / "note-export-test"
        assert export_dir.is_dir()
        assert (export_dir / "records.jsonl").exists()

    # -- P1 regression: scoped lookup GranolaIncompleteRead handling --

    def test_import_note_id_scoped_incomplete_note_found_reports_partial_read_exits_1(
        self, monkeypatch, tmp_path, capsys
    ):
        """P1 fix: scoped lookup is incomplete but note IS in partial pages.

        Must retain the note (complete=False) and exit 1 with partial_read,
        NOT write complete=True and exit 0.
        """
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client()
        client.list_notes.side_effect = GranolaIncompleteRead(
            reason="500 after 3 retries",
            partial_pages=[[NOTE_STUB_1, NOTE_STUB_2]],  # note_id "not_note1" IS here
        )
        client.hydrate_notes.side_effect = lambda stubs: [NOTE_FULL]
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                                  note_id="not_note1", as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["complete"] is False          # must NOT be True
        assert payload["notes"] == 1                 # note was imported
        assert payload["mapped"] == 1
        assert payload["error_code"] == "partial_read"

    def test_import_note_id_scoped_incomplete_note_not_found_reports_transient_error(
        self, monkeypatch, tmp_path, capsys
    ):
        """P1 fix: scoped lookup is incomplete and note NOT in partial pages.

        Must report transient_error (cannot confirm absence), NOT note_not_in_selected_folder.
        """
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client()
        client.list_notes.side_effect = GranolaIncompleteRead(
            reason="429 rate limit",
            partial_pages=[[NOTE_STUB_2]],  # only note2; note_id "not_note1" NOT here
        )
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                                  note_id="not_note1", as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        assert payload["error_code"] == "transient_error"  # NOT note_not_in_selected_folder
        client.write_source_yaml.assert_not_called()
        assert not (tmp_path / "source.yaml").exists()

    # -- P1 regression: export manifest scope limit --

    def test_import_note_id_export_manifest_scope_limit_is_1(
        self, monkeypatch, tmp_path, capsys
    ):
        """P1 fix: export manifest scope.limit must be 1 for --note-id imports, not null."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        client = _mock_client(notes_return=[NOTE_STUB_1, NOTE_STUB_2])
        client.hydrate_notes.side_effect = lambda stubs: [NOTE_FULL]
        _patch_granola(monkeypatch, client)

        handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path,
                              note_id="not_note1", export_id="limit-check-export", as_json=True)

        export_dir = tmp_path / "exports" / "limit-check-export"
        manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["scope"]["limit"] == 1   # must NOT be null
        assert manifest["scope"].get("note_id") == "not_note1"


# ---------------------------------------------------------------------------
# Tests: GranolaClient.write_source_yaml with note_id  (Phase 5)
# ---------------------------------------------------------------------------


class TestWriteSourceYamlNoteId:
    def test_write_source_yaml_with_note_id_recorded_in_scope(self, tmp_path, monkeypatch):
        """When note_id is given, scope dict in source.yaml includes the note_id field."""
        from connectonion.useful_tools.granola import GranolaClient

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        client.write_source_yaml(tmp_path, FOLDER_ID, PROFILE, limit=1, note_id="not_note1")

        doc = yaml.safe_load((tmp_path / "source.yaml").read_text(encoding="utf-8"))
        assert doc["scope"]["note_id"] == "not_note1"
        assert doc["scope"]["limit"] == 1

    def test_write_source_yaml_without_note_id_has_no_note_id_key(self, tmp_path, monkeypatch):
        """When note_id is not given, scope dict in source.yaml has no note_id key."""
        from connectonion.useful_tools.granola import GranolaClient

        monkeypatch.setenv("GRANOLA_API_KEY", _API_KEY)
        client = GranolaClient()
        client.write_source_yaml(tmp_path, FOLDER_ID, PROFILE)

        doc = yaml.safe_load((tmp_path / "source.yaml").read_text(encoding="utf-8"))
        assert "note_id" not in doc["scope"]


# ---------------------------------------------------------------------------
# Tests: adapter deleted_at defensive check  (Phase 5)
# ---------------------------------------------------------------------------


class TestAdapterDeletedAtDefense:
    def test_shape_problems_rejects_deleted_note(self):
        """_granola_shape_problems returns an error for a note with deleted_at set."""
        from connectonion.useful_tools.adapter import _granola_shape_problems

        problems = _granola_shape_problems(NOTE_DELETED_FULL)
        assert len(problems) == 1
        assert "deleted" in problems[0].lower()

    def test_shape_problems_accepts_active_note(self):
        """_granola_shape_problems returns no errors for a note without deleted_at."""
        from connectonion.useful_tools.adapter import _granola_shape_problems

        problems = _granola_shape_problems(NOTE_FULL, selected_folder_id=FOLDER_ID)
        assert problems == []

    def test_import_rejects_race_condition_deleted_note(self, monkeypatch, tmp_path, capsys):
        """A full note with deleted_at set (race condition) is rejected by the adapter layer."""
        from connectonion.cli.commands.granola_commands import handle_granola_import
        # hydrate_notes returns a note that has deleted_at set (race: deleted after scoped lookup)
        client = _mock_client(notes_return=[NOTE_FULL])
        client.hydrate_notes.side_effect = lambda stubs: [NOTE_DELETED_FULL]
        _patch_granola(monkeypatch, client)

        with pytest.raises(SystemExit) as exc_info:
            handle_granola_import(FOLDER_ID, profile=PROFILE, output_dir=tmp_path, as_json=True)
        assert exc_info.value.code == 1

        payload = json.loads(capsys.readouterr().out)
        # The note is rejected by the adapter (complete:true, but 0 mapped)
        assert payload["complete"] is True
        assert payload["mapped"] == 0
        assert len(payload["rejected"]) == 1
