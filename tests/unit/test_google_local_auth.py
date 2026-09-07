"""Local Google handoff: no status polling, no remote credential store."""
import base64
import json
from unittest.mock import Mock
import pytest
from nacl.public import PublicKey, SealedBox
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import auth_commands, google_auth


@pytest.fixture
def flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / "config"))
    monkeypatch.setattr(google_auth, "load_api_key", lambda: "test-account")
    server, expected, result = Mock(), {}, {}
    monkeypatch.setattr(auth_commands, "_microsoft_callback_server", lambda **kw: (server, "http://127.0.0.1:1234/callback", expected, result))
    response = Mock(status_code=200)
    response.json.return_value = {"auth_url": "https://accounts.google.com/o/oauth2/v2/auth?state=test-state"}
    get = Mock(return_value=response)
    monkeypatch.setattr(google_auth.requests, "get", get)
    payload = dict(access_token="test-access", refresh_token="test-refresh", expires_at="2099-01-01T00:00:00Z",
                   scopes="youtube.readonly", google_email="user@example.invalid")
    def consent(url):
        public_key = get.call_args.kwargs["params"]["handoff_public_key"]
        result["ciphertext"] = base64.urlsafe_b64encode(SealedBox(PublicKey(bytes.fromhex(public_key))).encrypt(json.dumps(payload).encode())).decode()
    monkeypatch.setattr(google_auth.webbrowser, "open", consent)
    return tmp_path, server, result, response, get, payload


@pytest.mark.parametrize("scopes", [None, "youtube.readonly"])
def test_handoff_saves_only_locally_and_keeps_actual_grant(flow, scopes):
    path, server, _, _, get, _ = flow
    args = ["auth", "google"] + (["--scopes", scopes] if scopes else [])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    saved = (path / "config/keys.env").read_text()
    assert "GOOGLE_SCOPES=youtube.readonly" in saved
    assert "GOOGLE_REFRESH_TOKEN=test-refresh" in saved
    assert "test-refresh" not in result.output and "test-access" not in result.output
    assert get.call_count == 1 and get.call_args.args[0].endswith("/google/init")
    assert get.call_args.kwargs["params"].get("scopes") == scopes
    server.server_close.assert_called_once()


def test_cancel_preserves_existing_credentials(flow, monkeypatch):
    path, server, callback, _, _, _ = flow
    config = path / "config"
    config.mkdir()
    (config / "keys.env").write_text("GOOGLE_REFRESH_TOKEN=old\n")
    monkeypatch.setattr(google_auth.webbrowser, "open", lambda url: callback.update(error="denied"))
    result = CliRunner().invoke(app, ["auth", "google"])
    assert result.exit_code == 1
    assert (config / "keys.env").read_text() == "GOOGLE_REFRESH_TOKEN=old\n"
    assert "co auth google" in result.output
    server.server_close.assert_called_once()


def test_bad_ciphertext_cannot_overwrite_credentials(flow, monkeypatch):
    path, _, callback, _, _, _ = flow
    monkeypatch.setattr(google_auth.webbrowser, "open", lambda url: callback.update(ciphertext="invalid"))
    result = CliRunner().invoke(app, ["auth", "google"])
    assert result.exit_code == 1
    assert not (path / "config/keys.env").exists()


def test_wrong_consent_host_not_opened(flow, monkeypatch):
    _, _, _, response, _, _ = flow
    response.json.return_value = {"auth_url": "https://evil.invalid/?state=test"}
    browser = Mock()
    monkeypatch.setattr(google_auth.webbrowser, "open", browser)
    assert CliRunner().invoke(app, ["auth", "google"]).exit_code == 1
    browser.assert_not_called()


def test_scope_typo_is_usage_error_before_network(flow):
    _, _, _, _, get, _ = flow
    result = CliRunner().invoke(app, ["auth", "google", "--scopes", "unknown"])
    assert result.exit_code == 2
    get.assert_not_called()


def test_backend_error_does_not_print_body(flow):
    _, _, _, response, _, _ = flow
    response.status_code = 500
    response.text = "private-provider-body"
    result = CliRunner().invoke(app, ["auth", "google"])
    assert result.exit_code == 1
    assert "private-provider-body" not in result.output
