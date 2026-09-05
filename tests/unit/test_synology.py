"""Unit tests for connectonion/useful_tools/synology.py

Tests cover:
- QuickConnect resolution: candidate ordering (LAN before relay) and unknown-ID errors
- pick_reachable: falls past unreachable candidates, raises when none answer
- login: credentials go in the POST body, never the query string
- stale-session retry on DSM codes 106/107/119
- list_files/search_files normalization
- connection status and existing sharing-link inventory
- search cleanup after failures and bounded polling
- upload: the binary part is written last, and overwrite is always explicit
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

ENV = {
    "SYNOLOGY_URL": "https://nas.local:5001",
    "SYNOLOGY_ACCOUNT": "aaron",
    "SYNOLOGY_PASSWORD": "hunter2",
    "SYNOLOGY_SID": "test-sid",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture(autouse=True)
def _no_credential_writes(monkeypatch):
    """save_credentials() writes ~/.co/keys.env — never touch the real one in tests."""
    import connectonion.useful_tools.synology as syno
    monkeypatch.setattr(syno, "save_credentials", lambda **kwargs: None)


def nas(sid="test-sid"):
    """Build a Synology instance with API-path discovery already primed."""
    from connectonion.useful_tools.synology import Synology
    instance = Synology()
    instance.sid = sid
    instance._paths = {
        "SYNO.API.Auth": {"path": "auth.cgi"},
        "SYNO.FileStation.List": {"path": "entry.cgi"},
        "SYNO.FileStation.Search": {"path": "entry.cgi"},
        "SYNO.FileStation.Upload": {"path": "entry.cgi"},
        "SYNO.FileStation.Sharing": {"path": "entry.cgi"},
    }
    return instance


# === QuickConnect resolution ===


def test_resolve_quickconnect_puts_lan_before_relay():
    """The relay is throttled, so same-network addresses must be tried first."""
    from connectonion.useful_tools.synology import resolve_quickconnect

    body = {
        "server": {
            "port": 5001,
            "interface": [{"ip": "192.168.1.50"}],
            "ddns": "mynas.synology.me",
            "external": {"ip": "203.0.113.9"},
        },
    }
    with patch("httpx.post", return_value=MagicMock(json=lambda: body)):
        candidates = resolve_quickconnect("mynas")

    assert candidates[0] == "https://192.168.1.50:5001"
    assert "https://mynas.synology.me:5001" in candidates
    assert candidates[-1] == "https://mynas.quickconnect.to"


def test_resolve_quickconnect_skips_null_ddns():
    """DSM reports a literal 'NULL' string when no DDNS is configured."""
    from connectonion.useful_tools.synology import resolve_quickconnect

    body = {"server": {"port": 5001, "interface": [], "ddns": "NULL"}}
    with patch("httpx.post", return_value=MagicMock(json=lambda: body)):
        candidates = resolve_quickconnect("mynas")

    assert not any("NULL" in c for c in candidates)


def test_resolve_quickconnect_rejects_unknown_id():
    """errno 4 is 'Alias not found' — verified against the live endpoint."""
    from connectonion.useful_tools.synology import resolve_quickconnect

    body = {"errno": 4, "errinfo": "get_server_info.go:92[Alias not found]"}
    with patch("httpx.post", return_value=MagicMock(json=lambda: body)):
        with pytest.raises(ValueError, match="not found"):
            resolve_quickconnect("nope")


# === Connection ladder ===


def test_pick_reachable_falls_past_unreachable_candidates():
    """An address that isn't on this network is expected, not fatal."""
    from connectonion.useful_tools.synology import pick_reachable

    def get(url, **kwargs):
        if "192.168" in url:
            raise httpx.ConnectTimeout("not on this network")
        return MagicMock(status_code=200, json=lambda: {"success": True})

    with patch("httpx.get", side_effect=get):
        assert pick_reachable(["https://192.168.1.50:5001", "https://relay"]) == "https://relay"


