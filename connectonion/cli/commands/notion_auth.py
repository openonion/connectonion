"""
Purpose: `co auth notion` — connect Notion in one browser step, with the token sealed to this computer; or paste a token
LLM-Note:
  Dependencies: imports from [base64, getpass, json, os, sys, webbrowser, requests, typer, nacl, backend.backend_url, auth_commands (callback server, URL printing), provider_credentials.save_authorization, environment, env_file, secret_store, notion_api] | imported by [cli/main.py `co auth notion`] | tested by [tests/unit/test_notion_auth.py]
  Data flow: default: binds a one-command 127.0.0.1 callback and an ephemeral Curve25519 key → GET {backend}/api/v1/oauth/notion/init (OpenOnion bearer) → opens Notion's consent page, where the user picks a workspace and the pages to share → the broker exchanges the code with the integration's client secret and redirects the browser to the callback with the credentials sealed to the ephemeral key → decrypted here, checked, saved | --paste, or when the sign-in service is not there (not signed in to OpenOnion, unreachable, or it does not offer Notion yet): open Notion's token page → one hidden paste (a pipe is read for at most PIPE_WAIT seconds) → GET /users/me with it → encrypted to the store `co env set --secret` uses
  State/Effects: sign-in: writes the NOTION_* record (access and refresh token, expiry, capabilities, owner email if given, bot id, workspace id and name) to the selected env file and leaves NOTION_API_KEY alone | paste: writes NOTION_API_KEY encrypted under ~/.co/keys/secrets only after Notion accepted it, and removes a stale one from the env file | network: the OpenOnion broker, Notion and the browser
  Integration: notion_api.credential() decides which one acts: a shell export, then the sign-in, then the saved key. The broker contract is docs/integrations/notion-oauth-broker.md
  Errors: an unexpected consent URL, cancel, timeout or an unreadable handoff exit 1 with existing credentials untouched and both ways forward named; a pasted token Notion refuses is not saved; 130 on Ctrl-C | the token is never printed and never put on a command line

Why the sign-in first, as co auth asana does (#3063 review): the machine does what it can and
the person only what only they can — here, pick the workspace and pages in Notion. Notion's
OAuth needs a client secret held by a server, so the exchange happens in the OpenOnion service;
until it offers Notion, the same command falls back to pasting a token.
"""

import base64
import getpass
import json
import os
import sys
import webbrowser
from time import monotonic
from urllib.parse import parse_qs, urlparse

import requests
import typer
from nacl.public import PrivateKey, SealedBox

from ...backend import backend_url
from .project_cmd_lib import load_api_key

MANUAL = "co auth notion --paste"
TOKEN_PAGE = "https://www.notion.so/profile/integrations"
PIPE_WAIT = 30               # seconds a pipe with no terminal may take to send a pasted token
REQUIRED = ("access_token", "expires_at", "bot_id", "workspace_id")
# Notion may answer without a refresh token: the sign-in then works until it lapses, and
# renewing it says to sign in again.
OPTIONAL = ("refresh_token", "scopes", "notion_email", "workspace_name")
WAIT_SECONDS = 300


class Unavailable(Exception):
    """The sign-in service cannot be used from here now; the paste is the way on."""


def _fail(message: str, next_step: str = f"co auth notion   (or paste a token: {MANUAL})", code: int = 1) -> None:
    print(message)
    print(f"Next: {next_step}")
    raise typer.Exit(code)


def _consent_url(auth_url: str) -> str:
    """The state of a consent page that is Notion's own, or ValueError: nothing else is opened."""
    parsed = urlparse(auth_url)
    query = parse_qs(parsed.query)
    if (parsed.scheme != "https" or parsed.hostname != "api.notion.com" or parsed.path != "/v1/oauth/authorize"
            or query.get("owner") != ["user"]):
        raise ValueError("unexpected consent URL")
    state = query.get("state", [""])[0]
    if not state:
        raise ValueError("consent URL without state")
    return state


