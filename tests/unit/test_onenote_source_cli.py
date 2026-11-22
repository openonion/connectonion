"""Contract tests for the OneNote CLI source. All Graph traffic is synthetic."""

import json
from contextlib import contextmanager

import httpx
import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.credentials import MissingAmbientAPIKey
from connectonion.provider_credentials import ProviderCredentialError
from connectonion.useful_tools import onenote_source as source

PAGE = "0-synthetic!page"
SECOND = "0-synthetic!other"
TIME = "2026-11-22T10:00:00Z"
SINCE = "2026-11-22T09:59:59Z"
LINK = "https://www.onenote.com/notebooks/synthetic?page-id=demo"
SELECTION = {"notebook": "fixture-book", "section": "fixture-section", "pages": [PAGE]}
CONTENT = b'<html><body><p>Synthetic text</p><img src="https://example.invalid/image"></body></html>'


@pytest.fixture
def entry(tmp_path):
    state = tmp_path / ".state"
    state.mkdir()
    subscriptions = state / "subscriptions.json"

    def write(**kwargs):
        setting = {
            "enabled": True,
            "consented": True,
            "remote": {"selection": SELECTION},
            "import_identity": {
                "account": "https://graph.microsoft.com/v1.0/users/fixture-user",
                "scope": SELECTION,
            },
            **kwargs,
        }
        subscriptions.write_text(json.dumps({"onenote": setting}), encoding="utf-8")

    write()
    return tmp_path, write


def invoke(root, *arguments):
    return CliRunner().invoke(app, ["onenote", *arguments, "--root", str(root), "--json"],
                              env={"COLUMNS": "160"})


def error(result, code):
    assert result.exit_code == 1, result.output
    assert not result.stdout
    assert json.loads(result.stderr)["error"]["code"] == code


@pytest.fixture
def graph(monkeypatch):
    class Graph:
        GRAPH_API_URL = "https://graph.microsoft.com/v1.0"
        calls = []
        statuses = []
        scope = {"Notes.Read"}
        section = SELECTION["section"]
        account = "fixture-user"
        metadata_error = None
        html = CONTENT
        link = LINK
        last_modified = TIME
        time_after_body = None

        @property
        def _credentials(self):
            return self

        @property
        def scopes(self):
            return self.scope

        def get(self, key):
            return "synthetic-refresh" if key == "REFRESH_TOKEN" else None

        def require_configured(self):
            self.calls.append("credential check")

        def _get_access_token(self):
            return "mock access token"

        def _refresh_via_backend(self, value):
            assert value == "synthetic-refresh"
            self.calls.append("refresh")
            return "mock renewed access token"

        def _request(self, method, endpoint, **kwargs):
            assert method == "GET"
            self.calls.append(endpoint)
            if endpoint == "/me":
                return {"id": self.account}
            if self.metadata_error:
                if not isinstance(self.metadata_error, dict):
                    raise self.metadata_error
                problem = self.metadata_error.get(endpoint)
                if problem:
                    raise problem
            return {
                "id": SECOND if "other" in endpoint else PAGE,
                "parentNotebook": {"id": SELECTION["notebook"]},
                "parentSection": {"id": self.section},
                "title": "Synthetic page",
                "lastModifiedDateTime": self.last_modified,
                "links": {"oneNoteWebUrl": {"href": self.link}},
            }

    @contextmanager
    def stream(method, url, **kwargs):
        assert method == "GET"
        assert url == "https://graph.microsoft.com/v1.0/me/onenote/pages/0-synthetic%21page/content"
        assert kwargs["follow_redirects"] is False
        Graph.calls.append("body")
        if Graph.time_after_body:
            Graph.last_modified = Graph.time_after_body
        status = Graph.statuses.pop(0) if Graph.statuses else 200
        yield httpx.Response(status, content=Graph.html, headers={"Content-Type": "text/html"})

    monkeypatch.setattr(source, "Outlook", Graph)
    monkeypatch.setattr(source.httpx, "stream", stream)
    return Graph


def test_help_is_discoverable_and_does_not_read_approval(monkeypatch, graph, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("OneNote help must not load the approval file")

    monkeypatch.setattr(source, "read_json", forbidden)
    runner = CliRunner()
    for verb in ("changes", "show"):
        result = runner.invoke(app, ["onenote", verb, "--help"], env={"COLUMNS": "160", "HOME": str(tmp_path)})
        assert result.exit_code == 0
        assert "Example:" in result.stdout and "Next:" in result.stdout
    group = runner.invoke(app, ["onenote", "--help"], env={"COLUMNS": "160", "HOME": str(tmp_path)})
    assert group.exit_code == 0
    assert "changes" in group.stdout and "show" in group.stdout
    assert not graph.calls
    assert list(tmp_path.iterdir()) == []


def test_changes_returns_only_selected_metadata_and_handles_empty(entry, graph):
    root, _ = entry
    result = invoke(root, "changes", "--since", "2026-11-22T20:59:59+11:00")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == [{"id": PAGE, "title": "Synthetic page", "time": TIME, "version": TIME}]
    assert not result.stderr
    assert graph.calls == ["credential check", "/me", "/me/onenote/pages/0-synthetic%21page"]
    empty = invoke(root, "changes", "--since", TIME)
    assert empty.exit_code == 0 and json.loads(empty.stdout) == []


def test_show_matches_the_change_version_and_does_not_write(entry, graph):
    root, _ = entry
    state = root / ".state" / "subscriptions.json"
    before = state.read_bytes()
    result = invoke(root, "show", PAGE)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "id": PAGE, "title": "Synthetic page", "time": TIME, "version": TIME,
        "text": "Synthetic text\n[image]", "author": None, "link": LINK,
    }
    assert graph.calls.count("body") == 1
    assert state.read_bytes() == before
    assert sorted(p.name for p in root.rglob("*")) == [".state", "subscriptions.json"]


