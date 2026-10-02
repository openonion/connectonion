"""Preview commands must make correct provider requests without leaking credentials."""

import json
from types import SimpleNamespace
from urllib.parse import unquote

import httpx
import pytest
from typer.testing import CliRunner

from connectonion import environment
from connectonion.cli.commands.experiments import api, microsoft, native
from connectonion.cli.commands.experiments.register import APPS
from connectonion.cli.main import app

runner = CliRunner()


@pytest.fixture
def calls(monkeypatch):
    captured = []

    def respond(method, url, **kwargs):
        captured.append((method, url, kwargs))
        return httpx.Response(200, json={"provider_field": {"unchanged": True}, "nextPageToken": "next"})

    monkeypatch.setattr(httpx, "request", respond)
    monkeypatch.setattr(api, "oauth_token", lambda provider: provider + "-access")
    monkeypatch.setattr(environment, "load_environment", lambda: None)
    monkeypatch.setattr(
        environment,
        "setting",
        lambda name: {
            "ATLASSIAN_URL": "https://example.atlassian.net",
            "ZENDESK_URL": "https://example.zendesk.com",
            "SHOPIFY_URL": "https://example.myshopify.com",
        }.get(name, "fake-secret"),
    )
    return captured


# One representative workflow from every HTTP connector; independent endpoint contracts.
@pytest.mark.parametrize(
    "args,method,url",
    [
        (["gdocs", "read", "doc"], "GET", "https://docs.googleapis.com/v1/documents/doc"),
        (
            ["gsheets", "read", "sheet", "Sheet1!A1:B2"],
            "GET",
            "https://sheets.googleapis.com/v4/spreadsheets/sheet/values/Sheet1%21A1%3AB2",
        ),
        (["gslides", "read", "slides"], "GET", "https://slides.googleapis.com/v1/presentations/slides"),
        (["gforms", "responses", "form"], "GET", "https://forms.googleapis.com/v1/forms/form/responses"),
        (["onedrive", "list"], "GET", "https://graph.microsoft.com/v1.0/me/drive/root/children"),
        (["sharepoint", "sites", "Project"], "GET", "https://graph.microsoft.com/v1.0/sites"),
        (
            ["excel", "sheets", "file", "--drive", "business"],
            "GET",
            "https://graph.microsoft.com/v1.0/drives/business/items/file/workbook/worksheets",
        ),
        (["todo", "tasks", "list"], "GET", "https://graph.microsoft.com/v1.0/me/todo/lists/list/tasks"),
        (["notion", "read", "page"], "GET", "https://api.notion.com/v1/blocks/page/children"),
        (["airtable", "records", "base", "table name"], "GET", "https://api.airtable.com/v0/base/table%20name"),
        (["todoist", "tasks"], "GET", "https://api.todoist.com/api/v1/tasks"),
        (["trello", "boards"], "GET", "https://api.trello.com/1/members/me/boards"),
        (["asana", "projects", "workspace"], "GET", "https://app.asana.com/api/1.0/projects"),
        (["hubspot", "contacts"], "GET", "https://api.hubapi.com/crm/v3/objects/contacts"),
        (["stripe", "invoices"], "GET", "https://api.stripe.com/v1/invoices"),
        (["jira", "search", "assignee = currentUser()"], "GET", "https://example.atlassian.net/rest/api/3/search/jql"),
        (["confluence", "read", "page"], "GET", "https://example.atlassian.net/wiki/api/v2/pages/page"),
        (["zendesk", "tickets"], "GET", "https://example.zendesk.com/api/v2/tickets.json"),
        (["dropbox", "list"], "POST", "https://api.dropboxapi.com/2/files/list_folder"),
        (["figma", "read", "file"], "GET", "https://api.figma.com/v1/files/file"),
        (["shopify", "products"], "POST", "https://example.myshopify.com/admin/api/2026-07/graphql.json"),
    ],
)
def test_read_endpoints_preserve_provider_json(args, method, url, calls):
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"provider_field": {"unchanged": True}, "nextPageToken": "next"}
    assert calls[0][:2] == (method, url)
    assert all(value is not None for value in calls[0][2]["params"].values())
    assert "fake-secret" not in result.output


