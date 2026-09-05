"""Google consent with an encrypted one-time handoff to the local CLI."""

import os
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qs, urlparse
import webbrowser

import requests
import typer
from nacl.public import PrivateKey

from ...backend import backend_url
from .project_cmd_lib import load_api_key

ALLOWED_SCOPES = {"gmail.send", "gmail.readonly", "gmail.modify", "calendar", "calendar.readonly",
                  "drive", "drive.readonly", "youtube", "youtube.readonly", "youtube.upload"}


def handle_google_auth(scopes: str | None = None):
    from .auth_commands import (_microsoft_callback_server, _decrypt_microsoft_handoff,
                                _save_google_to_env, _print_oauth_url)
    if scopes is not None and (not scopes or any(s not in ALLOWED_SCOPES for s in scopes.split(","))):
        print("Unsupported Google scopes. Next: co auth --help")
        raise typer.Exit(2)
    api_key = load_api_key()
    if not api_key:
        print("OpenOnion account not connected. Next: co auth")
        raise typer.Exit(1)
    private_key = PrivateKey.generate()
    server, callback_url, expected, result = _microsoft_callback_server(provider="Google")
    try:
        params = {"handoff_public_key": bytes(private_key.public_key).hex(), "handoff_url": callback_url}
        if scopes is not None:
            params["scopes"] = scopes
        response = requests.get(f"{backend_url()}/api/v1/oauth/google/init", params=params,
                                headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
        if response.status_code != 200:
            raise ValueError("Google authorization service needs the current CLI handoff support")
        auth_url = response.json()["auth_url"]
        parsed = urlparse(auth_url)
        if parsed.scheme != "https" or parsed.hostname != "accounts.google.com":
            raise ValueError("Unexpected Google consent URL")
        expected["value"] = parse_qs(parsed.query).get("state", [None])[0]
        if not expected["value"]:
            raise ValueError("Google authorization state missing")
        print("Opening Google consent. Credentials will be saved only on this computer.")
        _print_oauth_url(auth_url)
        webbrowser.open(auth_url)
        deadline = monotonic() + 300
        while not result and monotonic() < deadline:
            server.timeout = 1
            server.handle_request()
        if "ciphertext" not in result:
            raise ValueError("Google authorization cancelled or timed out")
        credentials = _decrypt_microsoft_handoff(private_key, result["ciphertext"], provider="google")
        path = Path(os.getenv("AGENT_CONFIG_PATH", str(Path.home() / ".co"))) / "keys.env"
        path.parent.mkdir(parents=True, exist_ok=True)
        _save_google_to_env(path, credentials)
        path.chmod(0o600)
        # Existing project overrides must not keep the old account active.
        if Path(".env").exists():
            _save_google_to_env(Path(".env"), credentials)
            Path(".env").chmod(0o600)
        for key, value in credentials.items():
            variable = {"access_token": "GOOGLE_ACCESS_TOKEN", "refresh_token": "GOOGLE_REFRESH_TOKEN",
                        "expires_at": "GOOGLE_TOKEN_EXPIRES_AT", "scopes": "GOOGLE_SCOPES",
                        "google_email": "GOOGLE_EMAIL"}.get(key)
            if variable:
                os.environ[variable] = value
        print("Google connected. Actual granted scopes saved locally. Next: co status")
    except (requests.RequestException, ValueError, KeyError, TypeError):
        print("Google authorization did not complete; existing credentials were kept. Next: co auth google")
        raise typer.Exit(1) from None
    finally:
        server.server_close()
