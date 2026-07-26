"""Unit tests for connectonion/useful_tools/gdrive.py

Tests cover:
- scope validation at construction
- token refresh once per instance (mirrors the Gmail contract)
- list_files/search_files normalization, paging, and query escaping
- download: binary via get_media, Google-native via export_media, shortcut resolution
- upload and delete (trash, not permanent)
"""

import os
from unittest.mock import MagicMock, patch

import pytest

ENV = {
    "GOOGLE_SCOPES": "gmail.send,gmail.readonly,gmail.modify,calendar,drive",
    "GOOGLE_ACCESS_TOKEN": "test-token",
    "GOOGLE_REFRESH_TOKEN": "test-refresh",
}


@pytest.fixture(autouse=True)
def _stub_token_refresh(request, monkeypatch):
    """Drive refreshes its access token once per instance; stub that network
    call so API-operation tests stay isolated. Tests of the refresh flow
    itself opt out with @pytest.mark.real_refresh."""
    if "real_refresh" in request.keywords:
        return
    from connectonion.useful_tools.gdrive import GDrive
    monkeypatch.setattr(GDrive, "_refresh_via_backend", lambda self, rt: "test-token")


def drive_with_service(service):
    """Build a GDrive whose _get_service() returns the given mock."""
    from connectonion.useful_tools.gdrive import GDrive
    drive = GDrive()
    drive._service = service
    return drive


def file_resource(**overrides):
    resource = {
        "id": "file-1",
        "name": "Report.pdf",
        "mimeType": "application/pdf",
        "modifiedTime": "2026-07-26T14:30:00.000Z",
        "size": "2048",
        "webViewLink": "https://drive.google.com/file/d/file-1/view",
    }
    resource.update(overrides)
    return resource


class TestGDriveInit:

    def test_requires_drive_scope(self):
        with patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.send,calendar"}, clear=False):
            from connectonion.useful_tools.gdrive import GDrive
            with pytest.raises(ValueError) as exc:
                GDrive()
            assert "drive" in str(exc.value)
            assert "co auth google" in str(exc.value)

    def test_initializes_with_drive_scope(self):
        with patch.dict(os.environ, ENV, clear=False):
            from connectonion.useful_tools.gdrive import GDrive
            assert GDrive()._service is None

    @pytest.mark.real_refresh
    def test_missing_credentials_raise(self):
        with patch.dict(os.environ, {**ENV, "GOOGLE_ACCESS_TOKEN": "", "GOOGLE_REFRESH_TOKEN": ""}, clear=False):
            from connectonion.useful_tools.gdrive import GDrive
            with pytest.raises(ValueError) as exc:
                GDrive()._get_service()
            assert "credentials not found" in str(exc.value)

    @pytest.mark.real_refresh
    @patch("connectonion.useful_tools.gdrive.build")
    def test_refreshes_token_before_building_service(self, mock_build, monkeypatch):
        """Same contract as Gmail: refresh up front, never trust a cached token."""
        from connectonion.useful_tools.gdrive import GDrive
        calls = []
        monkeypatch.setattr(GDrive, "_refresh_via_backend", lambda self, rt: calls.append(rt) or "fresh")

        with patch.dict(os.environ, ENV, clear=False):
            GDrive()._get_service()

        assert calls == ["test-refresh"]
        assert mock_build.call_args.kwargs["credentials"].token == "fresh"