def test_pick_reachable_falls_past_a_200_that_is_not_dsm():
    """A portal or proxy answering 200 with HTML is "not DSM", same as no answer.

    Seen for real: `co syno login openonion-nas` resolved four candidates and
    died with a JSONDecodeError on the first one instead of probing the rest.
    """
    from connectonion.useful_tools.synology import pick_reachable

    def get(url, **kwargs):
        if "portal" in url:
            reply = MagicMock(status_code=200)
            reply.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")
            return reply
        return MagicMock(status_code=200, json=lambda: {"success": True})

    with patch("httpx.get", side_effect=get):
        assert pick_reachable(["https://portal", "https://relay"]) == "https://relay"


def test_pick_reachable_raises_when_nothing_answers():
    from connectonion.useful_tools.synology import pick_reachable

    with patch("httpx.get", side_effect=httpx.ConnectTimeout("down")):
        with pytest.raises(ValueError, match="Could not reach"):
            pick_reachable(["https://a", "https://b"])


# === Auth ===


def test_login_sends_password_in_body_not_query():
    """The official examples put passwd= in a GET query string, where it lands
    in proxy and server logs. We POST it instead."""
    from connectonion.useful_tools.synology import Synology

    client = MagicMock()
    client.post.return_value = MagicMock(json=lambda: {"success": True, "data": {"sid": "fresh-sid"}})
    client.__enter__ = lambda self: client
    client.__exit__ = lambda *a: None

    instance = nas(sid="")
    with patch.object(Synology, "_client", return_value=client):
        instance._login()

    assert instance.sid == "fresh-sid"
    body = client.post.call_args.kwargs["data"]
    assert body["passwd"] == "hunter2"
    assert body["format"] == "sid"
    assert "params" not in client.post.call_args.kwargs


def test_login_decodes_wrong_password():
    from connectonion.useful_tools.synology import Synology

    client = MagicMock()
    client.post.return_value = MagicMock(json=lambda: {"success": False, "error": {"code": 400}})
    client.__enter__ = lambda self: client
    client.__exit__ = lambda *a: None

    with patch.object(Synology, "_client", return_value=client):
        with pytest.raises(ValueError, match="incorrect password"):
            nas(sid="")._login()


@pytest.mark.parametrize("code", [106, 107, 119])
def test_stale_session_triggers_one_relogin_then_retries(code):
    """Sessions expire after 7 days and die on duplicate login — re-auth silently."""
    from connectonion.useful_tools.synology import Synology

    instance = nas()
    replies = [
        {"success": False, "error": {"code": code}},
        {"success": True, "data": {"files": []}},
    ]

    with patch.object(Synology, "_call", side_effect=replies) as call:
        with patch.object(Synology, "_login") as login:
            instance._request("SYNO.FileStation.List", "list", folder_path="/home")

    assert login.call_count == 1
    assert call.call_count == 2


def test_real_error_is_not_retried():
    """A missing file is a real answer, not a dead session — surface it."""
    from connectonion.useful_tools.synology import Synology

    instance = nas()
    with patch.object(Synology, "_call", return_value={"success": False, "error": {"code": 408}}) as call:
        with pytest.raises(ValueError, match="No such file or directory"):
            instance._request("SYNO.FileStation.List", "list", folder_path="/nope")

    assert call.call_count == 1


# === Listing ===


def test_list_files_without_path_lists_shares():
    from connectonion.useful_tools.synology import Synology

    data = {"shares": [{"path": "/home", "name": "home", "isdir": True}]}
    with patch.object(Synology, "_request", return_value=data) as request:
        files = nas().list_files()

    assert request.call_args.args[1] == "list_share"
    assert files == [{"path": "/home", "name": "home", "type": "dir", "size": 0, "modified": 0}]


def test_list_files_normalizes_entries():
    from connectonion.useful_tools.synology import Synology

    data = {
        "files": [
            {"path": "/home/a.txt", "name": "a.txt", "isdir": False,
             "additional": {"size": 1024, "time": {"mtime": 1700000000}}},
        ]
    }
    with patch.object(Synology, "_request", return_value=data):
        files = nas().list_files(path="/home")

    assert files[0] == {
        "path": "/home/a.txt", "name": "a.txt", "type": "file",
        "size": 1024, "modified": 1700000000,
    }


def test_list_files_rejects_nonsense_count():
    assert nas().list_files(last=0) == []


