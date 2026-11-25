"""co auth notion: one browser step by default, NOTION_API_KEY kept as the manual way.

LLM-Note: Tests for connectonion/cli/commands/notion_auth.py and the credential order in
notion_api.credential(). The broker (OpenOnion) and the browser are stood in for: the consent
step seals a result to the public key the CLI sent, exactly as the real broker does. Notion is the
stateful fake from notion_fake.py, told which tokens it accepts.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import httpx
import pytest
import typer
from nacl.public import PublicKey, SealedBox
from typer.testing import CliRunner

from connectonion import environment as env
from connectonion.cli.commands import auth_commands, notion_auth
from connectonion.cli.commands import notion_api as api
from connectonion.cli.main import app
from connectonion.provider_credentials import (ProviderCredentialError, refresh_credentials,
                                               resolve_provider_credentials, save_authorization)
from tests.unit.notion_fake import FakeNotion

CONSENT = "https://api.notion.com/v1/oauth/authorize?client_id=c&response_type=code&owner=user&state=s1"


def soon(hours=1):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def grant(**changes):
    return {"access_token": "ntn-access-1", "refresh_token": "ntn-refresh-1", "expires_at": soon(),
            "scopes": "read_content,update_content,insert_content", "bot_id": "bot-1",
            "workspace_id": "ws-acme", "workspace_name": "Acme", "notion_email": "ann@example.test", **changes}


@pytest.fixture
def keys(tmp_path, monkeypatch):
    """The default env file, empty of any Notion credential."""
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / "config"))
    for key in env.provider_keys("notion") + ("NOTION_API_KEY", "NOTION_VERSION"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(env, "_loaded", {})
    monkeypatch.setattr(env, "_selected", None)
    path = tmp_path / "config" / "keys.env"
    path.parent.mkdir()
    return path


@pytest.fixture
def consent(keys, monkeypatch):
    """The broker's init answer and the browser: opening the page seals `payload` to the CLI."""
    monkeypatch.setattr(notion_auth, "load_api_key", lambda: "openonion-token")
    server, expected, result = Mock(), {}, {}
    monkeypatch.setattr(auth_commands, "_microsoft_callback_server",
                        lambda **kw: (server, "http://127.0.0.1:1234/callback", expected, result))
    response = Mock(status_code=200)
    response.json.return_value = {"auth_url": CONSENT}
    get = Mock(return_value=response)
    monkeypatch.setattr(notion_auth.requests, "get", get)
    payload = grant()

    def browser(url):
        public_key = get.call_args.kwargs["params"]["handoff_public_key"]
        sealed = SealedBox(PublicKey(bytes.fromhex(public_key))).encrypt(json.dumps(payload).encode())
        result["ciphertext"] = base64.urlsafe_b64encode(sealed).decode()
    opened = Mock(side_effect=browser)
    monkeypatch.setattr(notion_auth.webbrowser, "open", opened)
    return {"path": keys, "server": server, "result": result, "response": response, "get": get,
            "payload": payload, "opened": opened}


def auth():
    return CliRunner().invoke(app, ["auth", "notion"])


# -- co auth notion ------------------------------------------------------------

def test_one_browser_step_saves_the_sign_in_here_and_prints_no_token(consent):
    result = auth()
    assert result.exit_code == 0, result.output
    saved = env.read_env_file(consent["path"])
    assert saved["NOTION_ACCESS_TOKEN"] == "ntn-access-1" and saved["NOTION_REFRESH_TOKEN"] == "ntn-refresh-1"
    assert saved["NOTION_BOT_ID"] == "bot-1" and saved["NOTION_WORKSPACE_NAME"] == "Acme"
    assert "NOTION_API_KEY" not in saved
    assert "ntn-access-1" not in result.output and "ntn-refresh-1" not in result.output
    assert "workspace Acme" in result.output and "pages" in result.output
    assert result.output.strip().splitlines()[-1] == "Next: co notion check"
    assert consent["get"].call_args.args[0].endswith("/api/v1/oauth/notion/init")
    consent["server"].server_close.assert_called_once()


@pytest.mark.parametrize("url", ["https://evil.invalid/v1/oauth/authorize?owner=user&state=s",
                                 "http://api.notion.com/v1/oauth/authorize?owner=user&state=s",
                                 "https://api.notion.com/v1/oauth/authorize?owner=user",
                                 "https://api.notion.com/v1/oauth/authorize?owner=workspace&state=s"])
