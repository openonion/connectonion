"""Credentials remain one account across refresh, auth and concurrent processes."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import threading

import httpx
import pytest

from connectonion import environment as env
from connectonion.provider_credentials import (
    ProviderCredentialError, refresh_credentials, resolve_provider_credentials,
    save_authorization,
)


@pytest.fixture
def selected(tmp_path, monkeypatch):
    for provider in env.PROVIDER_PREFIXES:
        for key in env.provider_keys(provider):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(env, "_loaded", {})
    monkeypatch.setattr(env, "_selected", None)
    path = tmp_path / "selected.env"
    path.write_text("MODEL=keep-me\n")
    env.select_env_file(path)
    return path


def grant(provider, **changes):
    return {"access_token": "access-one", "refresh_token": "refresh-one",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "scopes": "gmail.readonly" if provider == "google" else "Mail.Read",
            f"{provider}_email": "one@example.test", **changes}


@pytest.mark.parametrize("provider", ["google", "microsoft"])
def test_refresh_keeps_omitted_metadata_in_the_selected_file(selected, provider):
    save_authorization(provider, selected, grant(provider))
    record = resolve_provider_credentials(provider)
    response = httpx.Response(200, json=grant(provider))
    response = httpx.Response(200, json={key: value for key, value in response.json().items()
                                       if key not in ("scopes", f"{provider}_email", "refresh_token")})
    refresh_credentials(record, backend="https://broker.invalid", api_key="synthetic",
                        post=lambda *a, **k: response)
    saved = env.read_env_file(selected)
    assert saved[f"{provider.upper()}_EMAIL"] == "one@example.test"
    assert saved[f"{provider.upper()}_SCOPES"] == grant(provider)["scopes"]
    assert saved[f"{provider.upper()}_REFRESH_TOKEN"] == "refresh-one"
    assert saved["MODEL"] == "keep-me"
    assert not (env.global_config_dir() / "keys.env").exists()
    if os.name != "nt":
        assert selected.stat().st_mode & 0o777 == 0o600


def test_process_record_never_overwrites_another_saved_account(selected, monkeypatch):
    save_authorization("google", selected, grant("google"))
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "process-access")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "process-refresh")
    before = selected.read_bytes()
    record = resolve_provider_credentials("google")
    assert record.path is None
    assert record.get("EMAIL") is None
    assert record.scopes == set()
    refresh_credentials(record, backend="https://broker.invalid", api_key="synthetic",
                        post=lambda *a, **k: httpx.Response(200, json=grant("google", google_email="process@example.test")))
    assert selected.read_bytes() == before


def test_concurrent_account_change_is_not_overwritten(selected):
    save_authorization("google", selected, grant("google"))
    record = resolve_provider_credentials("google")
    save_authorization("google", selected, grant("google", google_email="two@example.test", refresh_token="refresh-two"))
    before = selected.read_bytes()
    with pytest.raises(ProviderCredentialError) as error:
        refresh_credentials(record, backend="https://broker.invalid", api_key="synthetic",
                            post=lambda *a, **k: pytest.fail("Old account must not refresh"))
    assert error.value.code == "record_changed"
    assert selected.read_bytes() == before


def test_two_waiting_clients_refresh_same_account_only_once(selected):
    save_authorization("microsoft", selected, grant("microsoft"))
    records = [resolve_provider_credentials("microsoft") for _ in range(2)]
    barrier = threading.Barrier(2)
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs["json"])
        return httpx.Response(200, json=grant("microsoft", access_token="rotated-access", refresh_token="rotated-refresh"))
    def run(record):
        barrier.wait(timeout=5)
        return refresh_credentials(record, backend="https://broker.invalid", api_key="synthetic", post=post)
    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(run, records)) == ["rotated-access", "rotated-access"]
    assert calls == [{"refresh_token": "refresh-one"}]
    assert env.read_env_file(selected)["MICROSOFT_REFRESH_TOKEN"] == "rotated-refresh"


@pytest.mark.parametrize("status,detail,code,next_command", [
    (401, "Invalid token", "broker_auth_failed", "co auth"),
    (401, {"error": "reauth_required"}, "reauth_required", "auth google"),
    (503, "private body", "provider_unavailable", "co status"),
])
def test_refresh_failures_name_the_correct_recovery(selected, status, detail, code, next_command):
    save_authorization("google", selected, grant("google"))
    record = resolve_provider_credentials("google")
    before = selected.read_bytes()
    with pytest.raises(ProviderCredentialError) as error:
        refresh_credentials(record, backend="https://broker.invalid", api_key="synthetic",
                            post=lambda *a, **k: httpx.Response(status, json={"detail": detail}))
    assert error.value.code == code
    assert next_command in error.value.next_command
    assert "private body" not in str(error.value)
    assert selected.read_bytes() == before


@pytest.mark.parametrize("changes", [{"google_email": "foreign@example.test"},
                                      {"expires_at": "secret-invalid-expiry"}, {"access_token": ""}])
def test_invalid_response_keeps_record(selected, changes):
    save_authorization("google", selected, grant("google"))
    record = resolve_provider_credentials("google")
    before = selected.read_bytes()
    with pytest.raises(ProviderCredentialError, match="invalid credentials"):
        refresh_credentials(record, backend="https://broker.invalid", api_key="synthetic",
                            post=lambda *a, **k: httpx.Response(200, json=grant("google", **changes)))
    assert selected.read_bytes() == before


@pytest.mark.parametrize("module,klass,provider", [
    ("gmail", "Gmail", "google"), ("gdrive", "GDrive", "google"),
    ("google_calendar", "GoogleCalendar", "google"),
    ("youtube_auth", "YouTubeGoogleAuth", "google"),
    ("outlook", "Outlook", "microsoft"), ("microsoft_calendar", "MicrosoftCalendar", "microsoft"),
])
def test_missing_metadata_is_not_a_permission_denial(selected, module, klass, provider):
    from importlib import import_module
    save_authorization(provider, selected, grant(provider, scopes=""))
    client = getattr(import_module(f"connectonion.useful_tools.{module}"), klass)()
    assert client._credentials.scopes == set()
    assert client._credentials.get("ACCESS_TOKEN") == "access-one"


@pytest.mark.parametrize("klass", ["Outlook", "MicrosoftCalendar"])
def test_microsoft_refresh_only_record_recovers(selected, monkeypatch, klass):
    from connectonion.useful_tools.outlook import Outlook
    from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
    selected.write_text("MICROSOFT_REFRESH_TOKEN=recoverable\n")
    client = {"Outlook": Outlook, "MicrosoftCalendar": MicrosoftCalendar}[klass]()
    calls = []
    monkeypatch.setattr(client, "_refresh_via_backend", lambda token: calls.append(token) or "recovered-access")
    assert client._get_access_token() == "recovered-access"
    assert calls == ["recoverable"]


def test_two_processes_serialize_refresh_and_preserve_other_settings(selected, tmp_path):
    """The file lock protects independent CLIs, not only threads in one interpreter."""
    import subprocess
    import sys
    import time
    save_authorization("google", selected, grant("google"))
    root = Path(__file__).resolve().parents[2]
    code = r'''
import sys, time
from pathlib import Path
import httpx
from connectonion.environment import select_env_file
from connectonion.env_file import upsert_env
from connectonion.provider_credentials import resolve_provider_credentials, refresh_credentials
path, ready, other, calls = map(Path, sys.argv[1:])
select_env_file(path)
record = resolve_provider_credentials("google")
ready.touch()
deadline = time.monotonic() + 10
while not other.exists():
    if time.monotonic() > deadline:
        raise TimeoutError("Second process did not start")
    time.sleep(0.01)
def post(*args, **kwargs):
    with calls.open("a") as stream:
        stream.write("refresh\n")
    return httpx.Response(200, json={"access_token": "rotated", "refresh_token": "rotated-grant", "expires_at": "2099-01-01T00:00:00Z"})
assert refresh_credentials(record, backend="https://invalid.test", api_key="synthetic", post=post) == "rotated"
upsert_env(path, {"PROCESS_" + ready.name: "saved"})
'''
    markers = [tmp_path / "A", tmp_path / "B"]
    calls = tmp_path / "calls"
    child_env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path),
                 "USERPROFILE": str(tmp_path), "PYTHONPATH": str(root)}
    workers = [subprocess.Popen([sys.executable, "-c", code, str(selected),
                str(markers[i]), str(markers[1-i]), str(calls)], env=child_env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for i in range(2)]
    try:
        for worker in workers:
            out, err = worker.communicate(timeout=20)
            assert worker.returncode == 0, out + err
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.wait()
    assert calls.read_text().splitlines() == ["refresh"]
    saved = env.read_env_file(selected)
    assert saved["GOOGLE_REFRESH_TOKEN"] == "rotated-grant"
    assert saved["GOOGLE_EMAIL"] == "one@example.test"
    assert saved["PROCESS_A"] == saved["PROCESS_B"] == "saved"
    assert saved["MODEL"] == "keep-me"


def test_new_authorization_cannot_leave_the_previous_accounts_metadata(selected):
    save_authorization("google", selected, grant("google"))
    new_grant = {"access_token": "new-account", "expires_at": "2099-01-01T00:00:00Z"}
    save_authorization("google", selected, new_grant)
    record = resolve_provider_credentials("google")
    assert record.get("EMAIL") is None
    assert record.scopes == set()
    assert "GOOGLE_EMAIL" not in os.environ
    assert "GOOGLE_SCOPES" not in os.environ