@pytest.mark.parametrize("setting", [{"enabled": False}, {"consented": False}, {"unsubscribed": True}])
def test_changes_rejects_unapproved_scope_before_credentials(setting, entry, graph):
    root, write = entry
    write(**setting)
    error(invoke(root, "changes", "--since", SINCE), "approval_required")
    assert not graph.calls


def test_missing_approval_and_invalid_since_require_no_credentials(tmp_path, graph):
    error(invoke(tmp_path, "show", PAGE), "approval_required")
    error(invoke(tmp_path, "changes", "--since", "2026-11-22T12:00:00"), "invalid_since")
    assert not graph.calls


def test_out_of_scope_and_excessive_selections_require_no_credentials(entry, graph):
    root, write = entry
    error(invoke(root, "show", SECOND), "out_of_scope")
    scope = {**SELECTION, "pages": [str(n) for n in range(source.MAX_SELECTED + 1)]}
    write(remote={"selection": scope}, import_identity={"scope": scope, "account": "fixture"})
    error(invoke(root, "changes", "--since", SINCE), "invalid_scope")
    assert not graph.calls


def test_moved_page_and_wrong_account_fail_before_body(entry, graph):
    root, _ = entry
    graph.account = "different-account"
    error(invoke(root, "show", PAGE), "account_mismatch")
    assert graph.calls == ["credential check", "/me"]
    graph.account = "fixture-user"
    graph.section = "different-section"
    error(invoke(root, "show", PAGE), "out_of_scope")
    assert "body" not in graph.calls


def test_missing_notes_scope_fails_without_graph_requests(entry, graph):
    root, _ = entry
    graph.scope = {"User.Read"}
    error(invoke(root, "changes", "--since", SINCE), "missing_scope")
    assert graph.calls == ["credential check"]


@pytest.mark.parametrize(("status", "code"), [(401, "reauth_required"), (403, "permission_denied"),
                                               (404, "not_found"), (429, "rate_limited")])
def test_graph_statuses_are_machine_readable_and_never_expose_provider_detail(status, code, entry, graph):
    root, _ = entry
    graph.metadata_error = ProviderCredentialError("fixture", "private provider payload", "co auth microsoft", status)
    result = invoke(root, "changes", "--since", SINCE)
    error(result, code)
    assert "private provider payload" not in result.output
    assert "body" not in graph.calls


def test_one_failed_page_never_returns_partial_metadata(entry, graph):
    root, write = entry
    scope = {**SELECTION, "pages": [PAGE, SECOND]}
    write(remote={"selection": scope}, import_identity={
        "scope": scope, "account": "https://graph.microsoft.com/v1.0/users/fixture-user",
    })
    graph.metadata_error = {"/me/onenote/pages/0-synthetic%21other":
                            ProviderCredentialError("fixture", "fixture", "co auth microsoft", 404)}
    error(invoke(root, "changes", "--since", SINCE), "not_found")
    assert "body" not in graph.calls


def test_show_refreshes_once_and_reports_rate_limit(entry, graph):
    root, _ = entry
    graph.statuses[:] = [401, 401]
    error(invoke(root, "show", PAGE), "reauth_required")
    assert graph.calls.count("refresh") == 1
    graph.statuses[:] = [429]
    error(invoke(root, "show", PAGE), "rate_limited")


def test_show_refuses_oversized_or_changed_page(entry, graph, monkeypatch):
    root, _ = entry
    monkeypatch.setattr(source, "MAX_BODY_BYTES", 12)
    error(invoke(root, "show", PAGE), "content_limit")
    monkeypatch.setattr(source, "MAX_BODY_BYTES", 4096)
    graph.time_after_body = "2026-11-22T10:00:01Z"
    error(invoke(root, "show", PAGE), "changed_during_read")


def test_show_withholds_the_whole_body_when_a_credential_shape_is_found(entry, graph):
    root, _ = entry
    graph.html = (b"<html><body><p>-----BEGIN PRIVATE KEY-----</p>"
                  b"<p>fake-private-material</p><p>-----END PRIVATE KEY-----</p></body></html>")
    result = invoke(root, "show", PAGE)
    assert result.exit_code == 0
    assert json.loads(result.stdout)["text"] == "[withheld: possible credential]"
    assert "fake-private-material" not in result.output


def test_show_rejects_links_with_access_parameters_before_body(entry, graph):
    root, _ = entry
    graph.link = LINK + "&%61uthkey=mock"
    error(invoke(root, "show", PAGE), "invalid_response")
    assert "body" not in graph.calls


def test_show_reports_missing_broker_credentials_as_json(entry, graph, monkeypatch):
    root, _ = entry

    def fail_refresh(*args):
        raise MissingAmbientAPIKey()

    monkeypatch.setattr(graph, "_refresh_via_backend", fail_refresh)
    graph.statuses[:] = [401]
    error(invoke(root, "show", PAGE), "credential_unavailable")
    assert graph.calls.count("body") == 1