def test_a_consent_page_that_is_not_notions_own_is_never_opened(consent, url):
    consent["response"].json.return_value = {"auth_url": url}
    result = auth()
    assert result.exit_code == 1
    consent["opened"].assert_not_called()
    assert not consent["path"].exists()


def test_a_broker_without_notion_falls_back_to_the_paste_and_never_echoes_its_body(consent):
    consent["response"].status_code = 404
    consent["response"].text = "private-broker-body"
    result = auth()
    assert "HTTP 404" in result.output and "private-broker-body" not in result.output
    assert "Pasting a token instead" in result.output
    assert not consent["path"].exists()


def test_cancelling_keeps_what_was_there(consent):
    consent["path"].write_text("NOTION_API_KEY=ntn_manual\n")
    consent["opened"].side_effect = lambda url: consent["result"].update(error="access_denied")
    result = auth()
    assert result.exit_code == 1 and "cancelled" in result.output
    assert consent["path"].read_text() == "NOTION_API_KEY=ntn_manual\n"


@pytest.mark.parametrize("broken", [{"bot_id": ""}, {"workspace_id": None}, {"refresh_token": 5},
                                    {"expires_at": "2000-01-01T00:00:00+00:00"}])
def test_an_incomplete_or_stale_result_writes_nothing(consent, broken):
    consent["payload"].update(broken)
    if broken.get("workspace_id", "") is None:
        del consent["payload"]["workspace_id"]
    result = auth()
    assert result.exit_code == 1
    assert not consent["path"].exists()


def test_an_unreadable_result_writes_nothing(consent):
    consent["opened"].side_effect = lambda url: consent["result"].update(ciphertext="not-sealed")
    assert auth().exit_code == 1
    assert not consent["path"].exists()


def test_without_openonion_it_says_so_and_falls_back_to_the_paste(consent, monkeypatch):
    monkeypatch.setattr(notion_auth, "load_api_key", lambda: None)
    result = auth()
    assert "co auth signs in" in result.output and "Pasting a token instead" in result.output
    consent["get"].assert_not_called()


def test_a_saved_manual_key_is_kept_and_said_to_be_unused(consent):
    consent["path"].write_text("NOTION_API_KEY=ntn_manual\nNOTION_VERSION=2025-09-03\n")
    result = auth()
    assert result.exit_code == 0, result.output
    saved = env.read_env_file(consent["path"])
    assert saved["NOTION_API_KEY"] == "ntn_manual" and saved["NOTION_VERSION"] == "2025-09-03"
    assert "kept but not used" in result.output and "co env unset NOTION_ACCESS_TOKEN" in result.output


def test_a_sign_in_without_a_refresh_token_is_saved_and_later_asks_to_sign_in_again(consent, monkeypatch):
    del consent["payload"]["refresh_token"]
    assert auth().exit_code == 0
    saved = env.read_env_file(consent["path"])
    assert "NOTION_REFRESH_TOKEN" not in saved
    fake = FakeNotion()
    fake.accepted = set()
    monkeypatch.setattr(api, "_http", fake.client)
    monkeypatch.setenv("OPENONION_API_KEY", "openonion-token")
    result = CliRunner().invoke(app, ["notion", "check"])
    assert result.exit_code == 1 and result.stderr.strip().splitlines()[-1] == "Next: co auth notion"


# -- which credential acts ------------------------------------------------------------

@pytest.fixture
def notion(keys, monkeypatch):
    fake = FakeNotion()
    monkeypatch.setattr(api, "_http", fake.client)
    monkeypatch.setattr(api, "_sleep", lambda seconds: None)
    monkeypatch.setenv("OPENONION_API_KEY", "openonion-token")
    return fake


def bearer(fake):
    return fake.requests[-1].headers["authorization"].removeprefix("Bearer ")


def check():
    return CliRunner().invoke(app, ["notion", "check"])


def test_the_sign_in_is_used_before_a_saved_manual_key(notion, keys):
    keys.write_text("NOTION_API_KEY=ntn_manual\n")
    save_authorization("notion", keys, grant())
    result = check()
    assert result.exit_code == 0, result.output
    assert bearer(notion) == "ntn-access-1" and "Connected with the co auth notion sign-in" in result.stdout


def test_a_saved_manual_key_works_with_no_sign_in(notion, keys):
    keys.write_text("NOTION_API_KEY=ntn_manual\n")
    result = check()
    assert result.exit_code == 0, result.output
    assert bearer(notion) == "ntn_manual" and "Connected with NOTION_API_KEY" in result.stdout