class TestListFiles:

    def test_normalizes_and_excludes_trash(self):
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {
            "files": [file_resource(), file_resource(id="file-2", name="Notes", size=None)]
        }

        with patch.dict(os.environ, ENV, clear=False):
            files = drive_with_service(service).list_files(last=20)

        assert files[0] == {
            "id": "file-1",
            "name": "Report.pdf",
            "type": "application/pdf",
            "modified": "2026-07-26T14:30:00.000Z",
            "size": 2048,
            "link": "https://drive.google.com/file/d/file-1/view",
        }
        # Folders and native docs report no size at all.
        assert files[1]["size"] == 0
        assert service.files.return_value.list.call_args.kwargs["q"] == "trashed = false"

    def test_orders_by_most_recently_modified(self):
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).list_files()

        assert service.files.return_value.list.call_args.kwargs["orderBy"] == "modifiedTime desc"

    def test_requests_the_fields_it_reads(self):
        """Without an explicit nested fields string Drive omits size/modifiedTime."""
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).list_files()

        fields = service.files.return_value.list.call_args.kwargs["fields"]
        assert fields.startswith("nextPageToken, files(")
        for name in ("id", "name", "mimeType", "modifiedTime", "size", "webViewLink"):
            assert name in fields

    def test_pages_until_enough_files(self):
        service = MagicMock()
        service.files.return_value.list.return_value.execute.side_effect = [
            {"files": [file_resource(id=f"a{i}") for i in range(100)], "nextPageToken": "page2"},
            {"files": [file_resource(id="b1"), file_resource(id="b2")]},
        ]

        with patch.dict(os.environ, ENV, clear=False):
            files = drive_with_service(service).list_files(last=101)

        assert len(files) == 101
        assert files[-1]["id"] == "b1"

    def test_stops_when_drive_runs_out(self):
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {"files": [file_resource()]}

        with patch.dict(os.environ, ENV, clear=False):
            files = drive_with_service(service).list_files(last=50)

        assert len(files) == 1

    def test_zero_returns_empty_without_calling_drive(self):
        service = MagicMock()

        with patch.dict(os.environ, ENV, clear=False):
            assert drive_with_service(service).list_files(last=0) == []

        service.files.assert_not_called()


class TestSearchFiles:

    def test_builds_name_query_and_excludes_trash(self):
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {"files": [file_resource()]}

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).search_files("report")

        assert service.files.return_value.list.call_args.kwargs["q"] == (
            "name contains 'report' and trashed = false"
        )

    def test_escapes_quotes_so_the_query_cannot_break_out(self):
        """An apostrophe in a filename would otherwise make Drive reject the request."""
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).search_files("Bob's plan")

        assert service.files.return_value.list.call_args.kwargs["q"] == (
            "name contains 'Bob\\'s plan' and trashed = false"
        )

    def test_escapes_backslashes(self):
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).search_files("a\\b")

        assert "a\\\\b" in service.files.return_value.list.call_args.kwargs["q"]

    def test_blank_query_returns_empty_without_calling_drive(self):
        service = MagicMock()

        with patch.dict(os.environ, ENV, clear=False):
            assert drive_with_service(service).search_files("   ") == []

        service.files.assert_not_called()


