"""Google OAuth tests use synthetic keys, temporary homes and mocked HTTP."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import httpx
import pytest

from connectonion.useful_tools import youtube_auth as auth
from connectonion.useful_tools.creator_plan import CreatorError


@pytest.fixture
def login(monkeypatch):
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "synthetic-old-token")
    monkeypatch.setenv("GOOGLE_SCOPES", "gmail.readonly,youtube")
    monkeypatch.setattr(auth, "require_ambient_api_key", lambda: "synthetic-broker-key")
    return auth.YouTubeGoogleAuth()


def payload(**changes):
    return {"access_token": "synthetic-new-token", "refresh_token": "synthetic-rotation",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "scopes": "gmail.readonly,youtube", **changes}


def test_refresh_uses_existing_broker_and_persists_rotated_credentials(login, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path))
    post = MagicMock(return_value=httpx.Response(200, json=payload()))
    monkeypatch.setattr(auth.httpx, "post", post)
    credentials = login.credentials()
    assert credentials.token == "synthetic-new-token"
    assert credentials.refresh_token is None
    assert "synthetic-rotation" in (tmp_path / "keys.env").read_text()
    args, kwargs = post.call_args
    assert args[0].endswith("/api/v1/oauth/google/refresh")
    assert kwargs == {"headers": {"Authorization": "Bearer synthetic-broker-key"}, "timeout": 15.0}
    post.return_value = httpx.Response(200, json=payload(access_token="synthetic-long-running-token"))
    credentials.refresh(None)
    assert credentials.token == "synthetic-long-running-token"
    assert post.call_count == 2


@pytest.mark.parametrize("scopes", ["gmail.readonly,gmail.send", "youtube.upload", "not-youtube", "youtube.readonly.evil", ""])
def test_read_requires_exact_youtube_scope_before_network(login, monkeypatch, scopes):
    monkeypatch.setenv("GOOGLE_SCOPES", scopes)
    monkeypatch.setattr(auth.httpx, "post", lambda *a, **k: pytest.fail("Missing scope reached network"))
    with pytest.raises(CreatorError, match="co auth google --youtube"):
        login.credentials()


def test_readonly_grant_cannot_upload_or_update(login, monkeypatch):
    monkeypatch.setenv("GOOGLE_SCOPES", "https://www.googleapis.com/auth/youtube.readonly")
    login.require_scope("read")
    for operation in ["upload", "update"]:
        with pytest.raises(CreatorError):
            login.require_scope(operation)


@pytest.mark.parametrize("status", [401, 404, 500])
def test_broker_error_bodies_are_not_exposed(login, monkeypatch, status):
    monkeypatch.setattr(auth.httpx, "post", lambda *a, **k: httpx.Response(status, text="SECRET"))
    with pytest.raises(CreatorError) as error:
        login.credentials()
    assert "SECRET" not in str(error.value)


def test_invalid_refresh_payload_does_not_change_saved_login(login, monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(auth.httpx, "post", lambda *a, **k: httpx.Response(200, json=payload(expires_at="SECRET")))
    with pytest.raises(CreatorError) as error:
        login.credentials()
    assert "SECRET" not in str(error.value)
    assert not (tmp_path / "keys.env").exists()
    assert auth.os.environ["GOOGLE_ACCESS_TOKEN"] == "synthetic-old-token"


def test_foreign_broker_account_stops_before_network_and_disk(login, monkeypatch, tmp_path):
    from connectonion.credentials import AmbientAPIKeyAccountMismatch
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path))
    def foreign():
        raise AmbientAPIKeyAccountMismatch(claimed="0xforeign", expected="0xexpected")
    monkeypatch.setattr(auth, "require_ambient_api_key", foreign)
    monkeypatch.setattr(auth.httpx, "post", lambda *a, **k: pytest.fail("Foreign account reached broker"))
    with pytest.raises(AmbientAPIKeyAccountMismatch):
        login.credentials()
    assert not (tmp_path / "keys.env").exists()