WRITES = [
    (["gdocs", "create", "Report"], "POST"),
    (["gdocs", "append", "doc", "--input-file", "-"], "POST"),
    (["gsheets", "create", "Report"], "POST"),
    (["gsheets", "append", "sheet", "A1:B2", "--input-file", "-"], "POST"),
    (["gsheets", "update", "sheet", "A1:B2", "--input-file", "-"], "PUT"),
    (["gslides", "create", "Report"], "POST"),
    (["gslides", "replace", "slides", "Old", "New"], "POST"),
    (["gforms", "create", "Survey"], "POST"),
    (["gforms", "update", "form", "--input-file", "-"], "POST"),
    (["excel", "update", "file", "Sheet1", "A1:B2", "--input-file", "-"], "PATCH"),
    (["todo", "create", "list", "Task"], "POST"),
    (["todo", "complete", "list", "task"], "PATCH"),
    (["notion", "create", "parent", "Report", "--input-file", "-"], "POST"),
    (["notion", "append", "page", "--input-file", "-"], "PATCH"),
    (["airtable", "create", "base", "table", "--input-file", "-"], "POST"),
    (["airtable", "update", "base", "table", "--input-file", "-"], "PATCH"),
    (["todoist", "create", "Task"], "POST"),
    (["todoist", "complete", "task"], "POST"),
    (["trello", "create", "list", "Task"], "POST"),
    (["trello", "move", "card", "list"], "PUT"),
    (["asana", "create", "project", "Task"], "POST"),
    (["asana", "complete", "task"], "PUT"),
    (["hubspot", "create", "--input-file", "-"], "POST"),
    (["jira", "transition", "ENG-1", "21"], "POST"),
    (["jira", "comment", "ENG-1", "--input-file", "-"], "POST"),
    (["confluence", "create", "space", "Report", "--input-file", "-"], "POST"),
    (["zendesk", "reply", "ticket", "--input-file", "-"], "PUT"),
]


@pytest.mark.parametrize("args,method", WRITES)
def test_every_write_previews_without_auth_or_network_and_requires_yes(args, method, calls, monkeypatch):
    data = '[["Alice", "=formula stays raw"]]' if args[0] in {"gsheets", "excel"} else "{}"

    def no_credentials(*args):
        pytest.fail("A preview must not request credentials")

    with monkeypatch.context() as context:
        context.setattr(environment, "setting", no_credentials)
        context.setattr(api, "oauth_token", no_credentials)
        preview = runner.invoke(app, args, input=data)
    assert preview.exit_code == 0, preview.output
    body = json.loads(preview.stdout)["body"]
    assert not calls
    applied = runner.invoke(app, args + ["--yes"], input=data)
    assert applied.exit_code == 0, applied.output
    assert len(calls) == 1 and calls[0][0] == method
    # Some completion endpoints have no body; IDs are shown only in preview.
    if args[:2] != ["todoist", "complete"]:
        assert calls[0][2]["json"] == body
    if args[0] == "gsheets" and args[1] in {"append", "update"}:
        assert calls[0][2]["params"]["valueInputOption"] == "RAW"
    if args[:2] == ["gforms", "create"]:
        assert calls[0][2]["params"] == {"unpublished": "true"}
    if args[:2] == ["zendesk", "reply"]:
        assert calls[0][2]["json"]["ticket"]["comment"]["public"] is False


@pytest.mark.parametrize(
    "args,parameter,value",
    [
        (["gdocs", "list", "--page-token", "next"], "pageToken", "next"),
        (["notion", "read", "page", "--cursor", "next"], "start_cursor", "next"),
        (["jira", "search", "project=ENG", "--page-token", "next"], "nextPageToken", "next"),
        (["stripe", "invoices", "--after", "in_123"], "starting_after", "in_123"),
        (["zendesk", "tickets", "--after", "next"], "page[after]", "next"),
    ],
)
def test_next_page_is_forwarded(args, parameter, value, calls):
    assert runner.invoke(app, args).exit_code == 0
    assert calls[0][2]["params"][parameter] == value


def test_dropbox_continue_and_shopify_graphql_cursor(calls):
    assert runner.invoke(app, ["dropbox", "list", "--cursor", "next"]).exit_code == 0
    assert calls[-1][1].endswith("list_folder/continue")
    assert calls[-1][2]["json"] == {"cursor": "next"}
    assert runner.invoke(app, ["shopify", "products", "--after", "next"]).exit_code == 0
    assert calls[-1][2]["json"]["variables"] == {"first": 20, "after": "next"}


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/document/d/id",
        "https://docs.google.com/document/d/",
        "https://docs.google.com/forms/d/e/published/viewform",
    ],
)
def test_bad_document_urls_are_rejected(url):
    with pytest.raises(api.ExperimentError):
        api.document_id(url)


def test_document_and_range_encoding():
    assert api.document_id("https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=0") == "sheet-id"
    assert api.segment("../a?query#fragment") == "..%2Fa%3Fquery%23fragment"
    assert unquote(microsoft.workbook_range("file", "drive", "O'Brien", "'O'Brien'!A1:B2")).endswith(
        "/worksheets/O'Brien/range(address='''O''Brien''!A1:B2')"
    )


def test_api_failure_never_dumps_provider_error_or_credential(monkeypatch):
    monkeypatch.setattr(httpx, "request", lambda *args, **kwargs: httpx.Response(403, json={"error": "fake-secret"}))
    with pytest.raises(api.ExperimentError, match="HTTP 403") as failure:
        api.request("https://api.trello.com/1/test?token=fake-secret")
    assert "fake-secret" not in str(failure.value)