class TestDownload:

    def _stub_download(self, monkeypatch, payload=b"filebytes"):
        """Make MediaIoBaseDownload write payload into the buffer in one chunk."""
        def fake_downloader(buffer, request):
            downloader = MagicMock()

            def next_chunk():
                buffer.write(payload)
                return (None, True)

            downloader.next_chunk.side_effect = next_chunk
            return downloader

        monkeypatch.setattr("connectonion.useful_tools.gdrive.MediaIoBaseDownload", fake_downloader)

    def test_binary_file_uses_get_media(self, tmp_path, monkeypatch):
        self._stub_download(monkeypatch)
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = file_resource()

        with patch.dict(os.environ, ENV, clear=False):
            result = drive_with_service(service).download("file-1", dest=str(tmp_path))

        service.files.return_value.get_media.assert_called_once()
        service.files.return_value.export_media.assert_not_called()
        assert (tmp_path / "Report.pdf").read_bytes() == b"filebytes"
        assert "Report.pdf" in result

    def test_google_doc_is_exported_with_an_extension(self, tmp_path, monkeypatch):
        """A Doc has no bytes of its own — downloading it must export instead."""
        self._stub_download(monkeypatch, b"# Title")
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = file_resource(
            name="Design Notes",
            mimeType="application/vnd.google-apps.document",
            size=None,
        )

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).download("file-1", dest=str(tmp_path))

        service.files.return_value.export_media.assert_called_once()
        assert service.files.return_value.export_media.call_args.kwargs["mimeType"] == "text/markdown"
        assert (tmp_path / "Design Notes.md").read_bytes() == b"# Title"

    def test_sheet_exports_to_csv(self, tmp_path, monkeypatch):
        self._stub_download(monkeypatch, b"a,b\n1,2\n")
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = file_resource(
            name="Budget", mimeType="application/vnd.google-apps.spreadsheet", size=None,
        )

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).download("file-1", dest=str(tmp_path))

        assert service.files.return_value.export_media.call_args.kwargs["mimeType"] == "text/csv"
        assert (tmp_path / "Budget.csv").exists()

    def test_folder_download_is_refused_with_a_clear_message(self, tmp_path):
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = file_resource(
            name="Projects", mimeType="application/vnd.google-apps.folder", size=None,
        )

        with patch.dict(os.environ, ENV, clear=False):
            with pytest.raises(ValueError) as exc:
                drive_with_service(service).download("file-1", dest=str(tmp_path))

        assert "folder" in str(exc.value)
        assert "Projects" in str(exc.value)

    def test_shortcut_resolves_to_its_target(self, tmp_path, monkeypatch):
        self._stub_download(monkeypatch)
        service = MagicMock()
        service.files.return_value.get.return_value.execute.side_effect = [
            file_resource(
                id="shortcut-1",
                name="Link to Report",
                mimeType="application/vnd.google-apps.shortcut",
                size=None,
                shortcutDetails={"targetId": "file-1"},
            ),
            file_resource(),
        ]

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).download("shortcut-1", dest=str(tmp_path))

        assert (tmp_path / "Report.pdf").exists()

    def test_explicit_destination_path_is_honoured(self, tmp_path, monkeypatch):
        self._stub_download(monkeypatch)
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = file_resource()
        target = tmp_path / "renamed.pdf"

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).download("file-1", dest=str(target))

        assert target.read_bytes() == b"filebytes"


class TestUploadAndDelete:

    def test_upload_sends_the_file_and_returns_its_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "connectonion.useful_tools.gdrive.MediaFileUpload",
            lambda path, mimetype=None, resumable=False: MagicMock(),
        )
        local = tmp_path / "report.pdf"
        local.write_bytes(b"data")
        service = MagicMock()
        service.files.return_value.create.return_value.execute.return_value = file_resource()

        with patch.dict(os.environ, ENV, clear=False):
            result = drive_with_service(service).upload(str(local))

        assert service.files.return_value.create.call_args.kwargs["body"] == {"name": "report.pdf"}
        assert result["id"] == "file-1"

    def test_upload_honours_an_explicit_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "connectonion.useful_tools.gdrive.MediaFileUpload",
            lambda path, mimetype=None, resumable=False: MagicMock(),
        )
        local = tmp_path / "report.pdf"
        local.write_bytes(b"data")
        service = MagicMock()
        service.files.return_value.create.return_value.execute.return_value = file_resource()

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).upload(str(local), name="Q3 Report.pdf")

        assert service.files.return_value.create.call_args.kwargs["body"]["name"] == "Q3 Report.pdf"

    def test_upload_missing_file_raises(self, tmp_path):
        service = MagicMock()

        with patch.dict(os.environ, ENV, clear=False):
            with pytest.raises(ValueError) as exc:
                drive_with_service(service).upload(str(tmp_path / "nope.pdf"))

        assert "not found" in str(exc.value)

    def test_delete_trashes_rather_than_destroying(self):
        """An agent calling this by mistake must be recoverable from the Drive UI."""
        service = MagicMock()

        with patch.dict(os.environ, ENV, clear=False):
            drive_with_service(service).delete("file-1")

        service.files.return_value.delete.assert_not_called()
        assert service.files.return_value.update.call_args.kwargs["body"] == {"trashed": True}
