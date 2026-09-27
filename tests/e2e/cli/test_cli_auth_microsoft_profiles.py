"""`co auth microsoft` asks once for everything, and offers the core set when refused (#1887).

The owner decided one consent screen asks for everything a user can grant alone:
OneNote, OneDrive, SharePoint, Teams chats, the directory and To Do, beside mail
and calendar. Microsoft's consent is all or nothing, and some organisations block
it, so a refused full sign-in says why and falls back to the core set.
"""

import base64
import json
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from nacl.encoding import HexEncoder
from nacl.public import PublicKey, SealedBox

from .argparse_runner import ArgparseCliRunner

CREDENTIALS = {"access_token": "eyJ0.test", "refresh_token": "0.A.test", "expires_at": "2099-12-31T23:59:59",
               "scopes": "Mail.ReadWrite,Notes.ReadWrite.All", "microsoft_email": "me@example.edu"}


def _run(args, outcomes, *, tty=False, confirm=True):
    """Drive `co auth microsoft` against a stand-in oo-api.

    `outcomes` is one entry per sign-in attempt: "ok" returns sealed credentials,
    or a reason string makes the browser come back refused with that reason.
    Returns (result, the profiles each /microsoft/init asked for).
    """
    runner = ArgparseCliRunner()
    profiles, attempts = [], iter(outcomes)
    with runner.isolated_filesystem():
        Path(".env").write_text("OPENONION_API_KEY=test-key\n")

        def server_factory(*a, **k):
            result, state = {}, {"value": None}
            server = Mock()
            outcome = next(attempts)

            def handle():
                if outcome == "ok":
                    result["ciphertext"] = server.ciphertext
                else:
                    result["error"], result["reason"] = "authorization_denied", outcome
            server.handle_request.side_effect = handle
            server_factory.current = server
            return server, "http://127.0.0.1:54321/callback", state, result

        def get(url, **kwargs):
            assert url.endswith("/microsoft/init")
            profiles.append(kwargs["params"].get("profile"))
            key = PublicKey(kwargs["params"]["handoff_public_key"].encode("ascii"), encoder=HexEncoder)
            server_factory.current.ciphertext = base64.urlsafe_b64encode(
                SealedBox(key).encrypt(json.dumps(CREDENTIALS).encode())).decode()
            return Mock(status_code=200, json=lambda: {
                "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?state=s"})

        with patch("connectonion.cli.commands.auth_commands.requests.get", side_effect=get), \
                patch("connectonion.cli.commands.auth_commands.webbrowser"), \
                patch("connectonion.cli.commands.auth_commands._microsoft_callback_server", side_effect=server_factory), \
                patch("connectonion.cli.commands.auth_commands._interactive", return_value=tty), \
                patch("connectonion.cli.commands.auth_commands.typer.confirm", return_value=confirm):
            from connectonion.cli.main import cli
            result = runner.invoke(cli, ["--env-file", str(Path(".env").resolve()), "auth", "microsoft", *args])
            saved = Path(".env").read_text()
    return result, profiles, saved


def test_a_sign_in_asks_for_the_full_set():
    result, profiles, saved = _run([], ["ok"])
    assert profiles == ["full"]
    assert "Notes.ReadWrite.All" in saved


def test_core_asks_for_the_core_set_only():
    _, profiles, _ = _run(["--core"], ["ok"])
    assert profiles == ["core"]


def test_a_refused_full_sign_in_in_a_script_says_why_and_names_core():
    result, profiles, saved = _run([], ["access_denied AADSTS65004"], tty=False)
    assert profiles == ["full"]
    assert result.exit_code == 1
    assert "access_denied AADSTS65004" in result.output
    assert "co auth microsoft --core" in result.output
    assert "MICROSOFT_ACCESS_TOKEN" not in saved


def test_a_refused_full_sign_in_at_a_terminal_offers_core_and_uses_it():
    result, profiles, saved = _run([], ["access_denied AADSTS90094", "ok"], tty=True, confirm=True)
    assert profiles == ["full", "core"]
    assert "MICROSOFT_ACCESS_TOKEN=eyJ0.test" in saved


def test_declining_the_core_offer_saves_nothing():
    result, profiles, saved = _run([], ["access_denied", "ok"], tty=True, confirm=False)
    assert profiles == ["full"] and result.exit_code == 1
    assert "MICROSOFT_ACCESS_TOKEN" not in saved


def test_the_loopback_callback_keeps_the_refusal_reason():
    from connectonion.cli.commands.auth_commands import _microsoft_callback_server
    server, url, expected, result = _microsoft_callback_server()
    expected["value"] = "s"
    try:
        worker = threading.Thread(target=server.handle_request)
        worker.start()
        requests.get(url, params={"state": "s", "error": "authorization_denied",
                                  "reason": "access_denied AADSTS65004"}, timeout=2)
        worker.join(timeout=2)
    finally:
        server.server_close()
    assert result == {"error": "authorization_denied", "reason": "access_denied AADSTS65004"}