def test_empty_completion_response_is_valid_json(monkeypatch):
    monkeypatch.setattr(httpx, "request", lambda *args, **kwargs: httpx.Response(204))
    assert api.request("https://api.todoist.com/api/v1/tasks/id/close", method="POST") == {"status": 204}


@pytest.mark.parametrize(
    "url",
    [
        "http://example.atlassian.net",
        "https://example.atlassian.net.evil.test",
        "https://user:secret@example.atlassian.net",
        "https://example.atlassian.net/path",
        "https://example.atlassian.net?token=secret",
    ],
)
def test_account_hosts_cannot_redirect_credentials(url, monkeypatch):
    monkeypatch.setattr(api, "key", lambda name: url)
    with pytest.raises(api.ExperimentError):
        api.hosted("ATLASSIAN_URL", "atlassian.net")


@pytest.mark.parametrize("name", APPS)
def test_experiments_are_discoverable_with_setup_and_example(name):
    result = runner.invoke(app, [name, "--help"])
    assert result.exit_code == 0
    assert "Experimental" in result.stdout and "Setup:" in result.stdout
    assert "Example:" in result.stdout and "Back:" in result.stdout


def test_official_cli_adapters_use_argument_arrays(monkeypatch):
    captured = []
    monkeypatch.setattr(native.shutil, "which", lambda name: "/bin/" + name)
    monkeypatch.setattr(
        native.subprocess, "run", lambda args, **kwargs: captured.append(args) or SimpleNamespace(returncode=0)
    )
    assert runner.invoke(app, ["github", "issue", "openonion/connectonion", "2153"]).exit_code == 0
    assert captured[-1][:5] == ["/bin/gh", "issue", "view", "2153", "--repo"]
    assert runner.invoke(app, ["dingtalk", "people", "Alice; no shell", "--profile", "work"]).exit_code == 0
    assert captured[-1] == [
        "/bin/dws",
        "contact",
        "user",
        "search",
        "--query",
        "Alice; no shell",
        "--format",
        "json",
        "--profile",
        "work",
    ]


@pytest.mark.parametrize("provider", ["google", "microsoft"])
def test_oauth_refreshes_selected_account_not_another_file(tmp_path, monkeypatch, provider):
    from datetime import datetime, timedelta, timezone

    from connectonion import backend, credentials, provider_credentials

    selected = tmp_path / "account.env"
    selected.write_text("")
    environment.select_env_file(selected)
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    provider_credentials.save_authorization(
        provider,
        selected,
        {
            "access_token": "expired",
            "refresh_token": "selected-refresh",
            "expires_at": expiry,
            "scopes": "drive" if provider == "google" else "Files.ReadWrite",
            provider + "_email": "selected@example.test",
        },
    )
    captured = []

    def refresh(record, **kwargs):
        captured.append((record, kwargs))
        return "refreshed-selected"

    monkeypatch.setattr(provider_credentials, "refresh_credentials", refresh)
    monkeypatch.setattr(credentials, "require_ambient_api_key", lambda: "ambient")
    monkeypatch.setattr(backend, "backend_url", lambda: "https://broker.example.test")
    assert api.oauth_token(provider) == "refreshed-selected"
    record, settings = captured[0]
    assert record.get("REFRESH_TOKEN") == "selected-refresh"
    assert settings == {"backend": "https://broker.example.test", "api_key": "ambient"}


def test_selected_env_supplies_connector_secret(tmp_path):
    selected = tmp_path / "tokens.env"
    selected.write_text("NOTION_TOKEN=selected-token\n")
    environment.select_env_file(selected)
    assert api.key("NOTION_TOKEN") == "selected-token"


def test_onedrive_download_does_not_forward_graph_auth(monkeypatch, tmp_path):
    from contextlib import contextmanager

    captured = []
    monkeypatch.setattr(microsoft, "oauth_token", lambda provider: "graph-secret")
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(302, headers={"location": "https://download.example.test/file"}),
    )

    @contextmanager
    def stream(method, url, **kwargs):
        captured.append((method, url, kwargs))
        yield httpx.Response(200, content=b"file bytes", request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "stream", stream)
    target = tmp_path / "file.txt"
    result = runner.invoke(app, ["onedrive", "download", "file", "--to", str(target)])
    assert result.exit_code == 0, result.output
    assert target.read_bytes() == b"file bytes"
    assert captured == [("GET", "https://download.example.test/file", {"follow_redirects": True, "timeout": 30})]
    # Refuses an overwrite before asking for a token or making a cloud request.
    refused = runner.invoke(app, ["onedrive", "download", "file", "--to", str(target)])
    assert isinstance(refused.exception, api.ExperimentError)
    assert target.read_bytes() == b"file bytes" and len(captured) == 1
