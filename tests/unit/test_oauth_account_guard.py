"""Account-boundary tests shared by the OAuth provider tools."""

import base64
import importlib
import json
import os

import httpx
import pytest

from connectonion import credentials
from connectonion.credentials import AmbientAPIKeyAccountMismatch


OAUTH_REFRESHERS = (
    ("connectonion.useful_tools.gdrive", "GDrive"),
    ("connectonion.useful_tools.gmail", "Gmail"),
    ("connectonion.useful_tools.google_calendar", "GoogleCalendar"),
    ("connectonion.useful_tools.outlook", "Outlook"),
    ("connectonion.useful_tools.microsoft_calendar", "MicrosoftCalendar"),
)


def _token_for(public_key: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"public_key": public_key}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


@pytest.mark.parametrize("module_name,class_name", OAUTH_REFRESHERS)
def test_oauth_refresh_rejects_a_foreign_account_before_network_or_mutation(
    module_name, class_name, monkeypatch, tmp_path
):
    expected = "0x" + "1" * 64
    foreign = "0x" + "2" * 64
    openonion_token = _token_for(foreign)
    provider_values = {
        "GOOGLE_ACCESS_TOKEN": "google-access-before",
        "GOOGLE_REFRESH_TOKEN": "google-refresh-before",
        "GOOGLE_TOKEN_EXPIRES_AT": "google-expiry-before",
        "MICROSOFT_ACCESS_TOKEN": "microsoft-access-before",
        "MICROSOFT_REFRESH_TOKEN": "microsoft-refresh-before",
        "MICROSOFT_TOKEN_EXPIRES_AT": "microsoft-expiry-before",
    }
    monkeypatch.setenv("OPENONION_API_KEY", openonion_token)
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / "config"))
    for name, value in provider_values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        credentials,
        "project_identity",
        lambda: {"address": expected},
    )
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: pytest.fail("foreign account reached OAuth broker"),
    )

    module = importlib.import_module(module_name)
    refresher = getattr(module, class_name).__new__(getattr(module, class_name))
    with pytest.raises(AmbientAPIKeyAccountMismatch) as error:
        refresher._refresh_via_backend("provider-refresh-secret")

    assert openonion_token not in str(error.value)
    assert "provider-refresh-secret" not in str(error.value)
    assert foreign[:16] in str(error.value)
    assert {
        name: os.environ[name]
        for name in provider_values
    } == provider_values
    assert not (tmp_path / "config" / "keys.env").exists()