def test_search_runs_start_poll_clean():
    """File Station search is non-blocking: start, poll until finished, clean up."""
    from connectonion.useful_tools.synology import Synology

    replies = [
        {"taskid": "task-1"},
        {"finished": True, "files": [{"path": "/home/cat.jpg", "name": "cat.jpg", "isdir": False}]},
        {},
    ]
    with patch.object(Synology, "_request", side_effect=replies) as request:
        files = nas().search_files("cat")

    methods = [call.args[1] for call in request.call_args_list]
    assert methods == ["start", "list", "clean"]
    assert files[0]["name"] == "cat.jpg"


def test_search_cleans_the_task_when_polling_fails():
    """Temporary DSM search databases must not leak after a failed poll."""
    from connectonion.useful_tools.synology import Synology

    def request(_self, _api, method, **_params):
        if method == "start":
            return {"taskid": "task-1"}
        if method == "list":
            raise ValueError("network interrupted")
        return {}

    with patch.object(Synology, "_request", autospec=True, side_effect=request) as mocked:
        with pytest.raises(ValueError, match="network interrupted"):
            nas().search_files("cat")

    assert [call.args[2] for call in mocked.call_args_list] == ["start", "list", "clean"]


def test_search_times_out_instead_of_returning_partial_results():
    """An unfinished search is not a successful, complete answer."""
    from connectonion.useful_tools.synology import Synology, SynologyError

    replies = [{"taskid": "task-1"}, {"finished": False, "files": []}, {}]
    with patch.object(Synology, "_request", side_effect=replies) as request:
        with pytest.raises(SynologyError) as failure:
            nas().search_files("cat", poll_attempts=1, poll_interval=0)

    assert failure.value.code == "search_timeout"
    assert [call.args[1] for call in request.call_args_list] == ["start", "list", "clean"]


def test_search_ignores_empty_query():
    assert nas().search_files("   ") == []


# === Status and sharing-link inventory ===


def test_status_proves_file_station_access_without_writing():
    from connectonion.useful_tools.synology import Synology

    with patch.object(Synology, "_request", return_value={"shares": []}) as request:
        status = nas().status()

    request.assert_called_once_with("SYNO.FileStation.List", "list_share", limit=1)
    assert status == {
        "connected": True,
        "url": "https://nas.local:5001",
        "account": "aaron",
        "session_cached": True,
        "tls_verification": False,
    }


def test_list_sharing_links_normalizes_existing_links():
    from connectonion.useful_tools.synology import Synology

    data = {
        "links": [{
            "id": "share-1",
            "url": "https://nas.local/sharing/abc123",
            "path": "/home/report.pdf",
            "date_expired": "2026-09-30",
            "status": "valid",
        }],
    }
    with patch.object(Synology, "_request", return_value=data) as request:
        links = nas().list_sharing_links(last=25)

    request.assert_called_once_with(
        "SYNO.FileStation.Sharing", "list", version=3, offset=0, limit=25
    )
    assert links == [{
        "id": "share-1",
        "path": "/home/report.pdf",
        "url": "https://nas.local/sharing/abc123",
        "expires": "2026-09-30",
        "status": "valid",
    }]


def test_list_sharing_links_rejects_nonsense_count_without_a_request():
    from connectonion.useful_tools.synology import Synology

    with patch.object(Synology, "_request") as request:
        assert nas().list_sharing_links(last=0) == []

    request.assert_not_called()


# === Transfer ===


def test_upload_writes_binary_part_last_and_always_sets_overwrite(tmp_path):
    """DSM requires the file part last (RFC 1867), and returns error 1805 when
    overwrite is unspecified and the destination exists."""
    from connectonion.useful_tools.synology import Synology

    local = tmp_path / "note.txt"
    local.write_text("hello")

    client = MagicMock()
    client.post.return_value = MagicMock(json=lambda: {"success": True})
    client.__enter__ = lambda self: client
    client.__exit__ = lambda *a: None

    with patch.object(Synology, "_client", return_value=client):
        result = nas().upload(str(local), "/home/docs")

    kwargs = client.post.call_args.kwargs
    # httpx serializes every `data` field before any `files` entry, which is
    # what puts the binary part last on the wire.
    assert "file" in kwargs["files"]
    assert kwargs["data"]["overwrite"] == "false"
    assert kwargs["data"]["path"] == "/home/docs"
    assert "note.txt" in result