def test_a_key_exported_in_the_shell_wins_over_the_sign_in(notion, keys, monkeypatch):
    save_authorization("notion", keys, grant())
    monkeypatch.setenv("NOTION_API_KEY", "ntn_shell")
    assert check().exit_code == 0
    assert bearer(notion) == "ntn_shell"


def test_removing_the_sign_in_goes_back_to_the_manual_key(notion, keys):
    keys.write_text("NOTION_API_KEY=ntn_manual\n")
    save_authorization("notion", keys, grant())
    removed = CliRunner().invoke(app, ["env", "unset", "NOTION_ACCESS_TOKEN"])
    assert removed.exit_code == 0, removed.output
    saved = env.read_env_file(keys)
    assert not any(key.startswith("NOTION_") and key != "NOTION_API_KEY" for key in saved)   # bot id too
    assert check().exit_code == 0 and bearer(notion) == "ntn_manual"


# -- renewal ----------------------------------------------------------------------

@pytest.fixture
def broker(monkeypatch):
    """The OpenOnion refresh endpoint: each call rotates both tokens, as Notion does."""
    calls = []

    def post(url, headers, json, timeout):
        calls.append((url, json["refresh_token"]))
        n = len(calls) + 1
        return httpx.Response(200, json={"access_token": f"ntn-access-{n}", "refresh_token": f"ntn-refresh-{n}",
                                         "expires_at": soon(), "bot_id": "bot-1", "workspace_id": "ws-acme"})
    monkeypatch.setattr(httpx, "post", post)
    return calls


def test_an_expired_sign_in_is_renewed_before_the_request_and_the_rotation_saved(notion, keys, broker):
    save_authorization("notion", keys, grant())
    expired = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    keys.write_text(keys.read_text().replace(env.read_env_file(keys)["NOTION_TOKEN_EXPIRES_AT"], expired))
    assert check().exit_code == 0
    assert broker == [(broker[0][0], "ntn-refresh-1")] and broker[0][0].endswith("/api/v1/oauth/notion/refresh")
    assert bearer(notion) == "ntn-access-2"
    saved = env.read_env_file(keys)
    assert saved["NOTION_REFRESH_TOKEN"] == "ntn-refresh-2" and saved["NOTION_BOT_ID"] == "bot-1"


def test_a_rejected_token_is_renewed_once_and_the_request_sent_again(notion, keys, broker):
    save_authorization("notion", keys, grant())
    notion.accepted = {"ntn-access-2"}           # Notion gives no lifetime: the first sign of expiry is a 401
    assert check().exit_code == 0
    assert len(broker) == 1 and bearer(notion) == "ntn-access-2"




def test_a_sign_in_removed_in_notion_says_sign_in_again(notion, keys, broker):
    save_authorization("notion", keys, grant())
    notion.accepted = set()                       # removed under Settings → Connections
    result = check()
    assert result.exit_code == 1
    assert "even after renewing" in result.stderr
    assert result.stderr.strip().splitlines()[-1] == "Next: co auth notion"
    assert len(broker) == 1                       # renewed once, not in a loop


def test_a_refresh_the_broker_refuses_names_co_auth_notion(notion, keys, monkeypatch):
    save_authorization("notion", keys, grant())
    notion.accepted = set()
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(401, json={"detail": {"error": "reauth_required"}}))
    result = check()
    assert result.exit_code == 1 and "could not be renewed" in result.stderr
    assert result.stderr.strip().splitlines()[-1] == "Next: co auth notion"
    assert env.read_env_file(keys)["NOTION_REFRESH_TOKEN"] == "ntn-refresh-1"     # nothing overwritten


