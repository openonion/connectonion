"""
Purpose: Authenticate with OpenOnion backend using Ed25519 signature-based authentication to obtain JWT for managed keys
LLM-Note:
  Dependencies: imports from [sys, time, yaml, requests, pathlib, rich.console, rich.progress, rich.panel, address] | imported by [cli/main.py via handle_auth(), cli/commands/init.py, cli/commands/create.py] | calls the configured backend /api/v1/auth | tested by [no direct test file]
  Data flow: receives co_dir: Path from caller → address.load(co_dir) reads Ed25519 keypair from .co/keys/ → creates auth message with timestamp → address.sign() creates signature → POST to /api/v1/auth with {public_key, message, signature, timestamp} → backend verifies signature → receives JWT token → saves OPENONION_API_KEY to the selected env file (global default) → displays balance and email status → returns success bool
  State/Effects: atomically modifies the selected env file (OPENONION_API_KEY and AGENT_EMAIL) | makes network POST requests to the configured backend | chmod 0o600 on .env files (Unix/Mac) | writes to stdout via rich.Console with progress spinner | updates ~/.co/keys.env with IS_EMAIL_ACTIVE
  Integration: exposes handle_auth() for CLI and authenticate(co_dir, save_to_project) for programmatic use | called by init.py and create.py during project setup | relies on address module for Ed25519 keypair operations | uses requests for HTTP calls | displays Rich progress spinner during network call | backend creates account on first auth (no separate registration)
  Performance: network call to backend (2-5s) | signature generation is fast (<10ms) | file I/O for .env and keys.env | retries on network errors (up to 3 attempts with exponential backoff)
  Errors: fails if ~/.co/keys/ missing (no keypair) | fails if backend unreachable (network error) | fails if signature invalid (backend 401) | fails if timestamp expired (5min window) | prints error messages to console and returns False | backend 500 errors bubble up with error details
"""

import base64
import json
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qs, urlparse

import requests
import typer
from nacl.public import PrivateKey, SealedBox
from rich.console import Console

from ... import address
from ...backend import backend_url
from .project_cmd_lib import load_api_key, upsert_env

console = Console()
OAUTH_REQUEST_TIMEOUT_SECONDS = 15


def authenticate(co_dir: Path, save_to_project: bool = False, quiet: bool = False) -> bool:
    """Authenticate with OpenOnion API directly.

    Args:
        co_dir: Path to .co directory with keys
        save_to_project: Legacy compatibility argument; explicit co_dir/--env-file determines the sole destination
        quiet: If True, suppress verbose output (only show errors and minimal success)

    Returns:
        True if authentication successful, False otherwise
    """
    # Load agent keys - let it fail naturally if there's a problem
    addr_data = address.load(co_dir)
    if not addr_data:
        console.print("❌ No agent keys found!", style="red")
        return False

    public_key = addr_data["address"]

    # Create signed authentication message
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = address.sign(addr_data, message.encode()).hex()

    # Call the new unified auth endpoint
    auth_url = f"{backend_url()}/api/v1/auth"

    try:
        response = requests.post(auth_url, json={
            "public_key": public_key,
            "signature": signature,
            "message": message
        }, timeout=15)
    except requests.exceptions.RequestException:
        # First-run must survive a bad/offline network: a traceback wall here used to
        # abort `co init` before any scaffolding. One friendly line, keep going.
        console.print("⚠️  Could not reach the ConnectOnion backend — continuing offline.", style="yellow")
        console.print("   Run [bold]co auth[/bold] once you're online to activate co/* models and agent email.", style="yellow")
        return False

    if response.status_code == 200:
        data = response.json()
        token = data.get("token")

        # Extract agent email from server response FIRST (before saving to .env)
        user = data.get("user", {})
        email_info = user.get("email") if user else None

        # Get the agent email from the server response
        if email_info:
            agent_email = email_info.get("address", f"{public_key[:10]}@mail.openonion.ai")
        else:
            agent_email = f"{public_key[:10]}@mail.openonion.ai"

        from ...environment import (global_config_dir, explicit_env_file,
                                    selected_env_file, publish_values)
        # Direct SDK calls with a project co_dir remain explicit. The CLI picks
        # selected_identity_dir(), which defaults to the global identity.
        destination = selected_env_file()
        if explicit_env_file() is None and co_dir.resolve() != global_config_dir():
            destination = co_dir.parent / ".env"
        values = {"OPENONION_API_KEY": token, "AGENT_EMAIL": agent_email,
                  "IS_EMAIL_ACTIVE": "true", "AGENT_ADDRESS": public_key}
        upsert_env(destination, values)
        publish_values({key: str(value) for key, value in values.items() if value is not None})
        console.print(f"✓ Saved to {destination}", style="green")

        # Simple success message with balance
        balance = user.get('balance_usd', 0.0) if user else 0.0
        console.print(f"✓ Authenticated (Balance: ${balance:.2f})", style="green")

        return True
    else:
        # The backend answers errors in JSON; a gateway in front of it does not.
        # A 502 HTML page made `.json()` raise out of `co init` as a traceback,
        # stopping before the project's .env was written — half a project and a
        # stack trace where an explanation belongs. Seen for real on
        # 2026-08-03: the relay returned 502 for about twenty seconds and every
        # `co init` in that window died on JSONDecodeError.
        #
        # A backend blip is ordinary operation for something meant to run for
        # years, so report which status came back rather than the shape of the
        # reply this code hoped for.
        try:
            error_msg = response.json().get("detail", "Registration failed")
        except ValueError:
            error_msg = f"HTTP {response.status_code} (the reply was not JSON)"
        console.print(f"❌ Registration failed: {error_msg}", style="red")
        return False