def test_upload_rejects_missing_local_file():
    with pytest.raises(ValueError, match="File not found"):
        nas().upload("/no/such/file.txt", "/home")


def test_share_returns_the_url():
    from connectonion.useful_tools.synology import Synology

    data = {"links": [{"url": "https://nas.local/sharing/abc123"}]}
    with patch.object(Synology, "_request", return_value=data):
        assert nas().share("/home/a.txt") == "https://nas.local/sharing/abc123"


def test_share_raises_when_no_link_came_back():
    from connectonion.useful_tools.synology import Synology

    with patch.object(Synology, "_request", return_value={"links": []}):
        with pytest.raises(ValueError, match="no sharing link"):
            nas().share("/home/a.txt")


def test_missing_url_tells_the_user_to_log_in(monkeypatch):
    from connectonion.useful_tools.synology import Synology

    monkeypatch.delenv("SYNOLOGY_URL")
    with pytest.raises(ValueError, match="co syno login"):
        Synology()


def _upload_client(replies):
    """A client whose post() returns each reply in turn."""
    client = MagicMock()
    client.post.side_effect = [MagicMock(json=lambda b=b: b) for b in replies]
    client.__enter__ = lambda self: client
    client.__exit__ = lambda *a: None
    return client


def test_upload_sends_the_sid_in_the_query_not_the_form(tmp_path):
    """#794: every path failed with 'SID not found' (DSM 119).

    `_call()` and `download()` both put `_sid` in the query string; upload put
    it in the multipart body, and SYNO.FileStation.Upload does not read it
    there. One inconsistency, one command broken.
    """
    from connectonion.useful_tools.synology import Synology

    local = tmp_path / "clip.mp4"
    local.write_bytes(b"data")
    client = _upload_client([{"success": True}])

    with patch.object(Synology, "_client", return_value=client):
        nas().upload(str(local), "/home/Social Media Content")

    kwargs = client.post.call_args.kwargs
    assert kwargs.get("params", {}).get("_sid"), "the sid has to travel in the query"
    assert "_sid" not in kwargs.get("data", {}), "and not in the form body"


def test_upload_retries_once_after_a_stale_session(tmp_path):
    """119 is already in STALE_SESSION, but only `_request()` acts on it and
    upload does not go through `_request()`. So the one command that could not
    recover from a dead session was the one that hit it."""
    from connectonion.useful_tools.synology import Synology

    local = tmp_path / "clip.mp4"
    local.write_bytes(b"data")
    client = _upload_client([
        {"success": False, "error": {"code": 119}},
        {"success": True},
    ])
    logins = []

    with patch.object(Synology, "_client", return_value=client):
        with patch.object(Synology, "_login", side_effect=lambda: logins.append(1)):
            result = nas().upload(str(local), "/home/docs")

    assert len(logins) == 1, "a stale session should re-login exactly once"
    assert client.post.call_count == 2
    assert "clip.mp4" in result


def test_upload_does_not_retry_a_real_failure(tmp_path):
    """Only the stale-session codes get a second attempt. Retrying a genuine
    refusal doubles the wait before the user sees the reason."""
    from connectonion.useful_tools.synology import Synology

    local = tmp_path / "clip.mp4"
    local.write_bytes(b"data")
    client = _upload_client([{"success": False, "error": {"code": 1805}}])

    with patch.object(Synology, "_client", return_value=client):
        with pytest.raises(ValueError):
            nas().upload(str(local), "/home/docs")

    assert client.post.call_count == 1


def test_upload_still_puts_the_binary_part_last(tmp_path):
    """The RFC 1867 constraint the original test protects — moving the sid
    must not disturb it."""
    from connectonion.useful_tools.synology import Synology

    local = tmp_path / "note.txt"
    local.write_text("hello")
    client = _upload_client([{"success": True}])

    with patch.object(Synology, "_client", return_value=client):
        nas().upload(str(local), "/home/docs", overwrite=True)

    kwargs = client.post.call_args.kwargs
    assert "file" in kwargs["files"]
    assert kwargs["data"]["overwrite"] == "true"