def _open_handoff(private_key: PrivateKey, ciphertext: str) -> dict:
    """The sealed result as the record's fields, or ValueError. Only this command's key opens it."""
    try:
        data = json.loads(SealedBox(private_key).decrypt(base64.urlsafe_b64decode(ciphertext.encode("ascii"))))
    except Exception as error:
        raise ValueError("handoff could not be opened") from error
    if not isinstance(data, dict) or not all(isinstance(data.get(name), str) and data[name] for name in REQUIRED):
        raise ValueError("handoff is incomplete")
    if any(data.get(name) is not None and not isinstance(data[name], str) for name in OPTIONAL):
        raise ValueError("handoff is malformed")
    return {name: data[name] for name in REQUIRED + OPTIONAL if data.get(name)}


def _wait(server, result: dict) -> None:
    deadline = monotonic() + WAIT_SECONDS
    while not result and monotonic() < deadline:
        server.timeout = min(1, max(0, deadline - monotonic()))
        server.handle_request()


def _authorize(api_key: str) -> dict:
    from .auth_commands import _microsoft_callback_server, _print_oauth_url
    private_key = PrivateKey.generate()
    server, callback_url, expected, result = _microsoft_callback_server(provider="Notion")
    try:
        try:
            response = requests.get(f"{backend_url()}/api/v1/oauth/notion/init",
                                    params={"handoff_public_key": bytes(private_key.public_key).hex(),
                                            "handoff_url": callback_url},
                                    headers={"Authorization": f"Bearer {api_key}"}, timeout=15)
        except requests.RequestException:
            raise Unavailable("The OpenOnion sign-in service could not be reached") from None
        if response.status_code != 200:
            # The body is the broker's; it is never echoed. 404 is a broker without Notion yet.
            raise Unavailable(f"The Notion sign-in service is not available (HTTP {response.status_code})")
        try:
            auth_url = response.json()["auth_url"]
            expected["value"] = _consent_url(auth_url)
        except (ValueError, KeyError, TypeError):
            _fail("The sign-in service answered with a page that is not Notion's; it was not opened.")
        print("Opening Notion. Choose the workspace, then the pages and databases co may use "
              "(pages under them are included). The token is saved only on this computer.")
        _print_oauth_url(auth_url)
        webbrowser.open(auth_url)
        _wait(server, result)
        if result.get("error"):
            _fail(f"Notion sign-in was cancelled ({result.get('reason') or result['error']}); nothing was changed.")
        if "ciphertext" not in result:
            _fail(f"No answer from the browser within {WAIT_SECONDS // 60} minutes; nothing was changed.")
        try:
            return _open_handoff(private_key, result["ciphertext"])
        except ValueError:
            _fail("The sign-in result could not be read; nothing was changed.")
    finally:
        server.server_close()



# -- the paste way ---------------------------------------------------------------

def _piped() -> str:
    """One line from a pipe, waited for at most PIPE_WAIT seconds: an open pipe that never sends is a stop."""
    if os.name != "nt":            # select() cannot watch a pipe on Windows
        import select
        try:
            ready, _, _ = select.select([sys.stdin], [], [], PIPE_WAIT)
        except (OSError, ValueError):   # stdin with no file descriptor (an in-process runner): read it
            ready = [sys.stdin]
        if not ready:
            _fail(f"No token arrived on standard input within {PIPE_WAIT} s; nothing was changed.",
                  "co auth notion --paste < token.txt", 2)
    return sys.stdin.readline().strip()


def _token_from_paste() -> str:
    print(f"Open {TOKEN_PAGE} → create an internal connection (or a personal access token), give it the pages "
          "co may use, and copy its token.")
    try:
        webbrowser.open(TOKEN_PAGE)
    except webbrowser.Error:
        pass    # no browser is fine; the link is printed
    if not sys.stdin.isatty():
        return _piped()
    return getpass.getpass("Paste the token (hidden): ").strip()


def _ready_to_save() -> None:
    """Fail before asking for a token that could not be stored."""
    from ...environment import global_config_dir
    from ...secret_store import MissingAgentKey, read_agent_key
    try:
        read_agent_key(global_config_dir())
    except MissingAgentKey as error:
        cause = str(error).split(" Next:")[0].rstrip(". ")
        _fail(f"{cause}. Nothing was saved", "co auth  then co auth notion --paste")