def handle_auth():
    """Authenticate the global identity, or the explicitly selected env's identity."""
    from ...project import selected_identity_dir
    from ...environment import global_config_dir
    co_dir = selected_identity_dir()
    if not address.load(co_dir):
        from .project_cmd_lib import ensure_global_config
        ensure_global_config()
        co_dir = global_config_dir()
    console.print(f"Using identity in {co_dir}", markup=False)
    if not authenticate(co_dir):
        console.print("Authentication did not complete. Next: co auth")
        raise typer.Exit(1)
    console.print("Next: co status")


def _save_google_to_env(env_file: Path, credentials: dict) -> None:
    from ...provider_credentials import save_authorization
    save_authorization("google", env_file, credentials)


def _print_oauth_url(auth_url: str) -> None:
    """Print a copyable URL without Rich inserting terminal-width newlines."""
    console.print("    URL:", style="dim")
    console.print(auth_url, soft_wrap=True, markup=False, highlight=False)
    console.print()


def handle_google_auth(scopes: str | None = None):
    from .google_auth import handle_google_auth as local_auth
    return local_auth(scopes=scopes)


def _save_microsoft_to_env(env_file: Path, credentials: dict) -> None:
    from ...provider_credentials import save_authorization
    save_authorization("microsoft", env_file, credentials)


def _decrypt_microsoft_handoff(private_key: PrivateKey, ciphertext: str, provider: str = "microsoft") -> dict:
    """Open the one-time callback result that was sealed to this CLI."""
    try:
        plaintext = SealedBox(private_key).decrypt(
            base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        )
        credentials = json.loads(plaintext)
    except Exception as exc:
        raise ValueError("Microsoft OAuth handoff could not be decrypted") from exc

    required = {
        "access_token", "refresh_token", "expires_at",
        "scopes", f"{provider}_email",
    }
    if not required.issubset(credentials) or not all(
        isinstance(credentials[name], str) and credentials[name]
        for name in required
    ):
        raise ValueError("Microsoft OAuth handoff is incomplete")
    return credentials


def _microsoft_callback_server(provider: str = "Microsoft"):
    """Bind a one-command loopback receiver; nothing is written by the backend."""
    result = {}
    expected_state = {"value": None}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            state = params.get("state", [None])[0]
            if parsed.path != "/callback" or state != expected_state["value"]:
                self.send_response(400)
                self.end_headers()
                return

            error = params.get("error", [None])[0]
            ciphertext = params.get("ciphertext", [None])[0]
            if error:
                result["error"] = error
                status = 400
                message = f"{provider} authorization was cancelled. You may close this tab.".encode()
            elif ciphertext:
                result["ciphertext"] = ciphertext
                status = 200
                message = f"{provider} authorization complete. You may close this tab.".encode()
            else:
                self.send_response(400)
                self.end_headers()
                return

            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

        def log_message(self, format, *args):
            # Query parameters carry ciphertext; never put them in terminal logs.
            return

    server = HTTPServer(("127.0.0.1", 0), CallbackHandler)
    callback_url = f"http://127.0.0.1:{server.server_port}/callback"
    return server, callback_url, expected_state, result


