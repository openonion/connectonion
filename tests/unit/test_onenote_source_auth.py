import json
from pathlib import Path
import httpx
import pytest
import yaml
from connectonion.provider_credentials import ProviderCredentialError
from connectonion.useful_tools.onenote_source import OneNoteSource
from onenote_source_fixtures import graph, BASE, DATA, HTML

def test_read_scope_reuses_microsoft_credentials_and_no_write_tools(graph):
    source = OneNoteSource()
    assert source.verify_connection() == {"account": BASE + "/users/fixture-account", "read_only": True}
    assert not any(hasattr(source, name) for name in ("create_page", "edit_page", "delete_page"))


def test_missing_read_scope_has_safe_dependency_guidance(graph, monkeypatch):
    monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.Read")
    with pytest.raises(ProviderCredentialError) as error:
        OneNoteSource()
    assert "Notes.Read" in str(error.value) and "co auth microsoft" in str(error.value)
    assert "1886" in str(error.value) and "fixture-secret-token" not in str(error.value)


def test_expired_auth_refreshes_once_and_safe_failure(graph, monkeypatch):
    from connectonion.useful_tools.outlook import Outlook
    refreshed = []
    monkeypatch.setenv("MICROSOFT_REFRESH_TOKEN", "fixture-refresh")
    monkeypatch.setattr(Outlook, "_refresh_via_backend", lambda self, rt: refreshed.append(rt) or "fresh")
    routes, _ = graph
    routes["/me"] = (401, {"error": "fixture-secret-token"})
    with pytest.raises(ProviderCredentialError) as error:
        OneNoteSource().verify_connection()
    assert refreshed == ["fixture-refresh"]
    assert "co auth microsoft" in str(error.value) and "fixture-secret-token" not in str(error.value)


def test_cli_auth_failure_json_exits_one_without_secret(graph, monkeypatch):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.Read")
    result = CliRunner().invoke(app, ["onenote", "source", "verify", "--json"])
    assert result.exit_code == 1
    assert "Notes.Read" in json.loads(result.stdout)["error"]
    assert "fixture-secret-token" not in result.output


def test_verify_cli_succeeds_with_read_only_fixture_and_hides_token(graph):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    result = CliRunner().invoke(app, ["onenote", "source", "verify", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["read_only"] is True
    assert "fixture-secret-token" not in result.output


def test_verify_transient_transport_failure_has_safe_recovery(graph):
    routes, _ = graph
    def offline():
        raise httpx.ConnectError("private network detail")
    routes["/me"] = offline
    with pytest.raises(ProviderCredentialError) as error:
        OneNoteSource().verify_connection()
    assert "co onenote source verify" in str(error.value)
    assert "private network detail" not in str(error.value)