def test_another_process_rotating_the_same_bot_is_adopted_without_an_email(keys):
    save_authorization("notion", keys, grant(notion_email=None))
    stale = resolve_provider_credentials("notion")
    stale.values["NOTION_TOKEN_EXPIRES_AT"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    save_authorization("notion", keys, grant(notion_email=None, access_token="ntn-access-9",
                                             refresh_token="ntn-refresh-9"))   # the other process's refresh
    token = refresh_credentials(stale, backend="https://broker.invalid", api_key="x",
                                post=lambda *a, **k: pytest.fail("already renewed elsewhere"))
    assert token == "ntn-access-9"


def test_a_record_now_for_another_bot_is_never_refreshed_over(keys):
    save_authorization("notion", keys, grant(notion_email=None))
    stale = resolve_provider_credentials("notion")
    save_authorization("notion", keys, grant(notion_email=None, bot_id="bot-2", refresh_token="other"))
    with pytest.raises(ProviderCredentialError) as error:
        refresh_credentials(stale, backend="https://broker.invalid", api_key="x",
                            post=lambda *a, **k: pytest.fail("a different installation must not refresh"))
    assert error.value.code == "record_changed"


def test_a_refresh_answered_for_another_bot_is_refused(keys):
    save_authorization("notion", keys, grant())
    record = resolve_provider_credentials("notion")
    before = keys.read_bytes()
    with pytest.raises(ProviderCredentialError) as error:
        refresh_credentials(record, backend="https://broker.invalid", api_key="x",
                            post=lambda *a, **k: httpx.Response(200, json=grant(bot_id="bot-2")))
    assert error.value.code == "invalid_response" and keys.read_bytes() == before


# -- where else it shows ---------------------------------------------------------------

def test_auth_status_lists_notion_without_a_network_call(keys):
    save_authorization("notion", keys, grant())
    result = CliRunner().invoke(app, ["auth", "status"])
    assert result.exit_code == 0, result.output
    assert "Notion OAuth: connected" in result.output and "ntn-access-1" not in result.output


# -- co auth notion --paste: a token made by hand, checked, saved encrypted ---------------

@pytest.fixture
def pasting(keys, monkeypatch):
    """An agent key to encrypt with, a fake Notion that knows ntn_good, and no browser."""
    (keys.parent / "keys").mkdir(exist_ok=True)
    (keys.parent / "keys" / "agent.key").write_bytes(bytes(range(32)))
    fake = FakeNotion()
    monkeypatch.setattr(api, "_http", fake.client)
    monkeypatch.setattr(api, "_sleep", lambda seconds: None)
    monkeypatch.setattr(notion_auth.webbrowser, "open", Mock())
    return fake


def paste(token):
    return CliRunner().invoke(app, ["auth", "notion", "--paste"], input=token + "\n")


def test_a_pasted_token_notion_accepts_is_saved_encrypted_and_never_printed(pasting, keys):
    from connectonion.secret_store import get
    result = paste("ntn_good")
    assert result.exit_code == 0, result.output
    assert "Notion connected" in result.output and "ntn_good" not in result.output
    assert get(keys.parent, "NOTION_API_KEY") == "ntn_good"
    assert "NOTION_API_KEY" not in (keys.read_text() if keys.exists() else "")


def test_a_pasted_token_notion_refuses_is_not_saved(pasting, keys, monkeypatch):
    from connectonion.secret_store import stored_names
    pasting.fail("GET", "users/me", httpx.Response(401, json={
        "object": "error", "status": 401, "code": "unauthorized", "message": "API token is invalid."}))
    result = paste("ntn_bad")
    assert result.exit_code == 1 and "did not accept" in result.output
    assert "notion_api_key" not in stored_names(keys.parent)


def test_a_paste_says_when_the_sign_in_will_still_be_used(pasting, keys):
    save_authorization("notion", keys, grant())
    result = paste("ntn_good")
    assert result.exit_code == 0, result.output
    assert "used before this key" in result.output


def test_paste_with_nothing_pasted_saves_nothing(pasting, keys):
    assert paste("").exit_code == 2


def test_a_pipe_that_never_sends_stops_at_the_wait_on_windows_too(monkeypatch):
    """Windows has no select() on a pipe: the read runs on a thread, and the wait still ends."""
    import io, threading, time
    released = threading.Event()
    class Silent(io.StringIO):
        def readline(self, *a):
            released.wait(5)              # an open pipe that sends nothing, until the test lets go
            return ""
    monkeypatch.setattr(notion_auth, "CAN_SELECT", False)
    monkeypatch.setattr(notion_auth, "PIPE_WAIT", 0.1)
    monkeypatch.setattr(notion_auth.sys, "stdin", Silent())
    before = set(threading.enumerate())
    started = time.monotonic()
    with pytest.raises(typer.Exit) as stop:
        notion_auth._piped()
    waited = time.monotonic() - started
    released.set()
    for reader in set(threading.enumerate()) - before:
        reader.join(2)
    assert stop.value.exit_code == 2 and waited < 2


def test_a_pipe_that_sends_is_read_on_windows_too(monkeypatch):
    import io
    monkeypatch.setattr(notion_auth, "CAN_SELECT", False)
    monkeypatch.setattr(notion_auth.sys, "stdin", io.StringIO("ntn_from_pipe\n"))
    assert notion_auth._piped() == "ntn_from_pipe"
