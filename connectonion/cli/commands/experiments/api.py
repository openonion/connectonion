"""HTTP and input for the experimental connectors; provider responses stay raw."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
import typer


class ExperimentError(ValueError):
    """A provider failure without response bodies, URLs or credentials."""


def key(name: str) -> str:
    from ....environment import load_environment, setting

    load_environment()
    value = setting(name)
    if not value:
        raise ExperimentError(f"{name} is missing. Next: co env set {name} <value> --secret")
    return value


def segment(value: str) -> str:
    return quote(value, safe="")


def document_id(value: str) -> str:
    """Google document URL or opaque ID; never use a supplied URL as a host."""
    if "://" not in value:
        return segment(value)
    parsed = urlparse(value)
    parts = parsed.path.split("/")
    if parsed.hostname != "docs.google.com" or "d" not in parts:
        raise ExperimentError("Use a docs.google.com document URL or its ID.")
    identifiers = parts[parts.index("d") + 1 :]
    if not identifiers or not identifiers[0] or identifiers[0] == "e":
        raise ExperimentError("Use the document's edit URL or ID, not a published Forms /d/e URL.")
    return segment(identifiers[0])


def oauth_token(provider: str) -> str:
    from ....backend import backend_url
    from ....credentials import require_ambient_api_key
    from ....environment import load_environment
    from ....provider_credentials import refresh_credentials, resolve_provider_credentials, token_expiry

    load_environment()
    record = resolve_provider_credentials(provider)
    record.require_configured()
    token = record.get("ACCESS_TOKEN")
    expiry = token_expiry(record.get("TOKEN_EXPIRES_AT"))
    if token and (expiry is None or expiry > datetime.now(timezone.utc) + timedelta(minutes=5)):
        return token
    return refresh_credentials(record, backend=backend_url(), api_key=require_ambient_api_key())


def request(url: str, *, token: str = None, method: str = "GET", body=None, params=None, headers=None, auth=None):
    """One request, no automatic mutation retries or provider-body error dumps."""
    headers = dict(headers or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    params = {name: value for name, value in (params or {}).items() if value is not None}
    response = httpx.request(method, url, headers=headers, json=body, params=params, auth=auth, timeout=30)
    if not response.is_success:
        raise ExperimentError(
            f"Experimental API request failed (HTTP {response.status_code}). "
            "Check account access, granted permissions and API enablement. "
            "Inspect provider state before retrying a write."
        )
    return response.json() if response.content else {"status": response.status_code}


def google(url: str, **kwargs):
    return request(url, token=oauth_token("google"), **kwargs)


def graph(path: str, **kwargs):
    return request("https://graph.microsoft.com/v1.0/" + path, token=oauth_token("microsoft"), **kwargs)


def hosted(name: str, suffix: str) -> str:
    """Limit account-specific API hosts to the provider's own HTTPS domain."""
    value = key(name).rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not (parsed.hostname or "").endswith("." + suffix):
        raise ExperimentError(f"{name} must be an HTTPS {suffix} account URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise ExperimentError(f"{name} must be a base URL without credentials, path or query.")
    return value


def text_file(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).expanduser().read_text(encoding="utf-8")


def json_file(path: str):
    return json.loads(text_file(path))


def emit(data) -> None:
    print(json.dumps(data, ensure_ascii=False))


def mutation(yes: bool, operation: str, body) -> bool:
    if not yes:
        emit({"preview": operation, "body": body, "next": "Repeat the same command with --yes to apply."})
    return yes


def group(name: str, description: str, setup: str, example: str) -> typer.Typer:
    from ...typer_groups import _OneSuggestion

    return typer.Typer(
        cls=_OneSuggestion,
        no_args_is_help=True,
        help=f"Experimental: {description} Read-only unless a write is explicitly confirmed with --yes. "
        f"Setup: {setup}. Provider JSON is returned unchanged; listings may include a next-page cursor.",
        short_help=f"Experimental: {description}",
        epilog=f"Example: co {name} {example}",
    )
