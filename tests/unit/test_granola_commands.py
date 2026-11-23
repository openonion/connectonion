"""Unit tests for connectonion/cli/commands/granola_commands.py.

All tests use synthetic fixtures and mocked GranolaClient.
No real API keys or network calls required.
"""

import json
from unittest.mock import MagicMock

import pytest

from tests.unit.granola_fixtures import (
    FOLDER_ID,
    FOLDER_IN_SPACE,
    FOLDERS_PAGE,
    NOTE_FULL,
    NOTE_MINIMAL,
    NOTE_STUB_1,
    NOTE_STUB_2,
    NOTE_STUB_DELETED,
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


# ---------------------------------------------------------------------------
# Tests: GranolaClient.write_source_yaml
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Integration: CLI runner test (co granola import through the full CLI stack)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tests: GranolaClient.write_source_yaml with note_id  (Phase 5)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tests: adapter deleted_at defensive check  (Phase 5)
# ---------------------------------------------------------------------------