def _accepted(token: str) -> dict:
    """/users/me for this token, or exit: a token Notion refuses is never saved."""
    from . import notion_api as api
    response = api._send("GET", "users/me", None, None, token)
    try:
        data = response.json() if response is not None else None
    except ValueError:
        data = None
    if response is None or response.status_code != 200 or not isinstance(data, dict) or data.get("object") == "error":
        status = response.status_code if response is not None else "no answer"
        _fail(f"Notion did not accept that token ({status}); nothing was saved.", "co auth notion --paste")
    return data


def _paste() -> None:
    from ...env_file import upsert_env
    from ...environment import display_path, global_config_dir, process_environment, selected_command, selected_env_file
    from ...provider_credentials import resolve_provider_credentials
    from ...secret_store import put
    from . import notion_api as api
    _ready_to_save()
    token = _token_from_paste()
    if not token:
        _fail("No token was pasted; nothing was saved.", "co auth notion --paste", 2)
    bot = _accepted(token)
    space = api.workspace(bot)
    put(global_config_dir(), api.KEY, token)
    path = selected_env_file()
    upsert_env(path, {}, remove={api.KEY})    # a stale key in the env file would be read before the store
    print(f"✓ Notion connected: {space['bot_name'] or space['bot_id']} in workspace {space['name'] or '(unnamed)'}. "
          f"Saved encrypted as {api.KEY}.")
    if process_environment().get(api.KEY):
        print(f"! Your shell exports {api.KEY}, which is used first. Run: unset {api.KEY}")
    record = resolve_provider_credentials("notion")
    if record.get("ACCESS_TOKEN") or record.get("REFRESH_TOKEN"):
        print(f"! A co auth notion sign-in in {display_path(path)} is used before this key; "
              "co env unset NOTION_ACCESS_TOKEN removes it.")
    print(f"Next: {selected_command('co notion check')}")


def _stored_key() -> bool:
    from ...environment import global_config_dir
    from ...secret_store import SecretStoreError, stored_names
    try:
        return "notion_api_key" in stored_names(global_config_dir())
    except SecretStoreError:
        return False


def _manual_key_note(path) -> None:
    """Say which credential acts now, when a manual key is also present."""
    from ...environment import process_environment, read_env_file
    if process_environment().get("NOTION_API_KEY"):
        print("! Your shell exports NOTION_API_KEY, and a key exported in the shell is used before this sign-in. "
              "Run: unset NOTION_API_KEY")
    elif read_env_file(path).get("NOTION_API_KEY") or _stored_key():
        print("  The saved NOTION_API_KEY is kept but not used while this sign-in exists; "
              "co env unset NOTION_ACCESS_TOKEN removes the sign-in and goes back to it.")


def handle_notion_auth(paste: bool = False) -> None:
    """Connect Notion through the browser sign-in; paste a token with --paste or when the sign-in is not there."""
    from ...environment import display_path, selected_command, selected_env_file
    from ...provider_credentials import ProviderCredentialError, save_authorization
    if paste:
        return _paste()
    api_key = load_api_key()
    if not api_key:
        print("The one-step Notion sign-in goes through your OpenOnion account, which is not signed in here "
              "(co auth signs in). Pasting a token instead.")
        return _paste()
    try:
        credentials = _authorize(api_key)
    except Unavailable as why:
        print(f"{why}; nothing was changed. Pasting a token instead.")
        return _paste()
    path = selected_env_file()
    try:
        save_authorization("notion", path, credentials)
    except ProviderCredentialError:
        _fail("The sign-in result was not a usable Notion token; nothing was changed.")
    space = credentials.get("workspace_name") or credentials["workspace_id"]
    who = f" as {credentials['notion_email']}" if credentials.get("notion_email") else ""
    print(f"✓ Notion connected{who}: workspace {space}. Saved to {display_path(path)}.")
    _manual_key_note(path)
    print("  To share more pages later, run co auth notion again and pick them.")
    print(f"Next: {selected_command('co notion check')}")