def handle_microsoft_auth():
    """Authenticate with Microsoft OAuth for Outlook/Calendar access."""

    # Check if user is authenticated with OpenOnion first
    api_key = load_api_key()
    if not api_key:
        console.print("\n❌ [bold red]Not authenticated with OpenOnion[/bold red]")
        console.print("\n[cyan]Authenticate first:[/cyan]")
        console.print("  [bold]co auth[/bold]     Get your OpenOnion API key\n")
        raise typer.Exit(1)

    api_url = f"{backend_url()}/api/v1/oauth"
    headers = {"Authorization": f"Bearer {api_key}"}

    # Get OAuth URL
    console.print("🔑 Initializing Microsoft OAuth...", style="cyan")

    handoff_private_key = PrivateKey.generate()
    callback_server, callback_url, expected_state, callback_result = (
        _microsoft_callback_server()
    )
    try:
        response = requests.get(
            f"{api_url}/microsoft/init",
            headers=headers,
            params={
                "handoff_public_key": bytes(handoff_private_key.public_key).hex(),
                "handoff_url": callback_url,
            },
            timeout=OAUTH_REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            console.print(f"\n❌ Failed to initialize OAuth (HTTP {response.status_code}). Next: co auth microsoft", style="red")
            raise typer.Exit(1)

        auth_url = response.json()['auth_url']
        state = parse_qs(urlparse(auth_url).query).get("state", [None])[0]
        if not state:
            console.print("\n❌ OAuth response did not contain a state", style="red")
            raise typer.Exit(1)
        expected_state["value"] = state

        # Open browser
        console.print("\n🌐 Opening browser for Microsoft authentication...")
        _print_oauth_url(auth_url)

        webbrowser.open(auth_url)

        console.print("⏳ Waiting for authorization...", style="yellow")
        console.print("   (Complete the authorization in your browser)\n", style="dim")

        deadline = monotonic() + 300
        while not callback_result and monotonic() < deadline:
            callback_server.timeout = min(1, max(0, deadline - monotonic()))
            callback_server.handle_request()
        if callback_result.get("error"):
            console.print("\n❌ Microsoft authorization was cancelled", style="red")
            raise typer.Exit(1)
        if "ciphertext" not in callback_result:
            console.print("\n❌ Authorization timed out", style="red")
            console.print("Please try again with: [bold]co auth microsoft[/bold]\n")
            raise typer.Exit(1)
        try:
            credentials = _decrypt_microsoft_handoff(
                handoff_private_key,
                callback_result["ciphertext"],
            )
        except ValueError:
            console.print("\n❌ Microsoft OAuth handoff was invalid", style="red")
            raise typer.Exit(1)
        console.print("✓ Authorization successful!", style="green")
    except requests.RequestException:
        console.print("Microsoft authorization service is unavailable. Next: co status")
        raise typer.Exit(1) from None
    finally:
        callback_server.server_close()

    # Save credentials
    console.print("\n💾 Saving credentials...", style="cyan")

    from ...environment import selected_env_file
    env_file = selected_env_file()
    _save_microsoft_to_env(env_file, credentials)
    console.print(f"   ✓ Saved to {env_file}", style="green")

    # Success message
    console.print("\n✅ [bold green]Microsoft account connected![/bold green]")
    console.print(f"   Email: {credentials['microsoft_email']}", style="green")
    console.print("\n📧 You can now use Microsoft tools in your agents:")
    console.print("   [dim]from connectonion import Outlook, MicrosoftCalendar[/dim]")
    console.print("   [dim]agent = Agent('assistant', tools=[Outlook()])[/dim]\n")

    from ...environment import selected_command
    console.print(f"Next: {selected_command('co outlook inbox')}", markup=False)
